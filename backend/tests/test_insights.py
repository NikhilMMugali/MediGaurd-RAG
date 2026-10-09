"""Focused tests for Hospital Insights (section 12 "Hospital Insights"
checklist): every metric must come from real, authorization-scoped SQL —
never a wider scope than the role's own authorization context, and never a
fabricated value. The LLM is only ever asked to narrate metrics already
computed; test_insights_query_with_no_metrics_never_calls_llm proves the
no-data path short-circuits before any LLM call could invent something.
"""
import pytest

from app.auth.security import hash_password
from app.models.hospital import Condition, Medication, Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment
from app.rag.insights import answer_insight_question, build_overview


@pytest.fixture(autouse=True)
def fake_vector_store(monkeypatch):
    class FakeStore:
        def count(self) -> int:
            return 7

    monkeypatch.setattr("app.services.vector_store.get_vector_store", lambda: FakeStore())


@pytest.fixture()
def seeded_finance(db_session):
    user = User(username="finance01", full_name="Finance", hashed_password=hash_password("secret123"), role=RoleEnum.FINANCE)
    db_session.add(user)
    db_session.commit()
    return user


def _seed_patient(db_session, patient_id: str) -> Patient:
    patient = Patient(id=patient_id, first="Test", last="Patient")
    db_session.add(patient)
    db_session.commit()
    return patient


def test_doctor_with_no_assignments_gets_honest_empty_note_not_zero(db_session, seeded_doctor):
    overview = build_overview(db_session, seeded_doctor)
    assert overview.metrics == []
    assert overview.note is not None and "no assigned patients" in overview.note.lower()


def test_doctor_metrics_scoped_to_assigned_patients_only(db_session, seeded_doctor):
    _seed_patient(db_session, "patient-1")
    _seed_patient(db_session, "patient-2")
    db_session.add(Condition(id=new_uuid(), patient="patient-1", description="Hypertension"))
    db_session.add(Condition(id=new_uuid(), patient="patient-2", description="Diabetes"))
    db_session.add(Medication(id=new_uuid(), patient="patient-1", description="Metformin"))
    db_session.add(PatientAssignment(id=new_uuid(), patient_id="patient-1", user_id=seeded_doctor.id, assignment_type="attending"))
    db_session.commit()

    overview = build_overview(db_session, seeded_doctor)
    values = {m.key: m.value for m in overview.metrics}

    assert values["assigned_patients"] == 1
    # Only patient-1's condition is counted — patient-2's is a different
    # (unassigned) patient's data and must never inflate this doctor's number.
    assert values["documented_conditions"] == 1
    assert values["documented_medications"] == 1


def test_admin_overview_reports_live_counts_not_hardcoded(db_session, seeded_admin):
    _seed_patient(db_session, "patient-1")
    overview = build_overview(db_session, seeded_admin)
    values = {m.key: m.value for m in overview.metrics}
    assert values["total_patients"] == 1
    assert values["vectors"] == 7  # from fake_vector_store, proving it's read live, not hardcoded


def test_finance_outstanding_total_is_summed_from_real_claims(db_session, seeded_finance):
    from app.models.hospital import Claim

    db_session.add(Claim(id=new_uuid(), patientid="patient-1", outstandingp=120.5))
    db_session.add(Claim(id=new_uuid(), patientid="patient-1", outstandingp=0.0))
    db_session.commit()

    overview = build_overview(db_session, seeded_finance)
    values = {m.key: m.value for m in overview.metrics}
    assert values["outstanding_total"] == 120.5
    assert values["claims_with_balance"] == 1


def test_insights_query_with_no_metrics_never_calls_llm(db_session, seeded_doctor, monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("LLM must not be called when there are no authorized metrics to narrate")

    monkeypatch.setattr("app.rag.insights.get_llm_provider", _fail_if_called)

    result = answer_insight_question(db_session, seeded_doctor, "Summarize this patient's care.")
    assert result.metrics == []
    assert "no assigned patients" in result.answer.lower()


@pytest.fixture()
def seeded_admin(db_session):
    user = User(username="admin01", full_name="Admin", hashed_password=hash_password("secret123"), role=RoleEnum.ADMIN)
    db_session.add(user)
    db_session.commit()
    return user
