"""Focused tests for the two endpoints added for the frontend: the patient
list must never diverge from what RAG retrieval would actually authorize,
and the status endpoint must fall back to 'No Recent Information' rather
than invent a status for a patient that isn't authorized or for a role
that has no clinical access — all via a direct DB check, not RAG/Qdrant
(see progress/DECISIONS.md on why that matters for latency)."""
import pytest

from app.models.hospital import Condition
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment


@pytest.fixture()
def seeded_finance(db_session):
    from app.auth.security import hash_password

    user = User(username="finance01", full_name="Finance", hashed_password=hash_password("secret123"), role=RoleEnum.FINANCE)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, username, password, role):
    response = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    return response.json()["access_token"]


def test_list_patients_requires_auth(client):
    response = client.get("/api/patients")
    assert response.status_code == 401


def test_doctor_patient_list_is_scoped_to_assignments(client, db_session, seeded_doctor):
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    token = _login(client, "doctor01", "secret123", "DOCTOR")
    response = client.get("/api/patients", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "assigned"
    assert body["patient_ids"] == ["patient-1"]
    assert body["total"] == 1


def test_status_returns_no_recent_information_for_unassigned_patient(client, db_session, seeded_doctor):
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    token = _login(client, "doctor01", "secret123", "DOCTOR")
    response = client.get("/api/patients/patient-2/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "No Recent Information"
    assert body["citations"] == []


def test_status_returns_no_recent_information_for_non_clinical_role(client, db_session, seeded_finance):
    """FINANCE has no clinical access, so status must never report Stable/
    Attention for them even if a condition row exists for that patient."""
    db_session.add(Condition(id=new_uuid(), patient="patient-1", description="Hypertension"))
    db_session.commit()

    token = _login(client, "finance01", "secret123", "FINANCE")
    response = client.get("/api/patients/patient-1/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["status"] == "No Recent Information"


def test_status_reports_attention_when_a_condition_exists(client, db_session, seeded_doctor):
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.add(Condition(id=new_uuid(), patient="patient-1", description="Hypertension"))
    db_session.commit()

    token = _login(client, "doctor01", "secret123", "DOCTOR")
    response = client.get("/api/patients/patient-1/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Attention"
    assert len(body["citations"]) == 1


def test_status_reports_stable_when_no_condition_exists(client, db_session, seeded_doctor):
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    token = _login(client, "doctor01", "secret123", "DOCTOR")
    response = client.get("/api/patients/patient-1/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["status"] == "Stable"
