import argparse

from app.database import SyncSessionLocal
from app.parsers import get_supported_source_ids
from app.services.source_clients import download_and_archive_source_document


def main():
    parser = argparse.ArgumentParser(
        description="Download and archive a public official-source disclosure document."
    )
    parser.add_argument("--source-id", required=True, choices=get_supported_source_ids())
    parser.add_argument("--url", help="Specific public document URL to download.")
    parser.add_argument(
        "--use-public-sample",
        action="store_true",
        help="Use the configured public sample URL for this source, when available.",
    )
    parser.add_argument(
        "--access-acknowledged",
        action="store_true",
        help="Record that a human reviewed and acknowledged source access/use restrictions.",
    )
    args = parser.parse_args()

    with SyncSessionLocal() as session:
        result = download_and_archive_source_document(
            session,
            source_id=args.source_id,
            source_url=args.url,
            use_public_sample=args.use_public_sample,
            access_acknowledged=args.access_acknowledged,
        )

    print(f"source_id={result.plan.source_id}")
    print(f"source_url={result.plan.source_url}")
    print(f"ingestion_run_id={result.ingestion_run.id}")
    print(f"raw_document_id={result.raw_document.id}")
    print(f"parser_artifact_id={result.parser_artifact.id}")


if __name__ == "__main__":
    main()
