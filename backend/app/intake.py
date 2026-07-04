import argparse
from pathlib import Path

from app.database import SyncSessionLocal
from app.parsers import get_supported_source_ids
from app.services.intake import archive_manual_source_document


def main():
    parser = argparse.ArgumentParser(
        description="Archive an official-source disclosure artifact before parsing."
    )
    parser.add_argument("--source-id", required=True, choices=get_supported_source_ids())
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--content-type")
    parser.add_argument("--notes")
    parser.add_argument(
        "--access-acknowledged",
        action="store_true",
        help="Record that a human acknowledged source access/use restrictions.",
    )
    args = parser.parse_args()

    with SyncSessionLocal() as session:
        run, raw_document, artifact = archive_manual_source_document(
            session,
            source_id=args.source_id,
            source_url=args.source_url,
            local_file=args.file,
            content_type=args.content_type,
            notes=args.notes,
            access_acknowledged=args.access_acknowledged,
        )

    print(f"ingestion_run_id={run.id}")
    print(f"raw_document_id={raw_document.id}")
    print(f"parser_artifact_id={artifact.id}")
    print(f"storage_uri={raw_document.storage_uri}")


if __name__ == "__main__":
    main()
