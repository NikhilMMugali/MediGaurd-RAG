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


def test_upload_rejects_duplicate_file(client, seeded_doctor):
    """Same bytes uploaded twice must be rejected as a duplicate by hash,
    regardless of the filename used the second time. PyMuPDF stamps a fresh
    random document ID on every tobytes() call, so the identical-content
    bytes are generated once here and reused, rather than regenerated."""
    token = _login(client, seeded_doctor)
    headers = {"Authorization": f"Bearer {token}"}
    pdf_bytes = _make_pdf_bytes()

    first = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999_again.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert second.status_code == 409
