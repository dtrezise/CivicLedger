import hashlib
import mimetypes
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.models import IngestionRun, ParserArtifact, RawDocument
from app.parsers import get_parser


RAW_ARCHIVE_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw_documents"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guess_content_type(path: Path, content_type: str | None = None) -> str:
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def archive_manual_source_document(
    session: Session,
    *,
    source_id: str,
    source_url: str,
    local_file: Path,
    content_type: str | None = None,
    notes: str | None = None,
    access_acknowledged: bool = False,
) -> tuple[IngestionRun, RawDocument, ParserArtifact]:
    if not local_file.exists() or not local_file.is_file():
        raise FileNotFoundError(f"Local artifact not found: {local_file}")

    parser = get_parser(source_id)
    resolved_content_type = guess_content_type(local_file, content_type)
    file_hash = sha256_file(local_file)
    archive_dir = RAW_ARCHIVE_ROOT / source_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_path = archive_dir / f"{file_hash[:16]}-{local_file.name}"
    if not archived_path.exists():
        shutil.copy2(local_file, archived_path)

    now = datetime.utcnow()
    run = IngestionRun(
        id=uuid4(),
        source_name=source_id,
        source_url=source_url,
        started_at=now,
        completed_at=now,
        status="completed",
        dataset_version=settings.DATASET_VERSION,
        parser_version=settings.PARSER_VERSION,
        notes=notes or "Manual source intake; raw artifact archived before parsing.",
    )
    session.add(run)
    session.flush()

    raw_document = RawDocument(
        id=uuid4(),
        ingestion_run_id=run.id,
        source_url=source_url,
        retrieved_at=now,
        retrieval_source=source_id,
        content_type=resolved_content_type,
        file_hash=file_hash,
        storage_uri=str(archived_path),
        rights_status="public_record_access_restricted",
        parser_version=settings.PARSER_VERSION,
        provenance_complete=True,
        source_metadata={
            "source_id": source_id,
            "manual_intake": True,
            "access_acknowledged": access_acknowledged,
            "original_filename": local_file.name,
        },
    )
    session.add(raw_document)
    session.flush()

    content = archived_path.read_bytes()
    preview = parser.preview(content, filename=local_file.name, content_type=resolved_content_type)
    artifact = ParserArtifact(
        id=uuid4(),
        source_id=source_id,
        raw_document_id=raw_document.id,
        artifact_type="preview",
        parser_output={
            "document_type": preview.document_type,
            "normalized_record_count": preview.normalized_record_count,
            "filer_name": preview.filer_name,
            "report_type": preview.report_type,
            "filing_date": preview.filing_date,
            "transactions": [transaction.to_dict() for transaction in preview.transactions],
            "warnings": preview.warnings,
            "output": preview.output,
        },
        text_span={},
        confidence=None,
    )
    session.add(artifact)
    session.commit()
    session.refresh(run)
    session.refresh(raw_document)
    session.refresh(artifact)
    return run, raw_document, artifact
