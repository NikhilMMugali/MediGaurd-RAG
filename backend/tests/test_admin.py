"""Focused tests for the admin system-overview endpoints (section 66/69 —
live counts, never hardcoded). get_vector_store() is monkeypatched to a
fake with a fixed .count() so these tests never touch the real on-disk
Qdrant collection (which a concurrent indexing run may hold locked —
see progress/DECISIONS.md)."""
import pytest

from app.models.documents import AuditLog, SourceDocument
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User


@pytest.fixture()
def seeded_admin(db_session):
    from app.auth.security import hash_password

    user = User(username="admin01", full_name="Admin", hashed_password=hash_password("secret123"), role=RoleEnum.ADMIN)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(autouse=True)
def fake_vector_store(monkeypatch):
    class FakeStore:
        def count(self) -> int:
            return 42

    monkeypatch.setattr("app.services.vector_store.get_vector_store", lambda: FakeStore())


def _login(client, username, password, role):
    response = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    return response.json()["access_token"]


def test_database_stats_requires_admin(client, seeded_doctor):
    token = _login(client, "doctor01", "secret123", "DOCTOR")
    response = client.get("/api/admin/database/stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_database_stats_reports_live_counts(client, db_session, seeded_admin):
    token = _login(client, "admin01", "secret123", "ADMIN")
    response = client.get("/api/admin/database/stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["vectors"] == 42
    assert body["patients"] == 0  # no patients seeded in this test


def test_recent_activity_reports_uploads_and_security_events(client, db_session, seeded_admin):
    db_session.add(
        SourceDocument(id=new_uuid(), file_name="patient_P101.pdf", file_hash="hash1", status="COMPLETED")
    )
    db_session.add(
        AuditLog(
            id=new_uuid(),
            user_id=seeded_admin.id,
            action="rag_query",
            status="DENIED",
            query="What medications is P001 taking?",
            metadata_json={"denial_reason": "patient not assigned"},
        )
    )
    db_session.commit()

    token = _login(client, "admin01", "secret123", "ADMIN")
    response = client.get("/api/admin/activity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["recent_uploads"][0]["file_name"] == "patient_P101.pdf"
    assert body["recent_security_events"][0]["status"] == "DENIED"
    assert body["recent_security_events"][0]["reason"] == "patient not assigned"
