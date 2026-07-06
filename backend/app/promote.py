import argparse
from uuid import UUID

from app.database import SyncSessionLocal
from app.services.promotion import promote_preview_artifact


def main():
    parser = argparse.ArgumentParser(
        description="Promote a reviewed parser preview artifact into filing/trade records."
    )
    parser.add_argument("--artifact-id", required=True, type=UUID)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--person-name", required=True)
    parser.add_argument("--branch", required=True, choices=["Legislative", "Executive", "Judicial"])
    parser.add_argument("--chamber")
    parser.add_argument("--state")
    parser.add_argument("--party")
    parser.add_argument("--office")
    parser.add_argument("--agency")
    parser.add_argument("--court")
    args = parser.parse_args()

    with SyncSessionLocal() as session:
        filing, trades = promote_preview_artifact(
            session,
            preview_artifact_id=args.artifact_id,
            reviewer=args.reviewer,
            person_name=args.person_name,
            branch=args.branch,
            chamber=args.chamber,
            state=args.state,
            party=args.party,
            office=args.office,
            agency=args.agency,
            court=args.court,
        )

    print(f"filing_id={filing.id}")
    print(f"trade_count={len(trades)}")


if __name__ == "__main__":
    main()
