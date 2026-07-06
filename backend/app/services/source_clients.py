import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.models import IngestionRun, ParserArtifact, RawDocument
from app.parsers import get_supported_source_ids
from app.services.intake import archive_manual_source_document
from app.services.official_sources import OFFICIAL_SOURCES


@dataclass(frozen=True)
class SourceDownloadPlan:
    source_id: str
    source_url: str
    access_mode: str
    requires_acknowledgement: bool
    notes: str


@dataclass(frozen=True)
class SourceDownloadResult:
    plan: SourceDownloadPlan
    ingestion_run: IngestionRun
    raw_document: RawDocument
    parser_artifact: ParserArtifact


def source_by_id(source_id: str) -> dict:
    for source in OFFICIAL_SOURCES:
        if source["id"] == source_id:
            return source
    supported = ", ".join(get_supported_source_ids())
    raise ValueError(f"Unsupported source_id '{source_id}'. Supported: {supported}")


def build_download_plan(
    source_id: str,
    *,
    source_url: str | None = None,
    use_public_sample: bool = False,
    access_acknowledged: bool = False,
) -> SourceDownloadPlan:
    source = source_by_id(source_id)
    selected_url = source_url
    if use_public_sample:
        selected_url = source.get("public_sample_url")
    if not selected_url:
        raise ValueError(
            f"{source_id} does not expose a configured bulk download URL. "
            "Provide --url for a specific public document or use manual intake."
        )

    access_mode = source.get("access_mode") or "public_portal"
    requires_acknowledgement = "acknowledged" in access_mode
    if requires_acknowledgement and not access_acknowledged:
        raise ValueError(
            f"{source_id} requires human acknowledgement of source access/use terms. "
            "Rerun with --access-acknowledged after reviewing the official source notice."
        )

    notes = (
        f"Automated official-source download via {access_mode}. "
        f"Source page: {source['source_url']}"
    )
    return SourceDownloadPlan(
        source_id=source_id,
        source_url=selected_url,
        access_mode=access_mode,
        requires_acknowledgement=requires_acknowledgement,
        notes=notes,
    )


def filename_from_url(url: str, fallback: str = "official-source-document") -> str:
    name = Path(urlparse(url).path).name
    return name or fallback


def fetch_to_tempfile(url: str) -> tuple[Path, str | None]:
    request = Request(
        url,
        headers={
            "User-Agent": "CivicLedger research crawler/0.1 (+https://github.com/dtrezise/CivicLedger)"
        },
    )
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type")
        suffix = Path(filename_from_url(url)).suffix
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        with handle:
            handle.write(response.read())
        return Path(handle.name), content_type


def download_and_archive_source_document(
    session: Session,
    *,
    source_id: str,
    source_url: str | None = None,
    use_public_sample: bool = False,
    access_acknowledged: bool = False,
) -> SourceDownloadResult:
    plan = build_download_plan(
        source_id,
        source_url=source_url,
        use_public_sample=use_public_sample,
        access_acknowledged=access_acknowledged,
    )
    local_path, content_type = fetch_to_tempfile(plan.source_url)
    try:
        run, raw_document, artifact = archive_manual_source_document(
            session,
            source_id=plan.source_id,
            source_url=plan.source_url,
            local_file=local_path,
            content_type=content_type,
            notes=plan.notes,
            access_acknowledged=access_acknowledged,
        )
    finally:
        local_path.unlink(missing_ok=True)

    raw_document.source_metadata = {
        **(raw_document.source_metadata or {}),
        "download_plan": {
            "access_mode": plan.access_mode,
            "requires_acknowledgement": plan.requires_acknowledgement,
        },
    }
    session.commit()
    session.refresh(raw_document)
    return SourceDownloadResult(
        plan=plan,
        ingestion_run=run,
        raw_document=raw_document,
        parser_artifact=artifact,
    )
