"""Focused tests for the two endpoints added for the frontend: the patient
list must never diverge from what RAG retrieval would actually authorize,
and the status endpoint must fall back to 'No Recent Information' rather
than invent a status when retrieval itself was denied or found nothing."""
from unittest.mock import patch

from app.models.provenance import new_uuid
from app.models.ward import PatientAssignment
from app.rag.pipeline import RetrievalOutcome


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


def test_status_returns_no_recent_information_when_denied(client, seeded_doctor):
    token = _login(client, "doctor01", "secret123", "DOCTOR")
    with patch(
        "app.api.patients.retrieve_authorized_sources",
        return_value=RetrievalOutcome(status="DENIED", sources=[], debug={}, denial_answer="restricted"),
    ):
        response = client.get("/api/patients/some-patient/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "No Recent Information"
    assert body["citations"] == []


def test_status_reports_attention_when_a_condition_is_authorized(client, seeded_doctor):
    token = _login(client, "doctor01", "secret123", "DOCTOR")
    fake_sources = [
        {
            "knowledge_record_id": "kr-1",
            "source_type": "SYNTHEA",
            "record_type": "condition",
            "source_document_id": None,
            "source_page": None,
            "source_section": None,
        }
    ]
    with patch(
        "app.api.patients.retrieve_authorized_sources",
        return_value=RetrievalOutcome(status="OK", sources=fake_sources, debug={}),
    ):
        response = client.get("/api/patients/some-patient/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["status"] == "Attention"
