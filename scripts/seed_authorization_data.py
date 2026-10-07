"""Seed application-level authorization data: departments, wards, and
deterministic patient assignments for the demo doctor/nurse against REAL
imported Synthea patient ids (never fabricated ids).

Run after scripts/import_synthea.py and scripts/seed_users.py.

Usage:
    python scripts/seed_authorization_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.hospital import Patient  # noqa: E402
from app.models.user import Department, User  # noqa: E402
from app.models.ward import PatientAssignment, Ward  # noqa: E402

DEPARTMENTS = ["Cardiology", "General", "Emergency", "Nursing", "Finance", "Reception", "Admin"]
WARDS = [
    ("ICU", "Emergency"),
    ("Cardiology Ward", "Cardiology"),
    ("General Ward", "General"),
    ("Emergency Ward", "Emergency"),
]
ASSIGNMENTS_PER_WARD = 5


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        departments: dict[str, Department] = {}
        for name in DEPARTMENTS:
            dept = db.query(Department).filter(Department.name == name).first()
            if dept is None:
                dept = Department(name=name)
                db.add(dept)
                db.flush()
            departments[name] = dept

        wards: dict[str, Ward] = {}
        for ward_name, dept_name in WARDS:
            ward = db.query(Ward).filter(Ward.name == ward_name).first()
            if ward is None:
                ward = Ward(name=ward_name, department_id=departments[dept_name].id)
                db.add(ward)
                db.flush()
            wards[ward_name] = ward

        doctor = db.query(User).filter(User.username == "doctor01").first()
        nurse = db.query(User).filter(User.username == "nurse01").first()
        if doctor is None or nurse is None:
            print("doctor01/nurse01 not found — run scripts/seed_users.py first.")
            return

        if doctor.department_id is None:
            doctor.department_id = departments["Cardiology"].id
        if nurse.department_id is None:
            nurse.department_id = departments["General"].id

        existing_assignments = db.query(PatientAssignment).count()
        if existing_assignments > 0:
            print(f"SKIP  patient_assignments: already has {existing_assignments} rows")
            db.commit()
            return

        real_patients = [p.id for p in db.query(Patient.id).limit(ASSIGNMENTS_PER_WARD * 2).all()]
        if not real_patients:
            print("No patients found — run scripts/import_synthea.py first.")
            return

        created = 0
        for patient_id in real_patients[:ASSIGNMENTS_PER_WARD]:
            db.add(
                PatientAssignment(
                    patient_id=patient_id,
                    user_id=doctor.id,
                    ward_id=wards["Cardiology Ward"].id,
                    assignment_type="attending",
                )
            )
            created += 1
        for patient_id in real_patients[ASSIGNMENTS_PER_WARD : ASSIGNMENTS_PER_WARD * 2]:
            db.add(
                PatientAssignment(
                    patient_id=patient_id,
                    user_id=nurse.id,
                    ward_id=wards["General Ward"].id,
                    assignment_type="ward_nurse",
                )
            )
            created += 1

        db.commit()
        print(f"Seeded {len(departments)} departments, {len(wards)} wards, {created} patient assignments.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
