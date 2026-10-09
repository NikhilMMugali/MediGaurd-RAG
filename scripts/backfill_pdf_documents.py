"""Idempotent, safe backfill for previously-uploaded PDF documents whose
patient was never identified (source_documents.patient_id is None) — the
same broken state behind the two reported "PDF retrieval" bugs this session
(progress/DECISIONS.md "PDF retrieval fix" parts 1 and 2). Re-uses the exact
same repair logic the live duplicate-upload endpoint uses
(app.ingestion.pdf_mapper.repair_patient_link) rather than a second,
divergent implementation.

What it does, per candidate document:
  1. Read the already-persisted PDF bytes from disk (storage_path).
  2. Re-run text extraction and the current (three-tier) identity parser.
  3. If a patient can now be identified: link the document to it (matching
     an existing patient by external id/name where possible, never
     duplicating one), backfill patient_id onto any of that document's
     knowledge_records that still have none, and assign the document's
     original uploader as attending if the patient was newly created.
  4. Re-index that document's knowledge_records into Qdrant so the payload
     (which bakes patient_id in at upsert time) is corrected too.

Idempotent and safe to re-run: a document that already has a patient_id, or
whose identity still can't be resolved, is left untouched. Qdrant upsert is
idempotent on each knowledge_record's own stable id. No existing data is
deleted, no vector collection is reset, and only documents with
patient_id IS NULL are ever touched.

Run from the repo root, with the app NOT also running (embedded Qdrant
holds an exclusive single-writer file lock — see docs/TECH_STACK.md):

    cd backend && python3 ../scripts/backfill_pdf_documents.py [--dry-run]

--dry-run reports what would be repaired without writing anything or
touching Qdrant.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.ingestion.pdf_extractor import PdfExtractionError, extract_pdf  # noqa: E402
from app.ingestion.pdf_mapper import extract_patient_document_data, repair_patient_link  # noqa: E402
from app.models.documents import KnowledgeRecord, SourceDocument  # noqa: E402
from app.rag.indexing import index_records  # noqa: E402
from app.services.embedding_provider import get_embedding_provider  # noqa: E402
from app.services.vector_store import get_vector_store  # noqa: E402

settings = get_settings()


def main(dry_run: bool) -> None:
    db = SessionLocal()
    upload_dir = Path(settings.upload_dir)

    candidates = (
        db.query(SourceDocument)
        .filter(
            SourceDocument.patient_id.is_(None),
            SourceDocument.source_type == "UPLOADED_PDF",
            SourceDocument.storage_path.isnot(None),
        )
        .all()
    )
    print(f"Found {len(candidates)} uploaded document(s) with no patient association.")
    if not candidates:
        db.close()
        return

    embedder = None
    store = None
    if not dry_run:
        embedder = get_embedding_provider()
        store = get_vector_store()
        store.ensure_collection(embedder.dimension)

    repaired = 0
    for doc in candidates:
        full_path = upload_dir / doc.storage_path
        if not full_path.is_file():
            print(f"  SKIP {doc.id} ({doc.file_name}): stored file missing at {full_path}")
            continue

        try:
            result = extract_pdf(full_path.read_bytes(), doc.file_name)
        except PdfExtractionError as exc:
            print(f"  SKIP {doc.id} ({doc.file_name}): extraction failed — {exc}")
            continue

        if dry_run:
            normalized = extract_patient_document_data(result)
            info = normalized.patient
            if info and (info.first or info.last or info.external_patient_id):
                name = " ".join(p for p in (info.first, info.last) if p) or "(name not found)"
                print(f"  WOULD REPAIR {doc.id} ({doc.file_name}): identified as {name!r} (id={info.external_patient_id})")
            else:
                print(f"  WOULD SKIP {doc.id} ({doc.file_name}): identity still not resolvable")
            continue

        patient = repair_patient_link(db, doc, result, assign_user_id=doc.uploaded_by)
        if patient is None:
            print(f"  SKIP {doc.id} ({doc.file_name}): identity still not resolvable")
            continue

        records = db.query(KnowledgeRecord).filter(KnowledgeRecord.source_document_id == doc.id).all()
        indexed = index_records(records, embedder, store) if records else 0
        display = patient.display_id or patient.id
        print(f"  REPAIRED {doc.id} ({doc.file_name}) -> patient {display}, re-indexed {indexed} chunk(s)")
        repaired += 1

    db.close()
    verb = "would be repaired" if dry_run else "repaired"
    print(f"Done. {repaired if not dry_run else '(see above)'}/{len(candidates)} document(s) {verb}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be repaired without writing anything.")
    args = parser.parse_args()
    main(args.dry_run)
