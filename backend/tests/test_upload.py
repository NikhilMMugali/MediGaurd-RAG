import fitz

SAMPLE_PATIENT_PDF_TEXT = (
    "Patient: P999\n"
    "Name: Aarav Shah\n"
    "Diagnosis: Hypertension\n"
    "Medication: Metformin\n"
    "Allergy: Penicillin\n"
)


def _make_pdf_bytes(text: str = SAMPLE_PATIENT_PDF_TEXT) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line)
        y += 14
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _login(client, seeded_doctor):
    response = client.post(
        "/api/auth/login",
        json={"username": "doctor01", "password": "secret123", "role": "DOCTOR"},
    )
    return response.json()["access_token"]


def test_upload_requires_auth(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_rejects_non_pdf(client, seeded_doctor):
    token = _login(client, seeded_doctor)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", b"not a pdf", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_upload_extracts_pdf_text(client, seeded_doctor):
    token = _login(client, seeded_doctor)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999.pdf", _make_pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["page_count"] == 1


def test_upload_maps_new_patient_into_database(client, seeded_doctor, db_session):
    """Phase 2: a new patient PDF must create real rows in the canonical
    schema (patients/conditions/medications/allergies), not just extracted
    text, and every created row must carry provenance back to the upload."""
    from app.models.hospital import Allergy, Condition, Medication, Patient
    from app.models.ward import PatientAssignment

    token = _login(client, seeded_doctor)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999.pdf", _make_pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    document_id = response.json()["document_id"]

    patient = db_session.query(Patient).filter(Patient.external_patient_id == "P999").first()
    assert patient is not None
    assert patient.first == "Aarav"
    assert patient.last == "Shah"
    assert patient.source_document_id == document_id

    condition = db_session.query(Condition).filter(Condition.patient == patient.id).first()
    assert condition is not None
    assert condition.description == "Hypertension"
    assert condition.source_document_id == document_id

    # Regression: a brand-new patient with no PatientAssignment row at all
    # previously left the uploader unable to ask about them afterward (chat
    # and document Q&A both deny a patient-scoped role for an "unassigned"
    # patient) — the uploader must become the attending by default.
    assignment = (
        db_session.query(PatientAssignment)
        .filter(PatientAssignment.patient_id == patient.id, PatientAssignment.user_id == seeded_doctor.id)
        .first()
    )
    assert assignment is not None
    assert assignment.active is True

    medication = db_session.query(Medication).filter(Medication.patient == patient.id).first()
    assert medication is not None
    assert medication.description == "Metformin"

    allergy = db_session.query(Allergy).filter(Allergy.patient == patient.id).first()
    assert allergy is not None
    assert allergy.description == "Penicillin"


def test_uploader_can_query_the_newly_created_patient_afterward(client, seeded_doctor):
    """End-to-end regression for the exact bug reported: upload a PDF that
    introduces a new patient, then immediately ask about that patient
    through the normal chat RAG endpoint — must be ANSWERED, never DENIED."""
    token = _login(client, seeded_doctor)
    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999.pdf", _make_pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_response.status_code == 200
    patient_id = upload_response.json()["patient_id"]
    assert patient_id is not None

    query_response = client.post(
        "/api/rag/query",
        json={"question": "What conditions does this patient have?", "patient_id": patient_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert query_response.status_code == 200
    body = query_response.json()
    assert body["status"] == "ANSWERED"
    assert "Hypertension" in body["answer"]


def test_upload_of_fully_indexed_duplicate_reports_already_available(client, seeded_doctor):
    """Same bytes uploaded twice, by hash, regardless of the filename used
    the second time. A duplicate whose first upload was fully indexed is no
    longer a dead-end 409 — it's recognized as already-ready and the SAME
    document_id is returned, not a second document (section 5 "duplicate
    PDF uploads"). PyMuPDF stamps a fresh random document ID on every
    tobytes() call, so the identical-content bytes are generated once here
    and reused, rather than regenerated."""
    token = _login(client, seeded_doctor)
    headers = {"Authorization": f"Bearer {token}"}
    pdf_bytes = _make_pdf_bytes()

    first = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["chunks_indexed"] > 0

    second = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999_again.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["document_id"] == first_body["document_id"]
    assert second_body["status"] == "COMPLETED"
    assert second_body["chunks_indexed"] == first_body["chunks_indexed"]


def test_upload_of_broken_duplicate_is_repaired_not_dead_ended(client, seeded_doctor, db_session):
    """Regression for the exact reported bug: a document that was uploaded
    once but never actually indexed (predates the narrative-fallback fix,
    or a prior indexing failure) must not keep reporting a dead-end
    "already uploaded, COMPLETED" on every re-upload — it should be repaired
    in place and become genuinely queryable."""
    from app.models.documents import KnowledgeRecord, SourceDocument
    from app.models.provenance import new_uuid

    token = _login(client, seeded_doctor)
    headers = {"Authorization": f"Bearer {token}"}
    pdf_bytes = _make_pdf_bytes("Lab report with no recognizable Label:Value fields at all.\nJust prose.")

    broken = SourceDocument(
        id=new_uuid(),
        file_name="legacy_upload.pdf",
        file_hash=__import__("hashlib").sha256(pdf_bytes).hexdigest(),
        source_type="UPLOADED_PDF",
        uploaded_by=seeded_doctor.id,
        status="COMPLETED",
    )
    db_session.add(broken)
    db_session.commit()
    assert db_session.query(KnowledgeRecord).filter(KnowledgeRecord.source_document_id == broken.id).count() == 0

    response = client.post(
        "/api/documents/upload",
        files={"file": ("legacy_upload.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == broken.id
    assert body["status"] == "COMPLETED"
    assert body["chunks_indexed"] > 0

    repaired_count = db_session.query(KnowledgeRecord).filter(KnowledgeRecord.source_document_id == broken.id).count()
    assert repaired_count == body["chunks_indexed"]


def test_duplicate_with_chunks_but_no_patient_link_is_repaired(client, seeded_doctor, db_session):
    """Regression for the exact second reported bug: a document that has
    knowledge_records (so the zero-chunks repair path above wouldn't even
    trigger) but whose patient was never identified — "no patient could be
    identified in it" in the upload response — stays permanently
    unretrievable by a patient-scoped role unless re-upload also repairs the
    missing patient link, not just missing chunks."""
    from app.models.documents import KnowledgeRecord, SourceDocument
    from app.models.provenance import new_uuid
    from app.models.ward import PatientAssignment

    token = _login(client, seeded_doctor)
    headers = {"Authorization": f"Bearer {token}"}
    page_text = (
        "Patient Name\n"
        "KAVYA DEMO PATIENT\n"
        "Demo Patient ID\n"
        "DEMO-PT-2026-1042\n"
        "Gender\n"
        "Female\n"
        "Hemoglobin 13.8 g/dL 12.0 - 16.0 NORMAL\n"
    )
    pdf_bytes = _make_pdf_bytes(page_text)

    broken = SourceDocument(
        id=new_uuid(),
        file_name="kavya_report.pdf",
        file_hash=__import__("hashlib").sha256(pdf_bytes).hexdigest(),
        source_type="UPLOADED_PDF",
        uploaded_by=seeded_doctor.id,
        status="COMPLETED",
        patient_id=None,  # the exact broken state: identity was never resolved
    )
    db_session.add(broken)
    db_session.add(
        KnowledgeRecord(
            id=new_uuid(),
            patient_id=None,
            record_type="document",
            source_type="UPLOADED_PDF",
            source_document_id=broken.id,
            source_page=1,
            source_section="document",
            sensitivity="clinical",
            content="Patient: Unknown\nDocument page 1\n\n" + page_text,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/documents/upload",
        files={"file": ("kavya_report.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == broken.id
    assert body["patient_id"] is not None

    db_session.expire_all()
    repaired_doc = db_session.query(SourceDocument).filter(SourceDocument.id == broken.id).first()
    assert repaired_doc.patient_id is not None

    kr = db_session.query(KnowledgeRecord).filter(KnowledgeRecord.source_document_id == broken.id).first()
    assert kr.patient_id == repaired_doc.patient_id

    assignment = (
        db_session.query(PatientAssignment)
        .filter(PatientAssignment.patient_id == repaired_doc.patient_id, PatientAssignment.user_id == seeded_doctor.id)
        .first()
    )
    assert assignment is not None
