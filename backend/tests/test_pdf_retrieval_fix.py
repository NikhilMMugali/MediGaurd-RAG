"""Regression tests for the PDF retrieval bug reported against a real
uploaded lab report: upload "succeeded" but the document was completely
unretrievable (zero knowledge records), the patient's name got garbled by a
multi-field header line, free-text name questions never resolved to any
patient at all, and an unscoped semantic search then surfaced unrelated
patients' records as if they were relevant sources. See
progress/DECISIONS.md "PDF retrieval fix" for the full root-cause writeup.
"""
import hashlib

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.ingestion.pdf_mapper import extract_patient_document_data
from app.models.hospital import Patient
from app.models.provenance import new_uuid
from app.models.ward import PatientAssignment
from app.rag.pipeline import _resolve_patient_by_name
from app.schemas.ingestion import ExtractedPage, PdfExtractionResult
from app.services.vector_store import VectorStore

# A real-world lab-report header, with two Label:Value fields packed onto
# one physical line — this is what the simple per-line parser mangles.
_LAB_REPORT_PAGE_TEXT = (
    "Name : RAMESH SHAH Reg. No. : 50000000099\n"
    "Age : 40 Years Gender Male\n"
    "Ref. By : Reported Date : 13-Aug-2025 14:44\n"
    "TEST REPORT\n"
    "HAEMOGRAM REPORT\n"
    "Test Name Results Units Bio. Ref. Interval\n"
    "Hemoglobin: 14.5 gm% 13.0 - 17.0\n"
    "TSH (Thyroid stimulating hormone) L 0.675 uIU/mL 0.7 - 6.4\n"
)


def _extraction_result(text: str) -> PdfExtractionResult:
    return PdfExtractionResult(
        file_name="lab_report.pdf",
        file_hash="irrelevant",
        page_count=1,
        is_text_extractable=True,
        pages=[ExtractedPage(page_number=1, text=text, has_tables=True)],
    )


def test_identity_fallback_recovers_clean_name_from_packed_header_line():
    """The naive per-line parser would capture "RAMESH SHAH Reg. No. :
    50000000099" as the whole "name" (everything to end of line) — this
    must come out as just "RAMESH SHAH"."""
    data = extract_patient_document_data(_extraction_result(_LAB_REPORT_PAGE_TEXT))

    assert data.patient is not None
    assert data.patient.first == "RAMESH"
    assert data.patient.last == "SHAH"
    assert data.patient.external_patient_id == "50000000099"
    assert data.patient.gender == "Male"


def test_narrative_section_created_even_with_zero_structured_fields():
    """A lab report has no "Diagnosis:"/"Medication:" style lines at all —
    the structured lists stay empty, but the page's own text must still be
    kept as a narrative knowledge record, or the document is permanently
    unretrievable despite a successful-looking upload."""
    data = extract_patient_document_data(_extraction_result(_LAB_REPORT_PAGE_TEXT))

    assert data.conditions == []
    assert data.medications == []
    assert len(data.narrative_sections) == 1
    assert "Hemoglobin" in data.narrative_sections[0].content
    assert data.narrative_sections[0].source_page == 1


# The actual real-world layout that reproduced a second, distinct failure:
# a bare label on its own line with no colon at all, value on the very next
# line (common PDF form/table export) — the two colon-anchored strategies
# above never match this at all. Content matches the real reported fixture's
# structure (fictional synthetic test data, as the source PDF itself states).
_FORM_LAYOUT_PAGE_TEXT = (
    "SYNTHETIC TEST DATA - NOT A REAL PATIENT - NOT FOR CLINICAL USE\n"
    "Patient Name\n"
    "KAVYA DEMO PATIENT\n"
    "Demo Patient ID\n"
    "DEMO-PT-2026-1042\n"
    "Age\n"
    "29 years\n"
    "Gender\n"
    "Female\n"
    "Complete Blood Count (CBC)\n"
    "Hemoglobin 13.8 g/dL 12.0 - 16.0 NORMAL\n"
)


def test_label_next_line_fallback_recovers_identity_with_no_colon_at_all():
    """Neither the naive per-line parser nor `_extract_identity_fallback`
    have anything to anchor on here — there's no colon anywhere near the
    identity fields. This is the third, final fallback tier."""
    data = extract_patient_document_data(_extraction_result(_FORM_LAYOUT_PAGE_TEXT))

    assert data.patient is not None
    assert data.patient.first == "KAVYA"
    assert data.patient.last == "DEMO PATIENT"
    assert data.patient.external_patient_id == "DEMO-PT-2026-1042"
    assert data.patient.gender == "Female"
    assert len(data.narrative_sections) == 1


def test_resolve_patient_by_name_matches_exact_normalized_full_name(db_session):
    db_session.add(Patient(id=new_uuid(), first="Sunita", last="Mehta", display_id="P201"))
    db_session.add(Patient(id=new_uuid(), first="Ramesh", last="Shah", display_id="P202"))
    db_session.commit()

    resolved = _resolve_patient_by_name(db_session, "Can you tell me about Sunita Mehta please?")
    patient = db_session.query(Patient).filter(Patient.id == resolved).first()
    assert patient is not None
    assert patient.display_id == "P201"


def test_resolve_patient_by_name_returns_none_for_no_match(db_session):
    db_session.add(Patient(id=new_uuid(), first="Sunita", last="Mehta", display_id="P201"))
    db_session.commit()

    assert _resolve_patient_by_name(db_session, "Tell me about Nobody Here") is None


def _unit_vector(dim: int, hot_index: int, secondary: float = 0.0) -> list[float]:
    """A hand-built vector with a known, controllable cosine similarity to
    the all-ones query vector below — deliberately not routed through
    FakeEmbedder, whose hash-derived vectors have no real semantic meaning
    and can't demonstrate "unrelated content scores low" one way or the
    other. This isolates exactly the property under test: does
    VectorStore.search() actually apply score_threshold at all (the bug was
    `score_threshold or None` silently discarding a configured 0.0)."""
    vec = [0.0] * dim
    vec[hot_index] = 1.0 - secondary
    vec[(hot_index + 1) % dim] = secondary
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


@pytest.fixture()
def relevance_fixture_store(tmp_path):
    client = QdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(client, "test_collection")
    store.ensure_collection(8)

    # cosine(query, relevant) is high (~0.90); cosine(query, unrelated) is
    # low (~0.125) — comfortably on either side of the configured 0.35 floor.
    query_vector = _unit_vector(8, hot_index=0, secondary=0.0)
    relevant = {"knowledge_record_id": "kr-relevant", "content": "relevant"}
    unrelated = {"knowledge_record_id": "kr-unrelated", "content": "unrelated"}
    store.upsert(
        [
            PointStruct(id=new_uuid(), vector=_unit_vector(8, hot_index=0, secondary=0.1), payload=relevant),
            PointStruct(id=new_uuid(), vector=_unit_vector(8, hot_index=4, secondary=0.0), payload=unrelated),
        ]
    )
    return store, query_vector


def test_weak_semantic_match_is_excluded_by_relevance_threshold(relevance_fixture_store):
    """The actual reported-bug symptom: a record that scores far below any
    reasonable relevance bar must not be surfaced as a "source" just because
    it was the nearest thing in an otherwise-sparse collection. This is also
    the regression test for the `score_threshold or None` bug — a
    configured 0.0 threshold used to be silently discarded as "no filter"
    regardless of what RAG_SCORE_THRESHOLD was actually set to."""
    from app.config import get_settings

    store, query_vector = relevance_fixture_store
    settings = get_settings()

    unfiltered = store.search(query_vector, None, limit=5, score_threshold=None)
    assert len(unfiltered) == 2

    filtered = store.search(query_vector, None, limit=5, score_threshold=settings.rag_score_threshold)
    assert [hit.payload["knowledge_record_id"] for hit in filtered] == ["kr-relevant"]


def test_known_patient_fast_path_has_no_relevance_floor(db_session, seeded_doctor, tmp_path, monkeypatch):
    """Regression for a second-order bug introduced by the fix above: the
    relevance floor was *also* applied to the known-patient SQL fast path,
    where it isn't a security boundary at all (every candidate there is
    already scoped to the right patient_id AND record_type by SQL) — it
    just discarded correct, authorized answers whenever a coarse whole-page
    narrative chunk's broad content diluted its cosine similarity to a
    short, specific question below the configured floor. Reproduced live
    against the real reported document ("Which value is flagged LOW..."
    scored below 0.35 against its own correct page). The floor must stay
    removed from this path; it still applies on the unscoped cross-patient
    search path (test_weak_semantic_match_is_excluded_by_relevance_threshold
    above) where it's the actual fix for the actual reported bug.

    Uses hand-built, orthogonal-ish vectors (cosine ~0.125, well under the
    configured 0.35 floor) rather than a hash-based fake embedder, so this
    test actually proves the floor is gone — a hash-based vector's
    similarity to an unrelated query is arbitrary, not guaranteed low, and
    could pass even with the floor still in place."""
    from app.config import get_settings
    from app.models.documents import KnowledgeRecord
    from app.rag.pipeline import run_query

    settings = get_settings()
    client = QdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(client, "test_collection")
    store.ensure_collection(8)

    patient = Patient(id=new_uuid(), first="Kavya", last="Demo Patient", display_id="P301")
    db_session.add(patient)
    db_session.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=seeded_doctor.id, assignment_type="attending"))
    record = KnowledgeRecord(
        id=new_uuid(),
        patient_id=patient.id,
        record_type="document",
        source_type="UPLOADED_PDF",
        source_page=3,
        source_section="document",
        sensitivity="clinical",
        content="Whole-page narrative chunk covering CBC, chemistry, thyroid, and vitamin panels in one block.",
    )
    db_session.add(record)
    db_session.commit()

    query_vector = _unit_vector(8, hot_index=0, secondary=0.0)
    record_vector = _unit_vector(8, hot_index=4, secondary=0.0)  # cosine ~0.125 — well below 0.35
    store.upsert([PointStruct(id=record.id, vector=record_vector, payload={})])

    class _FixedVectorEmbedder:
        dimension = 8

        def embed_text(self, text: str) -> list[float]:
            return query_vector

    class _StubLLM:
        def generate(self, context_text: str, question: str) -> str:
            return "stub answer [SOURCE_1]"

    monkeypatch.setattr("app.rag.pipeline.get_embedding_provider", lambda: _FixedVectorEmbedder())
    monkeypatch.setattr("app.rag.pipeline.get_vector_store", lambda: store)
    monkeypatch.setattr("app.rag.pipeline.get_llm_provider", lambda sources: _StubLLM())

    result = run_query(db_session, seeded_doctor, "Which specific value was flagged outside its interval?", patient_id=patient.id)

    assert result.status == "ANSWERED"
    assert result.retrieved_count == 1
