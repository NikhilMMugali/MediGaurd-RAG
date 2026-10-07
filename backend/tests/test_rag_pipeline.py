"""Tests app.rag.pipeline.run_query end-to-end against a real (temp, local)
Qdrant collection, with the embedding model and LLM call both swapped for
fast fakes via monkeypatch — the retrieval/authorization code under test is
100% real. This is the "security invariant" test from the Phase 3 spec:
it inspects what was actually handed to the LLM, not just the final answer
text, so a restricted record leaking into the prompt would be caught even
if the LLM happened to never mention it.
"""
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment
from app.services.vector_store import VectorStore
from tests.test_rag_authorization import FIXTURE_RECORDS, FakeEmbedder


@pytest.fixture()
def seeded_finance(db_session):
    from app.auth.security import hash_password

    user = User(username="finance01", full_name="Finance", hashed_password=hash_password("secret123"), role=RoleEnum.FINANCE)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(autouse=True)
def patched_rag_dependencies(monkeypatch, tmp_path):
    client = QdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(client, "test_collection")
    embedder = FakeEmbedder()
    store.ensure_collection(embedder.dimension)
    points = [PointStruct(id=new_uuid(), vector=embedder.embed_text(r["content"]), payload=r) for r in FIXTURE_RECORDS]
    store.upsert(points)

    captured_context: dict = {}

    class CapturingLLM:
        def generate(self, context_text: str, question: str) -> str:
            captured_context["text"] = context_text
            return "stub answer [SOURCE_1]"

    monkeypatch.setattr("app.rag.pipeline.get_embedding_provider", lambda: embedder)
    monkeypatch.setattr("app.rag.pipeline.get_vector_store", lambda: store)
    monkeypatch.setattr("app.rag.pipeline.get_llm_provider", lambda sources: CapturingLLM())
    return captured_context


def test_finance_query_never_sends_clinical_content_to_llm(db_session, seeded_finance, patched_rag_dependencies):
    from app.rag.pipeline import run_query

    result = run_query(db_session, seeded_finance, "What is patient-1's diagnosis and claim balance?")

    assert result.status == "ANSWERED"
    llm_context = patched_rag_dependencies.get("text", "")
    # The security invariant: restricted clinical content must never appear
    # in the text that was actually handed to the LLM, regardless of what
    # the LLM's own answer says.
    assert "Hypertension" not in llm_context
    assert "Diabetes" not in llm_context
    assert "claim balance" in llm_context


def test_doctor_denied_for_unassigned_patient_before_any_retrieval(db_session, seeded_doctor, patched_rag_dependencies):
    from app.rag.pipeline import run_query

    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    # Fixture ids ("patient-2") aren't UUID-shaped, so pass the id via the
    # explicit field rather than relying on the free-text UUID regex scan
    # (real Synthea ids are UUIDs and would be picked up from the question
    # text itself — see test_doctor_answered_for_assigned_patient's sibling
    # coverage in test_rag_authorization.py for the pure-filter version).
    result = run_query(db_session, seeded_doctor, "What is the diagnosis?", patient_id="patient-2")

    assert result.status == "DENIED"
    assert result.retrieved_count == 0
    assert "text" not in patched_rag_dependencies  # LLM was never even called


def test_doctor_answered_for_assigned_patient(db_session, seeded_doctor, patched_rag_dependencies):
    from app.rag.pipeline import run_query

    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    result = run_query(db_session, seeded_doctor, "What is the diagnosis for patient-1?")

    assert result.status == "ANSWERED"
    assert "Hypertension" in patched_rag_dependencies["text"]
    assert len(result.citations) > 0
