"""Phase 3 focused security tests. Per the speed rule these do not repeat
Phase 1/2 coverage — they test only the new retrieval-time authorization
boundary, which is the single most important behavior in the whole project:

    an unauthorized knowledge record must never be retrieved from Qdrant,
    and therefore must never be supplied to the LLM.

A tiny real Qdrant collection (qdrant-client's embedded mode, a fresh temp
dir per test) backs these tests so the actual filter engine is exercised,
not a hand-rolled stand-in for it. A fake, fast, deterministic embedder
replaces Sentence Transformers so these tests don't depend on downloading
or running a real ML model.
"""
import hashlib

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.authorization.context import AuthorizationContext, build_authorization_context
from app.authorization.qdrant_filter import build_retrieval_filter
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment
from app.services.vector_store import VectorStore

VECTOR_DIM = 8


class FakeEmbedder:
    """Deterministic, content-derived vectors — no ML model required."""

    dimension = VECTOR_DIM

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()[:VECTOR_DIM]
        return [b / 255.0 for b in digest]

    def embed_text(self, text: str) -> list[float]:
        return self._vec(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


FIXTURE_RECORDS = [
    {
        "knowledge_record_id": "kr-condition-p1",
        "source_type": "SYNTHEA",
        "source_document_id": None,
        "source_page": None,
        "source_section": None,
        "patient_id": "patient-1",
        "record_type": "condition",
        "department_id": None,
        "sensitivity": "clinical",
        "content": "Patient patient-1 has a diagnosis of Hypertension.",
    },
    {
        "knowledge_record_id": "kr-claim-p1",
        "source_type": "SYNTHEA",
        "source_document_id": None,
        "source_page": None,
        "source_section": None,
        "patient_id": "patient-1",
        "record_type": "claim",
        "department_id": None,
        "sensitivity": "finance",
        "content": "Patient patient-1 has an outstanding claim balance of 500.",
    },
    {
        "knowledge_record_id": "kr-condition-p2",
        "source_type": "SYNTHEA",
        "source_document_id": None,
        "source_page": None,
        "source_section": None,
        "patient_id": "patient-2",
        "record_type": "condition",
        "department_id": None,
        "sensitivity": "clinical",
        "content": "Patient patient-2 has a diagnosis of Diabetes.",
    },
    {
        "knowledge_record_id": "kr-encounter-p1",
        "source_type": "SYNTHEA",
        "source_document_id": None,
        "source_page": None,
        "source_section": None,
        "patient_id": "patient-1",
        "record_type": "encounter",
        "department_id": None,
        "sensitivity": "operational",
        "content": "Patient patient-1 had an encounter on 2026-01-01.",
    },
]


@pytest.fixture()
def fixture_store(tmp_path) -> VectorStore:
    client = QdrantClient(path=str(tmp_path / "qdrant"))
    store = VectorStore(client, "test_collection")
    embedder = FakeEmbedder()
    store.ensure_collection(embedder.dimension)
    points = [
        PointStruct(id=new_uuid(), vector=embedder.embed_text(r["content"]), payload=r) for r in FIXTURE_RECORDS
    ]
    store.upsert(points)
    return store


def _search_contents(store: VectorStore, ctx: AuthorizationContext) -> list[str]:
    query_filter = build_retrieval_filter(ctx)
    hits = store.search(FakeEmbedder().embed_text("diagnosis claim encounter"), query_filter, limit=10, score_threshold=0.0)
    return [h.payload["content"] for h in hits]


def test_doctor_sees_only_assigned_patient_clinical_and_operational_records(fixture_store):
    ctx = AuthorizationContext(
        user_id="u1",
        role=RoleEnum.DOCTOR,
        department_id=None,
        allowed_record_types=["condition", "medication", "encounter"],
        allowed_sensitivity=["clinical", "operational"],
        assigned_patient_ids=["patient-1"],
    )
    contents = _search_contents(fixture_store, ctx)
    assert any("Hypertension" in c for c in contents)
    assert any("encounter" in c for c in contents)
    # Never the unassigned patient's condition, and never the finance record.
    assert not any("Diabetes" in c for c in contents)
    assert not any("claim balance" in c for c in contents)


def test_finance_sees_only_claim_never_clinical(fixture_store):
    ctx = AuthorizationContext(
        user_id="u2",
        role=RoleEnum.FINANCE,
        department_id=None,
        allowed_record_types=["claim", "claim_transaction"],
        allowed_sensitivity=["finance"],
        assigned_patient_ids=None,
    )
    contents = _search_contents(fixture_store, ctx)
    assert any("claim balance" in c for c in contents)
    assert not any("Hypertension" in c for c in contents)
    assert not any("Diabetes" in c for c in contents)


def test_reception_sees_only_encounter(fixture_store):
    ctx = AuthorizationContext(
        user_id="u3",
        role=RoleEnum.RECEPTION,
        department_id=None,
        allowed_record_types=["encounter"],
        allowed_sensitivity=["operational"],
        assigned_patient_ids=None,
    )
    contents = _search_contents(fixture_store, ctx)
    assert any("encounter" in c for c in contents)
    assert not any("Hypertension" in c for c in contents)
    assert not any("claim balance" in c for c in contents)


def test_admin_sees_everything(fixture_store):
    ctx = AuthorizationContext(
        user_id="u4",
        role=RoleEnum.ADMIN,
        department_id=None,
        allowed_record_types=["condition", "claim", "encounter"],
        allowed_sensitivity=["clinical", "finance", "operational"],
        assigned_patient_ids=None,
    )
    contents = _search_contents(fixture_store, ctx)
    assert any("Hypertension" in c for c in contents)
    assert any("Diabetes" in c for c in contents)
    assert any("claim balance" in c for c in contents)


def test_doctor_with_no_assignments_matches_nothing(fixture_store):
    """An empty assigned_patient_ids list must never be treated as
    'no restriction' — that would silently grant access to everyone."""
    ctx = AuthorizationContext(
        user_id="u5",
        role=RoleEnum.DOCTOR,
        department_id=None,
        allowed_record_types=["condition"],
        allowed_sensitivity=["clinical"],
        assigned_patient_ids=[],
    )
    query_filter = build_retrieval_filter(ctx)
    hits = fixture_store.search(FakeEmbedder().embed_text("diagnosis"), query_filter, limit=10, score_threshold=0.0)
    assert hits == []


def test_build_authorization_context_resolves_real_patient_assignments(db_session, seeded_doctor):
    db_session.add(
        PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending")
    )
    db_session.commit()

    ctx = build_authorization_context(db_session, seeded_doctor)
    assert ctx.assigned_patient_ids == ["patient-1"]
    assert "condition" in ctx.allowed_record_types
    assert "claim" not in ctx.allowed_record_types
