"""Canonical hospital tables, columns matching the verified Synthea CSV
headers exactly (see docs/DATABASE_SCHEMA.md). Tables whose CSV has no
native id column (conditions, medications, observations, allergies,
procedures, immunizations, devices, supplies, payer_transitions) get a
surrogate UUID primary key generated at import time; everything else keeps
Synthea's own id so relationships don't need remapping.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.provenance import ProvenanceMixin, new_uuid


class Organization(Base, ProvenanceMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(10))
    zip: Mapped[str | None] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(String(50))
    revenue: Mapped[float | None] = mapped_column(Float)
    utilization: Mapped[int | None] = mapped_column(Integer)
    npi: Mapped[str | None] = mapped_column(String(50))


class Provider(Base, ProvenanceMixin):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str | None] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(10))
    speciality: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(10))
    zip: Mapped[str | None] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    encounters: Mapped[int | None] = mapped_column(Integer)
    procedures: Mapped[int | None] = mapped_column(Integer)
    npi: Mapped[str | None] = mapped_column(String(50))


class Payer(Base, ProvenanceMixin):
    __tablename__ = "payers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    ownership: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state_headquartered: Mapped[str | None] = mapped_column(String(10))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(50))
    amount_covered: Mapped[float | None] = mapped_column(Float)
    amount_uncovered: Mapped[float | None] = mapped_column(Float)
    revenue: Mapped[float | None] = mapped_column(Float)
    covered_encounters: Mapped[int | None] = mapped_column(Integer)
    uncovered_encounters: Mapped[int | None] = mapped_column(Integer)
    covered_medications: Mapped[int | None] = mapped_column(Integer)
    uncovered_medications: Mapped[int | None] = mapped_column(Integer)
    covered_procedures: Mapped[int | None] = mapped_column(Integer)
    uncovered_procedures: Mapped[int | None] = mapped_column(Integer)
    covered_immunizations: Mapped[int | None] = mapped_column(Integer)
    uncovered_immunizations: Mapped[int | None] = mapped_column(Integer)
    unique_customers: Mapped[int | None] = mapped_column(Integer)
    qols_avg: Mapped[float | None] = mapped_column(Float)
    member_months: Mapped[int | None] = mapped_column(Integer)


class Patient(Base, ProvenanceMixin):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Set when this patient was introduced via an uploaded PDF rather than
    # Synthea, to preserve the document's own identifier without pretending
    # it is a Synthea id.
    external_patient_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Clean demo-facing id ("P001") shown everywhere in the UI instead of
    # the raw Synthea UUID in `id`. `id` remains the real internal/foreign
    # key used by every other table (conditions.patient, knowledge_records
    # .patient_id, patient_assignments.patient_id, etc.) — adding this
    # column avoids remapping every FK in the schema just to get a readable
    # display id (docs/CLEAN_DATASET.md).
    display_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)

    birthdate: Mapped[date | None] = mapped_column(Date)
    deathdate: Mapped[date | None] = mapped_column(Date)
    # Highly sensitive — never embedded, never surfaced in ordinary RAG answers.
    ssn: Mapped[str | None] = mapped_column(String(20))
    drivers: Mapped[str | None] = mapped_column(String(50))
    passport: Mapped[str | None] = mapped_column(String(50))

    prefix: Mapped[str | None] = mapped_column(String(10))
    first: Mapped[str | None] = mapped_column(String(100))
    middle: Mapped[str | None] = mapped_column(String(100))
    last: Mapped[str | None] = mapped_column(String(100))
    suffix: Mapped[str | None] = mapped_column(String(10))
    maiden: Mapped[str | None] = mapped_column(String(100))
    marital: Mapped[str | None] = mapped_column(String(10))
    race: Mapped[str | None] = mapped_column(String(50))
    ethnicity: Mapped[str | None] = mapped_column(String(50))
    gender: Mapped[str | None] = mapped_column(String(10))
    birthplace: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(10))
    county: Mapped[str | None] = mapped_column(String(100))
    fips: Mapped[str | None] = mapped_column(String(20))
    zip: Mapped[str | None] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    healthcare_expenses: Mapped[float | None] = mapped_column(Float)
    healthcare_coverage: Mapped[float | None] = mapped_column(Float)
    income: Mapped[float | None] = mapped_column(Float)


class Encounter(Base, ProvenanceMixin):
    __tablename__ = "encounters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    start: Mapped[datetime | None] = mapped_column(DateTime)
    stop: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    organization: Mapped[str | None] = mapped_column(String(36))
    provider: Mapped[str | None] = mapped_column(String(36))
    payer: Mapped[str | None] = mapped_column(String(36))
    encounterclass: Mapped[str | None] = mapped_column(String(50))
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    base_encounter_cost: Mapped[float | None] = mapped_column(Float)
    total_claim_cost: Mapped[float | None] = mapped_column(Float)
    payer_coverage: Mapped[float | None] = mapped_column(Float)
    reasoncode: Mapped[str | None] = mapped_column(String(50))
    reasondescription: Mapped[str | None] = mapped_column(String(255))


class Condition(Base, ProvenanceMixin):
    __tablename__ = "conditions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    start: Mapped[date | None] = mapped_column(Date)
    stop: Mapped[date | None] = mapped_column(Date)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    system: Mapped[str | None] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))


class Medication(Base, ProvenanceMixin):
    __tablename__ = "medications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    start: Mapped[datetime | None] = mapped_column(DateTime)
    stop: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    payer: Mapped[str | None] = mapped_column(String(36))
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    base_cost: Mapped[float | None] = mapped_column(Float)
    payer_coverage: Mapped[float | None] = mapped_column(Float)
    dispenses: Mapped[int | None] = mapped_column(Integer)
    totalcost: Mapped[float | None] = mapped_column(Float)
    reasoncode: Mapped[str | None] = mapped_column(String(50))
    reasondescription: Mapped[str | None] = mapped_column(String(255))


class Observation(Base, ProvenanceMixin):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    date: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    category: Mapped[str | None] = mapped_column(String(50))
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    value: Mapped[str | None] = mapped_column(String(255))
    units: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[str | None] = mapped_column(String(50))


class Allergy(Base, ProvenanceMixin):
    __tablename__ = "allergies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    start: Mapped[date | None] = mapped_column(Date)
    stop: Mapped[date | None] = mapped_column(Date)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    system: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(50))
    category: Mapped[str | None] = mapped_column(String(50))
    reaction1: Mapped[str | None] = mapped_column(String(50))
    description1: Mapped[str | None] = mapped_column(String(255))
    severity1: Mapped[str | None] = mapped_column(String(20))
    reaction2: Mapped[str | None] = mapped_column(String(50))
    description2: Mapped[str | None] = mapped_column(String(255))
    severity2: Mapped[str | None] = mapped_column(String(20))


class Procedure(Base, ProvenanceMixin):
    __tablename__ = "procedures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    start: Mapped[datetime | None] = mapped_column(DateTime)
    stop: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    system: Mapped[str | None] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    base_cost: Mapped[float | None] = mapped_column(Float)
    reasoncode: Mapped[str | None] = mapped_column(String(50))
    reasondescription: Mapped[str | None] = mapped_column(String(255))


class Careplan(Base, ProvenanceMixin):
    __tablename__ = "careplans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    start: Mapped[date | None] = mapped_column(Date)
    stop: Mapped[date | None] = mapped_column(Date)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    reasoncode: Mapped[str | None] = mapped_column(String(50))
    reasondescription: Mapped[str | None] = mapped_column(String(255))


class Immunization(Base, ProvenanceMixin):
    __tablename__ = "immunizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    date: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    base_cost: Mapped[float | None] = mapped_column(Float)


class ImagingStudy(Base, ProvenanceMixin):
    __tablename__ = "imaging_studies"

    # Synthea's own Id repeats across series/instance rows within one study,
    # so it cannot be the primary key here; kept as study_id instead.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    study_id: Mapped[str | None] = mapped_column(String(36), index=True)
    date: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    series_uid: Mapped[str | None] = mapped_column(String(255))
    bodysite_code: Mapped[str | None] = mapped_column(String(50))
    bodysite_description: Mapped[str | None] = mapped_column(String(255))
    modality_code: Mapped[str | None] = mapped_column(String(20))
    modality_description: Mapped[str | None] = mapped_column(String(255))
    instance_uid: Mapped[str | None] = mapped_column(String(255))
    sop_code: Mapped[str | None] = mapped_column(String(50))
    sop_description: Mapped[str | None] = mapped_column(String(255))
    procedure_code: Mapped[str | None] = mapped_column(String(50))


class Device(Base, ProvenanceMixin):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    start: Mapped[datetime | None] = mapped_column(DateTime)
    stop: Mapped[datetime | None] = mapped_column(DateTime)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    udi: Mapped[str | None] = mapped_column(String(255))


class Supply(Base, ProvenanceMixin):
    __tablename__ = "supplies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    date: Mapped[date | None] = mapped_column(Date)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    encounter: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[int | None] = mapped_column(Integer)


class Claim(Base, ProvenanceMixin):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patientid: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    providerid: Mapped[str | None] = mapped_column(String(36))
    primarypatientinsuranceid: Mapped[str | None] = mapped_column(String(36))
    secondarypatientinsuranceid: Mapped[str | None] = mapped_column(String(36))
    departmentid: Mapped[str | None] = mapped_column(String(20))
    patientdepartmentid: Mapped[str | None] = mapped_column(String(20))
    diagnosis1: Mapped[str | None] = mapped_column(String(50))
    diagnosis2: Mapped[str | None] = mapped_column(String(50))
    diagnosis3: Mapped[str | None] = mapped_column(String(50))
    diagnosis4: Mapped[str | None] = mapped_column(String(50))
    diagnosis5: Mapped[str | None] = mapped_column(String(50))
    diagnosis6: Mapped[str | None] = mapped_column(String(50))
    diagnosis7: Mapped[str | None] = mapped_column(String(50))
    diagnosis8: Mapped[str | None] = mapped_column(String(50))
    referringproviderid: Mapped[str | None] = mapped_column(String(36))
    appointmentid: Mapped[str | None] = mapped_column(String(36))
    currentillnessdate: Mapped[datetime | None] = mapped_column(DateTime)
    servicedate: Mapped[datetime | None] = mapped_column(DateTime)
    supervisingproviderid: Mapped[str | None] = mapped_column(String(36))
    status1: Mapped[str | None] = mapped_column(String(20))
    status2: Mapped[str | None] = mapped_column(String(20))
    statusp: Mapped[str | None] = mapped_column(String(20))
    outstanding1: Mapped[float | None] = mapped_column(Float)
    outstanding2: Mapped[float | None] = mapped_column(Float)
    outstandingp: Mapped[float | None] = mapped_column(Float)
    lastbilleddate1: Mapped[datetime | None] = mapped_column(DateTime)
    lastbilleddate2: Mapped[datetime | None] = mapped_column(DateTime)
    lastbilleddatep: Mapped[datetime | None] = mapped_column(DateTime)
    healthcareclaimtypeid1: Mapped[str | None] = mapped_column(String(10))
    healthcareclaimtypeid2: Mapped[str | None] = mapped_column(String(10))


class ClaimTransaction(Base, ProvenanceMixin):
    __tablename__ = "claims_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claimid: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    chargeid: Mapped[str | None] = mapped_column(String(50))
    patientid: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    type: Mapped[str | None] = mapped_column(String(30))
    amount: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(30))
    fromdate: Mapped[datetime | None] = mapped_column(DateTime)
    todate: Mapped[datetime | None] = mapped_column(DateTime)
    placeofservice: Mapped[str | None] = mapped_column(String(36))
    procedurecode: Mapped[str | None] = mapped_column(String(50))
    modifier1: Mapped[str | None] = mapped_column(String(20))
    modifier2: Mapped[str | None] = mapped_column(String(20))
    diagnosisref1: Mapped[str | None] = mapped_column(String(10))
    diagnosisref2: Mapped[str | None] = mapped_column(String(10))
    diagnosisref3: Mapped[str | None] = mapped_column(String(10))
    diagnosisref4: Mapped[str | None] = mapped_column(String(10))
    units: Mapped[int | None] = mapped_column(Integer)
    departmentid: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    unitamount: Mapped[float | None] = mapped_column(Float)
    transferoutid: Mapped[str | None] = mapped_column(String(36))
    transfertype: Mapped[str | None] = mapped_column(String(10))
    payments: Mapped[float | None] = mapped_column(Float)
    adjustments: Mapped[float | None] = mapped_column(Float)
    transfers: Mapped[float | None] = mapped_column(Float)
    outstanding: Mapped[float | None] = mapped_column(Float)
    appointmentid: Mapped[str | None] = mapped_column(String(36))
    linenote: Mapped[str | None] = mapped_column(Text)
    patientinsuranceid: Mapped[str | None] = mapped_column(String(36))
    feescheduleid: Mapped[str | None] = mapped_column(String(36))
    providerid: Mapped[str | None] = mapped_column(String(36))
    supervisingproviderid: Mapped[str | None] = mapped_column(String(36))


class PayerTransition(Base, ProvenanceMixin):
    __tablename__ = "payer_transitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    memberid: Mapped[str | None] = mapped_column(String(36))
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    end_date: Mapped[datetime | None] = mapped_column(DateTime)
    payer: Mapped[str | None] = mapped_column(String(36))
    secondary_payer: Mapped[str | None] = mapped_column(String(36))
    plan_ownership: Mapped[str | None] = mapped_column(String(20))
    owner_name: Mapped[str | None] = mapped_column(String(255))
