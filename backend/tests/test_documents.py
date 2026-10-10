"""Focused tests for Document Intelligence (section 12 "PDF ingestion" /
"Authorization" checklist): document-level authorization on the list,
status, and query endpoints, and that document-scoped Q&A never lets one
document's chunks answer a question scoped to another document. These never
touch the real on-disk Qdrant collection — see fake_vector_store below and
patched_rag_dependencies in test_rag_pipeline.py for why.
"""
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.auth.security import hash_password
from app.models.documents import SourceDocument
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment
from app.services.vector_store import VectorStore
from tests.test_rag_authorization import FakeEmbedder


@pytest.fixture(autouse=True)
def fake_vector_store(monkeypatch):
    class FakeStore:
        def count(self) -> int:
            return 0

    monkeypatch.setattr("app.services.vector_store.get_vector_store", lambda: FakeStore())


@pytest.fixture()
def seeded_nurse(db_session):
    user = User(username="nurse01", full_name="Nurse", hashed_password=hash_password("secret123"), role=RoleEnum.NURSE)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def seeded_finance(db_session):
    user = User(username="finance01", full_name="Finance", hashed_password=hash_password("secret123"), role=RoleEnum.FINANCE)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, username, password, role):
    response = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    return response.json()["access_token"]


def _seed_document(db_session, *, uploaded_by, patient_id, status="COMPLETED", storage_path=None):
    doc = SourceDocument(
        id=new_uuid(),
        file_name="report.pdf",
        file_hash=new_uuid(),
        source_type="UPLOADED_PDF",
        uploaded_by=uploaded_by,
        patient_id=patient_id,
        status=status,
        storage_path=storage_path,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_document_list_requires_doctor_nurse_or_admin(client, seeded_finance):
    token = _login(client, "finance01", "secret123", "FINANCE")
    response = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_document_list_shows_own_upload_even_if_patient_unassigned(client, db_session, seeded_doctor):
    _seed_document(db_session, uploaded_by=seeded_doctor.id, patient_id="patient-not-assigned")
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_document_list_hides_other_uploader_unassigned_patient_document(client, db_session, seeded_doctor, seeded_nurse):
    _seed_document(db_session, uploaded_by=seeded_nurse.id, patient_id="patient-not-assigned")
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_document_list_shows_assigned_patients_document_from_another_uploader(client, db_session, seeded_doctor, seeded_nurse):
    doc = _seed_document(db_session, uploaded_by=seeded_nurse.id, patient_id="patient-1")
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["documents"][0]["document_id"] == doc.id


def test_document_status_denied_for_unauthorized_viewer(client, db_session, seeded_doctor, seeded_nurse):
    doc = _seed_document(db_session, uploaded_by=seeded_nurse.id, patient_id="patient-not-assigned")
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get(f"/api/documents/{doc.id}/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_document_query_denied_before_any_retrieval_for_unauthorized_document(client, db_session, seeded_doctor, seeded_nurse):
    """The critical security property (section 5G/8): an unauthorized
    document_id must 403 at the authorization check, never fall through to
    run_query (and therefore never to Qdrant or the LLM)."""
    doc = _seed_document(db_session, uploaded_by=seeded_nurse.id, patient_id="patient-not-assigned")
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.post(
        "/api/documents/query",
        json={"document_id": doc.id, "question": "What medications are mentioned?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_document_query_unprocessed_document_returns_no_context_without_retrieval(client, db_session, seeded_doctor):
    doc = _seed_document(db_session, uploaded_by=seeded_doctor.id, patient_id=None, status="NEEDS_REVIEW")
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.post(
        "/api/documents/query",
        json={"document_id": doc.id, "question": "Summarize this report."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NO_AUTHORIZED_CONTEXT"


@pytest.fixture()
def two_document_store(tmp_path):
    """Two different documents' chunks for the SAME patient, so a passing
    test here genuinely proves document_id scoping — patient-level scoping
    alone would let both through."""
    client_ = QdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(client_, "test_collection")
    embedder = FakeEmbedder()
    store.ensure_collection(embedder.dimension)
    records = [
        {
            "knowledge_record_id": "kr-doc-a",
            "source_type": "UPLOADED_PDF",
            "source_document_id": "doc-a",
            "source_page": 1,
            "source_section": "medication",
            "patient_id": "patient-1",
            "record_type": "medication",
            "department_id": None,
            "sensitivity": "clinical",
            "content": "Patient patient-1 Medication: Metformin (from document A).",
        },
        {
            "knowledge_record_id": "kr-doc-b",
            "source_type": "UPLOADED_PDF",
            "source_document_id": "doc-b",
            "source_page": 1,
            "source_section": "medication",
            "patient_id": "patient-1",
            "record_type": "medication",
            "department_id": None,
            "sensitivity": "clinical",
            "content": "Patient patient-1 Medication: Lisinopril (from document B).",
        },
    ]
    points = [PointStruct(id=new_uuid(), vector=embedder.embed_text(r["content"]), payload=r) for r in records]
    store.upsert(points)
    return store, embedder


# ---- GET /api/documents/{document_id}/file — the authenticated file-
# serving endpoint behind the citation PDF viewer. No test touched this
# endpoint at all before this pass, despite it being exactly the kind of
# "guessing a document ID must not bypass authorization" security path the
# PDF-viewer feature's acceptance criteria call out.


@pytest.fixture()
def isolated_upload_dir(tmp_path, monkeypatch):
    """Points the file endpoint's upload_dir at a throwaway tmp directory
    instead of the real ./data/uploads, so this test never reads or writes
    real uploaded patient PDFs."""
    monkeypatch.setattr("app.api.upload.settings.upload_dir", str(tmp_path))
    return tmp_path


def _write_fake_pdf(upload_dir, document_id: str) -> str:
    storage_path = f"{document_id}.pdf"
    (upload_dir / storage_path).write_bytes(b"%PDF-1.4 fake pdf bytes for testing")
    return storage_path


def test_document_file_requires_doctor_nurse_or_admin(client, seeded_finance):
    token = _login(client, "finance01", "secret123", "FINANCE")
    response = client.get("/api/documents/some-doc-id/file", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_document_file_404_for_nonexistent_document_id(client, seeded_doctor):
    token = _login(client, "doctor01", "secret123", "DOCTOR")
    response = client.get("/api/documents/does-not-exist/file", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_document_file_denied_for_unauthorized_viewer(client, db_session, seeded_doctor, seeded_nurse, isolated_upload_dir):
    """The exact 'guessing a document ID' scenario from the PDF-viewer
    acceptance criteria: doctor01 knows a real document_id (e.g. from a
    citation shown to a different user, or simple enumeration) but is
    neither its uploader nor assigned to its patient — must 403, and must
    never reach FileResponse / the stored bytes."""
    storage_path = _write_fake_pdf(isolated_upload_dir, "secret-doc")
    doc = _seed_document(db_session, uploaded_by=seeded_nurse.id, patient_id="patient-not-assigned", storage_path=storage_path)
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get(f"/api/documents/{doc.id}/file", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_document_file_served_to_uploader(client, db_session, seeded_doctor, isolated_upload_dir):
    doc = _seed_document(db_session, uploaded_by=seeded_doctor.id, patient_id=None)
    storage_path = _write_fake_pdf(isolated_upload_dir, doc.id)
    doc.storage_path = storage_path
    db_session.commit()
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get(f"/api/documents/{doc.id}/file", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 fake pdf bytes for testing"


def test_document_file_served_to_assigned_clinician_even_if_uploaded_by_someone_else(
    client, db_session, seeded_doctor, seeded_nurse, isolated_upload_dir
):
    doc = _seed_document(db_session, uploaded_by=seeded_nurse.id, patient_id="patient-1")
    storage_path = _write_fake_pdf(isolated_upload_dir, doc.id)
    doc.storage_path = storage_path
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get(f"/api/documents/{doc.id}/file", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_document_file_rejects_storage_path_escaping_upload_dir(client, db_session, seeded_doctor, isolated_upload_dir, tmp_path):
    """A storage_path that traverses outside upload_dir (however it got
    there) must never be served — the endpoint resolves the path and
    checks it is still inside upload_dir before touching the filesystem."""
    outside_secret = tmp_path.parent / "outside-secret.pdf"
    outside_secret.write_bytes(b"should never be served")
    doc = _seed_document(db_session, uploaded_by=seeded_doctor.id, patient_id=None, storage_path="../outside-secret.pdf")
    token = _login(client, "doctor01", "secret123", "DOCTOR")

    response = client.get(f"/api/documents/{doc.id}/file", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_document_query_scopes_retrieval_to_the_named_document_only(db_session, seeded_doctor, two_document_store, monkeypatch):
    from app.rag.pipeline import run_query

    store, embedder = two_document_store
    captured: dict = {}

    class CapturingLLM:
        def generate(self, context_text: str, question: str) -> str:
            captured["text"] = context_text
            return "stub answer [SOURCE_1]"

    monkeypatch.setattr("app.rag.pipeline.get_embedding_provider", lambda: embedder)
    monkeypatch.setattr("app.rag.pipeline.get_vector_store", lambda: store)
    monkeypatch.setattr("app.rag.pipeline.get_llm_provider", lambda sources: CapturingLLM())

    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    # No explicit patient_id: this exercises the Qdrant-filter branch of
    # _semantic_retrieve (document_id is only meaningful there) rather than
    # the known-patient SQL fast path, which reads KnowledgeRecord rows this
    # fixture deliberately does not create — only Qdrant points.
    result = run_query(db_session, seeded_doctor, "What medication is mentioned?", document_id="doc-a")

    assert result.status == "ANSWERED"
    assert "Metformin" in captured["text"]
    assert "Lisinopril" not in captured["text"]
