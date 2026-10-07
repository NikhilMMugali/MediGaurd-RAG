from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db.session import get_db
from app.models.documents import IngestionJob, KnowledgeRecord
from app.models.hospital import (
    Allergy,
    Claim,
    ClaimTransaction,
    Condition,
    Encounter,
    Medication,
    Observation,
    Patient,
    Procedure,
)
from app.models.user import RoleEnum
from app.schemas.admin import DatabaseStats, IngestionJobStatus

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/database/stats", response_model=DatabaseStats, dependencies=[Depends(require_roles(RoleEnum.ADMIN))])
def database_stats(db: Session = Depends(get_db)) -> DatabaseStats:
    return DatabaseStats(
        patients=db.query(Patient).count(),
        encounters=db.query(Encounter).count(),
        conditions=db.query(Condition).count(),
        medications=db.query(Medication).count(),
        observations=db.query(Observation).count(),
        allergies=db.query(Allergy).count(),
        procedures=db.query(Procedure).count(),
        claims=db.query(Claim).count(),
        claims_transactions=db.query(ClaimTransaction).count(),
        knowledge_records=db.query(KnowledgeRecord).count(),
    )


@router.get(
    "/ingestion/{job_id}",
    response_model=IngestionJobStatus,
    dependencies=[Depends(require_roles(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE))],
)
def ingestion_job_status(job_id: str, db: Session = Depends(get_db)) -> IngestionJobStatus:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
    return IngestionJobStatus(
        id=job.id,
        source_document_id=job.source_document_id,
        status=job.status,
        records_created=job.records_created,
        chunks_created=job.chunks_created,
        error_message=job.error_message,
    )
