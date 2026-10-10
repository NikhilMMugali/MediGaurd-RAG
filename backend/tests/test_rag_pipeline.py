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
    captured_context["store"] = store
    captured_context["embedder"] = embedder
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


# ---- Citation integrity (section 3/10: document_id, patient association,
# and page metadata must survive the API response correctly, and a
# structured (database) citation must never be confused with a PDF one).
# The frontend's PDF viewer (ChatMessage.tsx) gates purely on
# citation.document_id being non-null to decide whether a citation is
# openable — these tests lock in the backend half of that contract.


def test_structured_citation_has_no_document_id_for_synthea_native_fact(db_session, seeded_doctor, patched_rag_dependencies):
    """A fact answered from the structured fast path, sourced from a
    Synthea-native SQL row (never an uploaded PDF), must report
    document_id=None on its citation. If this were ever non-None, the
    frontend's citation click-handler would treat a pure database fact as
    openable, opening nothing or — worse — an unrelated document that
    happens to share that id."""
    from app.models.hospital import Condition, Patient
    from app.rag.pipeline import run_query

    patient = Patient(id=new_uuid(), first="Jordan", last="Rivera", display_id="P401")
    db_session.add(patient)
    db_session.add(Condition(id=new_uuid(), patient=patient.id, description="Essential hypertension (disorder)"))
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    result = run_query(db_session, seeded_doctor, "What conditions does this patient have?", patient_id=patient.id)

    assert result.status == "ANSWERED"
    assert "text" not in patched_rag_dependencies  # structured fast path never calls the LLM
    assert len(result.citations) == 1
    assert result.citations[0].document_id is None
    assert result.citations[0].page is None


def test_semantic_citation_preserves_document_id_page_and_evidence_text(db_session, seeded_doctor, patched_rag_dependencies):
    """The inverse case: a semantic (PDF-narrative) citation must carry the
    real document_id/page/evidence_text through to the API response
    unchanged — these are exactly the fields the PDF viewer and citation
    click-handler depend on to open the right document at the right page."""
    from app.models.documents import KnowledgeRecord
    from app.models.hospital import Patient
    from app.rag.pipeline import run_query
    from app.services.vector_store import VectorStore

    store, embedder = patched_rag_dependencies["store"], patched_rag_dependencies["embedder"]
    patient = Patient(id=new_uuid(), first="Priya", last="Nair", display_id="P402")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    record = KnowledgeRecord(
        id=new_uuid(),
        patient_id=patient.id,
        record_type="document",
        source_type="UPLOADED_PDF",
        source_document_id="doc-402",
        source_page=4,
        source_section="document",
        sensitivity="clinical",
        content="25-OH Vitamin D: 22 ng/mL (LOW), reference interval 30-100 ng/mL.",
    )
    db_session.add(record)
    db_session.commit()
    store.upsert([PointStruct(id=record.id, vector=embedder.embed_text(record.content), payload={})])

    result = run_query(db_session, seeded_doctor, "What was the vitamin D level?", patient_id=patient.id)

    assert result.status == "ANSWERED"
    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.document_id == "doc-402"
    assert citation.page == 4
    assert citation.evidence_text == record.content
    assert citation.patient_id == "P402"


def test_pdf_citation_carries_highlight_text_but_database_citation_does_not(db_session, seeded_doctor, patched_rag_dependencies, monkeypatch):
    """highlight_text is what the PDF viewer highlights. It must reach the
    API response for a PDF-narrative citation (a verbatim passage from that
    page) and must be None for a database-only citation."""
    from app.models.documents import KnowledgeRecord
    from app.models.hospital import Condition, Patient
    from app.rag.pipeline import run_query

    class RichAnswerLLM:
        def generate(self, context_text: str, question: str) -> str:
            return "The report shows 25-OH Vitamin D of 18 ng/mL, flagged LOW against 30 - 100 ng/mL [SOURCE_1]."

    monkeypatch.setattr("app.rag.pipeline.get_llm_provider", lambda sources: RichAnswerLLM())
    store, embedder = patched_rag_dependencies["store"], patched_rag_dependencies["embedder"]

    patient = Patient(id=new_uuid(), first="Asha", last="Menon", display_id="P403")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    page_text = "Patient: Unknown\nDocument page 3\n\nWBC Count\n6,200\n25-OH Vitamin D\n18\nng/mL\n30 - 100\nLOW\nFerritin\n42"
    record = KnowledgeRecord(
        id=new_uuid(), patient_id=patient.id, record_type="document", source_type="UPLOADED_PDF",
        source_document_id="doc-403", source_page=3, source_section="document", sensitivity="clinical", content=page_text,
    )
    db_session.add(record)
    db_session.add(Condition(id=new_uuid(), patient=patient.id, description="Essential hypertension (disorder)"))
    db_session.commit()
    store.upsert([PointStruct(id=record.id, vector=embedder.embed_text(page_text), payload={})])

    pdf_result = run_query(db_session, seeded_doctor, "What about his vitamin D result?", patient_id=patient.id)
    assert pdf_result.status == "ANSWERED"
    highlight = pdf_result.citations[0].highlight_text
    assert highlight is not None
    assert "25-OH Vitamin D" in highlight
    assert "Patient: Unknown" not in highlight
    assert all(line in page_text for line in highlight.split("\n"))

    db_result = run_query(db_session, seeded_doctor, "What conditions does this patient have?", patient_id=patient.id)
    assert db_result.citations[0].document_id is None
    assert db_result.citations[0].highlight_text is None
