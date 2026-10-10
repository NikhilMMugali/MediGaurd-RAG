"""OCR image upload: validation, extraction, identity, persistence, idempotency,
repair, and the secure RAG path over OCR text.

Two kinds of tests, on purpose:
  * pipeline-logic tests substitute a fast fake for the OCR engine only (so a
    specific text/confidence can be asserted precisely) while everything else —
    validation, preprocessing, storage, identity, chunking, indexing into a real
    temp Qdrant, retrieval, authorization — is the real code;
  * `real_ocr` tests run the actual RapidOCR engine on images rendered here, so
    "OCR works" is demonstrated on real pixels, not assumed.

No real patient data: every image is rendered from synthetic text.
"""
import io

import pytest
from PIL import Image, ImageDraw, ImageFont
from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList
from sqlalchemy import func

from app.auth.security import hash_password
from app.ingestion.ocr_engine import OcrLine, OcrResult
from app.models.documents import KnowledgeRecord, SourceDocument
from app.models.hospital import Condition, Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment
from app.services.vector_store import VectorStore
from tests.test_rag_authorization import FakeEmbedder

REPORT_LINES = [
    "LABORATORY REPORT",
    "Patient Name: Meera Krishnan",
    "Hemoglobin 13.8 g/dL 12.0 - 15.5 NORMAL",
    "25-OH Vitamin D 18 ng/mL 30 - 100 LOW",
    "Ferritin 42 ng/mL 15 - 150 NORMAL",
]


# ---------------------------------------------------------------- helpers ---
def render_png(lines: list[str], size=(1100, 520)) -> bytes:
    font = ImageFont.load_default(size=30)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    for i, text in enumerate(lines):
        draw.text((40, 30 + i * 80), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_user(db, username, role):
    user = User(username=username, full_name=username.title(), hashed_password=hash_password("secret123"), role=role)
    db.add(user)
    db.commit()
    return user


def login(client, username, role):
    response = client.post("/api/auth/login", json={"username": username, "password": "secret123", "role": role})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client, headers, data: bytes, name="report.png", patient_id=None, content_type="image/png"):
    form = {"patient_id": patient_id} if patient_id else None
    return client.post("/api/documents/upload-image", files={"file": (name, data, content_type)}, data=form, headers=headers)


def fake_ocr(monkeypatch, lines: list[str], confidence: float = 0.97):
    def _run(prepared):
        return OcrResult(
            lines=[OcrLine(text=t, confidence=confidence, box=[20.0, 20.0 + 40 * i, 700.0, 52.0 + 40 * i]) for i, t in enumerate(lines)],
            width=prepared.width,
            height=prepared.height,
        )

    monkeypatch.setattr("app.services.image_ingestion.run_ocr", _run)


_SHARED = {}  # the test harness shares ONE session between the request and the test


def doc_status(client, headers, document_id) -> dict:
    # Background processing committed through another session; drop this
    # session's cached rows so the read below sees them (a real request has
    # its own fresh session, so this is purely a harness concern).
    if _SHARED.get("db") is not None:
        _SHARED["db"].expire_all()
    response = client.get(f"/api/documents/{document_id}/status", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def ocr_records(db, document_id):
    db.expire_all()
    return db.query(KnowledgeRecord).filter(KnowledgeRecord.source_document_id == document_id).all()


# --------------------------------------------------------------- fixtures ---
@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path, db_session):
    _SHARED["db"] = db_session
    uploads = tmp_path / "uploads"
    monkeypatch.setattr("app.api.upload.settings.upload_dir", str(uploads))
    monkeypatch.setattr("app.api.image_upload.settings.upload_dir", str(uploads))

    qclient = QdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(qclient, "test_collection")
    embedder = FakeEmbedder()
    store.ensure_collection(embedder.dimension)
    for target in ("app.services.image_ingestion", "app.rag.pipeline", "app.api.upload"):
        monkeypatch.setattr(f"{target}.get_vector_store", lambda: store)
        monkeypatch.setattr(f"{target}.get_embedding_provider", lambda: embedder)

    captured: dict = {}

    class CapturingLLM:
        answer = "The Vitamin D result is 18 ng/mL, flagged LOW [SOURCE_1]."

        def generate(self, context_text: str, question: str) -> str:
            captured["context"] = context_text
            captured["question"] = question
            return self.answer

    llm = CapturingLLM()
    monkeypatch.setattr("app.rag.pipeline.get_llm_provider", lambda sources: llm)
    return {"store": store, "uploads": uploads, "captured": captured, "llm": llm}


@pytest.fixture()
def nurse(db_session):
    return make_user(db_session, "nurse01", RoleEnum.NURSE)


@pytest.fixture()
def second_doctor(db_session):
    return make_user(db_session, "doctor02", RoleEnum.DOCTOR)


@pytest.fixture()
def finance(db_session):
    return make_user(db_session, "finance01", RoleEnum.FINANCE)


@pytest.fixture()
def reception(db_session):
    return make_user(db_session, "reception01", RoleEnum.RECEPTION)


@pytest.fixture()
def admin(db_session):
    return make_user(db_session, "admin01", RoleEnum.ADMIN)


def new_patient_via_upload(client, db_session, monkeypatch, doctor_headers, lines=REPORT_LINES, name="report.png"):
    fake_ocr(monkeypatch, lines)
    response = upload(client, doctor_headers, render_png(lines), name=name)
    assert response.status_code == 200, response.text
    return response.json()


# ============================================================ UPLOAD / VALIDATION
def test_valid_image_is_stored_ocred_identified_indexed_and_ready(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    headers = login(client, "doctor01", "DOCTOR")
    body = new_patient_via_upload(client, db_session, monkeypatch, headers)

    assert body["status"] == "VALIDATING"  # truthful: the response returns before OCR finishes
    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "COMPLETED"
    assert status["source_type"] == "OCR_IMAGE"
    assert status["ocr_quality"] == "good"
    assert status["page_count"] == 1
    assert status["patient_id"].startswith("P")

    doc = db_session.query(SourceDocument).filter(SourceDocument.id == body["document_id"]).one()
    assert (isolated_env["uploads"] / doc.storage_path).is_file()  # original persisted
    assert (isolated_env["uploads"] / f"{doc.id}.ocr.json").is_file()  # OCR result persisted

    records = ocr_records(db_session, doc.id)
    assert records and all(r.source_type == "OCR_IMAGE" and r.record_type == "document" and r.source_page == 1 for r in records)
    assert all(r.patient_id == doc.patient_id for r in records)
    assert "13.8 g/dL" in "\n".join(r.content for r in records)
    assert isolated_env["store"].count() == len(records)  # indexed AND readable back


@pytest.mark.parametrize(
    "name,data,content_type,expected",
    [
        ("notes.txt", b"plain text", "text/plain", 400),
        ("scan.gif", b"GIF89a" + b"\x00" * 40, "image/gif", 400),
        ("report.pdf", b"%PDF-1.4 x", "application/pdf", 400),
        ("empty.png", b"", "image/png", 422),
        ("fake.png", b"this is not an image at all", "image/png", 422),
    ],
)
def test_unsupported_empty_and_unreadable_files_are_rejected(client, seeded_doctor, name, data, content_type, expected):
    headers = login(client, "doctor01", "DOCTOR")
    assert upload(client, headers, data, name=name, content_type=content_type).status_code == expected


def test_gif_content_with_an_image_extension_is_rejected_by_content_not_name(client, seeded_doctor):
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, format="GIF")
    headers = login(client, "doctor01", "DOCTOR")
    assert upload(client, headers, buf.getvalue(), name="looks_ok.png").status_code == 400


def test_oversized_file_is_rejected(client, seeded_doctor, monkeypatch):
    monkeypatch.setattr("app.api.image_upload.settings.max_upload_size_mb", 0)
    headers = login(client, "doctor01", "DOCTOR")
    response = upload(client, headers, render_png(REPORT_LINES))
    assert response.status_code == 400 and "limit" in response.json()["detail"]


def test_decompression_bomb_sized_image_is_rejected_before_decoding(client, seeded_doctor, monkeypatch):
    monkeypatch.setattr("app.api.image_upload.settings.ocr_max_image_pixels", 10_000)
    headers = login(client, "doctor01", "DOCTOR")
    response = upload(client, headers, render_png(REPORT_LINES))
    assert response.status_code == 422 and "too large" in response.json()["detail"]


def test_upload_requires_authentication_and_a_clinical_role(client, seeded_doctor, finance, reception):
    data = render_png(REPORT_LINES)
    assert client.post("/api/documents/upload-image", files={"file": ("r.png", data, "image/png")}).status_code == 401
    for username, role in (("finance01", "FINANCE"), ("reception01", "RECEPTION")):
        assert upload(client, login(client, username, role), data).status_code == 403


def test_path_traversal_in_the_upload_filename_is_neutralised(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    headers = login(client, "doctor01", "DOCTOR")
    fake_ocr(monkeypatch, REPORT_LINES)
    body = upload(client, headers, render_png(REPORT_LINES), name="../../etc/passwd.png").json()
    doc = db_session.query(SourceDocument).filter(SourceDocument.id == body["document_id"]).one()
    assert doc.file_name == "passwd.png"
    assert (isolated_env["uploads"] / doc.storage_path).resolve().parent == isolated_env["uploads"].resolve()


# ============================================================== REAL OCR
@pytest.mark.real_ocr
def test_real_ocr_reads_a_rendered_report_and_makes_it_searchable(client, db_session, seeded_doctor, isolated_env):
    """No fake: the actual OCR engine reads actual pixels."""
    headers = login(client, "doctor01", "DOCTOR")
    body = upload(client, headers, render_png(REPORT_LINES)).json()
    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "COMPLETED", status

    ocr = client.get(f"/api/documents/{body['document_id']}/ocr", headers=headers).json()
    text = ocr["text"]
    # Values, units and the flag survive OCR exactly.
    for needle in ("13.8", "g/dL", "18", "ng/mL", "LOW", "Meera Krishnan"):
        assert needle in text, (needle, text)
    assert ocr["quality"] in ("good", "fair") and ocr["mean_confidence"] > 0.8
    assert all(len(line["box"]) == 4 and line["box"][2] > line["box"][0] for line in ocr["lines"])
    assert ocr["width"] == 1100 and ocr["height"] == 520

    patient = db_session.query(Patient).filter(Patient.id == db_session.query(SourceDocument).one().patient_id).one()
    assert (patient.first, patient.last) == ("Meera", "Krishnan")  # identity read from the pixels


@pytest.mark.real_ocr
def test_real_ocr_on_a_blank_image_is_sent_to_review_not_reported_as_success(client, db_session, seeded_doctor, isolated_env):
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(buf, format="PNG")
    headers = login(client, "doctor01", "DOCTOR")
    body = upload(client, headers, buf.getvalue(), name="blank.png").json()

    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "NEEDS_REVIEW"
    assert "little text" in status["error_message"]
    assert ocr_records(db_session, body["document_id"]) == []  # nothing indexed from garbage
    assert isolated_env["store"].count() == 0


@pytest.mark.real_ocr
def test_real_ocr_survives_a_rotated_exif_photo(client, db_session, seeded_doctor, isolated_env):
    """A phone photo stores pixels sideways and an EXIF orientation tag; the
    text must still be read in its displayed orientation."""
    upright = Image.open(io.BytesIO(render_png(REPORT_LINES)))
    sideways = upright.rotate(90, expand=True)  # pixels stored rotated
    exif = Image.Exif()
    exif[0x0112] = 8  # displayed rotated back by 90deg CCW-> upright
    buf = io.BytesIO()
    sideways.save(buf, format="JPEG", exif=exif.tobytes(), quality=95)
    headers = login(client, "doctor01", "DOCTOR")
    body = upload(client, headers, buf.getvalue(), name="photo.jpg", content_type="image/jpeg").json()
    ocr = client.get(f"/api/documents/{body['document_id']}/ocr", headers=headers).json()
    assert "Vitamin D" in ocr["text"] and "18" in ocr["text"]
    assert (ocr["width"], ocr["height"]) == (1100, 520)  # display orientation, not stored pixels


# ======================================================= IDENTITY AND ASSIGNMENT
def test_brand_new_patient_is_created_and_only_the_uploader_is_assigned(client, db_session, seeded_doctor, second_doctor, monkeypatch):
    headers = login(client, "doctor01", "DOCTOR")
    body = new_patient_via_upload(client, db_session, monkeypatch, headers)
    db_session.expire_all()
    doc = db_session.query(SourceDocument).one()
    assignments = db_session.query(PatientAssignment).filter(PatientAssignment.patient_id == doc.patient_id).all()
    assert [a.user_id for a in assignments] == [seeded_doctor.id]  # not every doctor
    other = login(client, "doctor02", "DOCTOR")
    assert client.get(f"/api/documents/{body['document_id']}/status", headers=other).status_code == 403


def test_existing_patient_is_matched_case_insensitively_without_creating_a_duplicate(client, db_session, seeded_doctor, monkeypatch):
    patient = Patient(id=new_uuid(), first="Meera", last="Krishnan", display_id="P007")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "doctor01", "DOCTOR")
    body = new_patient_via_upload(client, db_session, monkeypatch, headers, lines=["Patient Name: MEERA  KRISHNAN", "Hemoglobin 13.8 g/dL"])

    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "COMPLETED" and status["patient_id"] == "P007"
    assert db_session.query(func.count(Patient.id)).scalar() == 1


def test_a_near_miss_name_goes_to_review_instead_of_creating_a_duplicate_patient(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    patient = Patient(id=new_uuid(), first="Meera", last="Krishnan", display_id="P007")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "doctor01", "DOCTOR")
    # OCR misread: "Krishnan" -> "Krishnon"
    body = new_patient_via_upload(client, db_session, monkeypatch, headers, lines=["Patient Name: Meera Krishnon", "Hemoglobin 13.8 g/dL"])

    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "NEEDS_REVIEW" and "P007" in status["error_message"]
    assert db_session.query(func.count(Patient.id)).scalar() == 1  # no duplicate
    assert ocr_records(db_session, body["document_id"]) == [] and isolated_env["store"].count() == 0


def test_review_can_be_resolved_by_confirming_the_patient_and_then_indexes(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    patient = Patient(id=new_uuid(), first="Meera", last="Krishnan", display_id="P007")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "doctor01", "DOCTOR")
    body = new_patient_via_upload(client, db_session, monkeypatch, headers, lines=["Patient Name: Meera Krishnon", "Hemoglobin 13.8 g/dL"])
    assert doc_status(client, headers, body["document_id"])["status"] == "NEEDS_REVIEW"

    confirmed = client.post(f"/api/documents/{body['document_id']}/confirm-patient", json={"patient_id": "P007"}, headers=headers)
    assert confirmed.status_code == 200
    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "COMPLETED" and status["patient_id"] == "P007"
    assert len(ocr_records(db_session, body["document_id"])) >= 1 and isolated_env["store"].count() >= 1


def test_confirming_requires_access_to_the_target_patient(client, db_session, seeded_doctor, monkeypatch):
    other = Patient(id=new_uuid(), first="Someone", last="Else", display_id="P008")
    db_session.add(other)
    db_session.commit()  # seeded_doctor is NOT assigned to P008
    headers = login(client, "doctor01", "DOCTOR")
    body = new_patient_via_upload(client, db_session, monkeypatch, headers, lines=["no name here at all", "Hemoglobin 13.8 g/dL"])
    assert doc_status(client, headers, body["document_id"])["status"] == "NEEDS_REVIEW"
    assert client.post(f"/api/documents/{body['document_id']}/confirm-patient", json={"patient_id": "P008"}, headers=headers).status_code == 403


def test_image_naming_a_patient_the_uploader_may_not_access_is_reviewed_without_revealing_who(client, db_session, seeded_doctor, nurse, monkeypatch):
    patient = Patient(id=new_uuid(), first="Meera", last="Krishnan", display_id="P007")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=nurse.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "doctor01", "DOCTOR")  # not assigned to P007
    body = new_patient_via_upload(client, db_session, monkeypatch, headers)

    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "NEEDS_REVIEW"
    assert "P007" not in status["error_message"] and status["patient_id"] is None
    db_session.expire_all()
    assert db_session.query(SourceDocument).one().patient_id is None  # never attached to someone else's chart


def test_admin_may_attach_an_image_to_any_existing_patient(client, db_session, admin, nurse, monkeypatch):
    patient = Patient(id=new_uuid(), first="Meera", last="Krishnan", display_id="P007")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=nurse.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "admin01", "ADMIN")
    body = new_patient_via_upload(client, db_session, monkeypatch, headers)
    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "COMPLETED" and status["patient_id"] == "P007"


def test_explicit_patient_selection_is_authorized_by_the_server(client, db_session, seeded_doctor, monkeypatch):
    mine = Patient(id=new_uuid(), first="Meera", last="Krishnan", display_id="P007")
    theirs = Patient(id=new_uuid(), first="Other", last="Person", display_id="P008")
    db_session.add_all([mine, theirs])
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=mine.id, user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "doctor01", "DOCTOR")
    fake_ocr(monkeypatch, REPORT_LINES)
    data = render_png(REPORT_LINES)

    assert upload(client, headers, data, patient_id="P008").status_code == 403
    assert upload(client, headers, data, patient_id="P999").status_code == 404
    ok = upload(client, headers, data, patient_id="P007")
    assert ok.status_code == 200 and doc_status(client, headers, ok.json()["document_id"])["patient_id"] == "P007"


def test_explicit_patient_whose_name_contradicts_the_image_is_held_for_review(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    wrong = Patient(id=new_uuid(), first="Totally", last="Different", display_id="P009")
    db_session.add(wrong)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=wrong.id, user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    headers = login(client, "doctor01", "DOCTOR")
    fake_ocr(monkeypatch, REPORT_LINES)
    body = upload(client, headers, render_png(REPORT_LINES), patient_id="P009").json()

    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "NEEDS_REVIEW" and "does not match the selected patient" in status["error_message"]
    assert isolated_env["store"].count() == 0  # not filed under the wrong chart

    assert client.post(f"/api/documents/{body['document_id']}/confirm-patient", json={"patient_id": "P009"}, headers=headers).status_code == 200
    assert doc_status(client, headers, body["document_id"])["status"] == "COMPLETED"


def test_display_ids_never_collide_past_p999(db_session):
    from app.ingestion.pdf_mapper import _next_display_id

    for display in ("P007", "P999", "P1000"):
        db_session.add(Patient(id=new_uuid(), first="A", last="B", display_id=display))
    db_session.commit()
    assert _next_display_id(db_session) == "P1001"


# =========================================================== LOW-QUALITY OCR
def test_low_confidence_ocr_is_not_indexed_and_the_user_is_told_why(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    fake_ocr(monkeypatch, REPORT_LINES, confidence=0.30)
    headers = login(client, "doctor01", "DOCTOR")
    body = upload(client, headers, render_png(REPORT_LINES)).json()

    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "NEEDS_REVIEW" and status["ocr_quality"] == "poor"
    assert "low confidence" in status["error_message"]
    assert ocr_records(db_session, body["document_id"]) == [] and isolated_env["store"].count() == 0
    # The text is still viewable so a person can judge it.
    assert client.get(f"/api/documents/{body['document_id']}/ocr", headers=headers).json()["problem"]
    # Confirming a patient cannot launder unreadable text into the index.
    assert client.post(f"/api/documents/{body['document_id']}/confirm-patient", json={"patient_id": "P001"}, headers=headers).status_code in (404, 409)


def test_fair_quality_ocr_is_indexed_with_a_visible_caveat(client, db_session, seeded_doctor, monkeypatch):
    fake_ocr(monkeypatch, REPORT_LINES, confidence=0.70)
    headers = login(client, "doctor01", "DOCTOR")
    body = upload(client, headers, render_png(REPORT_LINES)).json()
    status = doc_status(client, headers, body["document_id"])
    assert status["status"] == "COMPLETED" and status["ocr_quality"] == "fair"
    assert "confidence" in status["error_message"]


# =================================================== IDEMPOTENCY AND REPAIR
def test_duplicate_upload_is_idempotent(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    headers = login(client, "doctor01", "DOCTOR")
    data = render_png(REPORT_LINES)
    fake_ocr(monkeypatch, REPORT_LINES)
    first = upload(client, headers, data).json()
    records_before = len(ocr_records(db_session, first["document_id"]))
    vectors_before = isolated_env["store"].count()

    second = upload(client, headers, data).json()
    assert second["document_id"] == first["document_id"] and second["duplicate"] is True
    assert second["status"] == "COMPLETED" and "already uploaded and is ready" in second["message"]
    assert len(ocr_records(db_session, first["document_id"])) == records_before
    assert isolated_env["store"].count() == vectors_before
    assert db_session.query(func.count(Patient.id)).scalar() == 1
    assert db_session.query(func.count(SourceDocument.id)).scalar() == 1
    assert db_session.query(func.count(PatientAssignment.id)).scalar() == 1


def test_a_failed_indexing_attempt_is_repaired_by_reupload_without_duplicates(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    headers = login(client, "doctor01", "DOCTOR")
    data = render_png(REPORT_LINES)
    fake_ocr(monkeypatch, REPORT_LINES)

    def boom(*args, **kwargs):
        raise RuntimeError("qdrant unavailable")

    with monkeypatch.context() as scoped:  # real indexing is restored when the block exits
        scoped.setattr("app.services.image_ingestion.index_records", boom)
        first = upload(client, headers, data).json()
        assert doc_status(client, headers, first["document_id"])["status"] == "FAILED"  # honest, not "completed"
    assert isolated_env["store"].count() == 0
    created = len(ocr_records(db_session, first["document_id"]))
    assert created >= 1  # the chunks exist in SQL, just not searchable yet

    again = upload(client, headers, data).json()
    assert again["duplicate"] is True and "repairing" in again["message"]
    assert doc_status(client, headers, first["document_id"])["status"] == "COMPLETED"
    assert len(ocr_records(db_session, first["document_id"])) == created  # no duplicate chunks
    assert isolated_env["store"].count() == created
    assert db_session.query(func.count(Patient.id)).scalar() == 1


def test_reupload_repairs_a_document_whose_vectors_are_missing(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    headers = login(client, "doctor01", "DOCTOR")
    data = render_png(REPORT_LINES)
    fake_ocr(monkeypatch, REPORT_LINES)
    first = upload(client, headers, data).json()
    records = ocr_records(db_session, first["document_id"])
    store = isolated_env["store"]
    store.client.delete(collection_name=store.collection, points_selector=PointIdsList(points=[r.id for r in records]))
    assert store.count() == 0  # the DB says "completed" but nothing is searchable

    again = upload(client, headers, data).json()
    assert again["duplicate"] is True and "repairing" in again["message"]
    assert doc_status(client, headers, first["document_id"])["status"] == "COMPLETED"
    assert store.count() == len(records)  # restored, same ids, no duplicates
    assert len(ocr_records(db_session, first["document_id"])) == len(records)


def test_reupload_rewrites_a_lost_image_file_and_keeps_the_stored_ocr(client, db_session, seeded_doctor, monkeypatch, isolated_env):
    headers = login(client, "doctor01", "DOCTOR")
    data = render_png(REPORT_LINES)
    fake_ocr(monkeypatch, REPORT_LINES)
    first = upload(client, headers, data).json()
    doc = db_session.query(SourceDocument).one()
    (isolated_env["uploads"] / doc.storage_path).unlink()

    again = upload(client, headers, data).json()
    assert again["duplicate"] is True
    assert (isolated_env["uploads"] / doc.storage_path).read_bytes() == data
    assert doc_status(client, headers, first["document_id"])["status"] == "COMPLETED"


def test_duplicate_of_a_low_quality_image_reports_the_review_reason_instead_of_reprocessing(client, seeded_doctor, monkeypatch):
    fake_ocr(monkeypatch, REPORT_LINES, confidence=0.2)
    headers = login(client, "doctor01", "DOCTOR")
    data = render_png(REPORT_LINES)
    upload(client, headers, data)
    again = upload(client, headers, data).json()
    assert again["status"] == "NEEDS_REVIEW" and again["duplicate"] is True


def test_another_users_duplicate_cannot_be_opened_by_re_uploading_the_same_bytes(client, db_session, seeded_doctor, second_doctor, monkeypatch):
    fake_ocr(monkeypatch, REPORT_LINES)
    data = render_png(REPORT_LINES)
    upload(client, login(client, "doctor01", "DOCTOR"), data)
    assert upload(client, login(client, "doctor02", "DOCTOR"), data).status_code == 403


# ===================================================== SERVING THE ORIGINAL IMAGE
def test_authorized_user_can_fetch_the_original_image_with_safe_headers(client, db_session, seeded_doctor, monkeypatch):
    headers = login(client, "doctor01", "DOCTOR")
    data = render_png(REPORT_LINES)
    fake_ocr(monkeypatch, REPORT_LINES)
    body = upload(client, headers, data).json()
    response = client.get(f"/api/documents/{body['document_id']}/file", headers=headers)
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_unauthorized_users_cannot_open_the_image_its_text_or_its_status(client, db_session, seeded_doctor, second_doctor, nurse, finance, reception, monkeypatch):
    fake_ocr(monkeypatch, REPORT_LINES)
    body = upload(client, login(client, "doctor01", "DOCTOR"), render_png(REPORT_LINES)).json()
    doc_id = body["document_id"]
    for username, role in (("doctor02", "DOCTOR"), ("nurse01", "NURSE")):
        headers = login(client, username, role)
        for path in ("file", "ocr", "status"):
            assert client.get(f"/api/documents/{doc_id}/{path}", headers=headers).status_code == 403, (username, path)
    for username, role in (("finance01", "FINANCE"), ("reception01", "RECEPTION")):
        headers = login(client, username, role)
        for path in ("file", "ocr", "status"):
            assert client.get(f"/api/documents/{doc_id}/{path}", headers=headers).status_code == 403, (username, path)
    assert client.get(f"/api/documents/{doc_id}/file").status_code == 401


def test_a_nurse_assigned_to_the_patient_can_view_it_and_admin_always_can(client, db_session, seeded_doctor, nurse, admin, monkeypatch):
    fake_ocr(monkeypatch, REPORT_LINES)
    body = upload(client, login(client, "doctor01", "DOCTOR"), render_png(REPORT_LINES)).json()
    db_session.expire_all()
    patient_id = db_session.query(SourceDocument).one().patient_id
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient_id, user_id=nurse.id, assignment_type="nursing"))
    db_session.commit()
    for username, role in (("nurse01", "NURSE"), ("admin01", "ADMIN")):
        assert client.get(f"/api/documents/{body['document_id']}/file", headers=login(client, username, role)).status_code == 200


def test_ocr_endpoints_do_not_serve_pdf_documents(client, db_session, seeded_doctor):
    doc = SourceDocument(id=new_uuid(), file_name="x.pdf", file_hash="h", source_type="UPLOADED_PDF", uploaded_by=seeded_doctor.id, status="COMPLETED")
    db_session.add(doc)
    db_session.commit()
    assert client.get(f"/api/documents/{doc.id}/ocr", headers=login(client, "doctor01", "DOCTOR")).status_code == 404
