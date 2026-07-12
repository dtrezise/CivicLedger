import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Filing, ParserArtifact, Person, RawDocument, Trade


VALUE_RANGE_DEFAULTS = {
    "$1,001 - $15,000": (Decimal("1001"), Decimal("15000")),
    "$15,001 - $50,000": (Decimal("15001"), Decimal("50000")),
    "$50,001 - $100,000": (Decimal("50001"), Decimal("100000")),
    "$100,001 - $250,000": (Decimal("100001"), Decimal("250000")),
    "$250,001 - $500,000": (Decimal("250001"), Decimal("500000")),
    "$500,001 - $1,000,000": (Decimal("500001"), Decimal("1000000")),
}
OFFICIAL_DISCLOSURE_HOSTS = {
    "house-financial-disclosure": {"disclosures-clerk.house.gov"},
    "senate-public-financial-disclosure": {
        "efdsearch.senate.gov",
        "efd-media-public.senate.gov",
    },
    "oge-individual-disclosures": {"oge.gov", "www.oge.gov"},
    "judicial-financial-disclosure": {"pub.jefs.uscourts.gov"},
}
REQUIRED_PREVIEW_FIELDS = {
    "action",
    "asset_display_name",
    "document_id",
    "official_id",
    "reported_date",
    "source_file_hash",
    "source_url",
    "trade_date",
    "value_range_label",
}


def parse_date(value: str | None, fallback: date | None = None) -> date:
    if value:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return fallback or date.today()


def parse_value_range(label: str) -> tuple[Decimal | None, Decimal | None]:
    if label in VALUE_RANGE_DEFAULTS:
        return VALUE_RANGE_DEFAULTS[label]
    return None, None


def decimal_confidence(row: dict, fallback: str = "0.85") -> Decimal:
    try:
        return Decimal(str(row.get("confidence") or fallback))
    except Exception:
        return Decimal(fallback)


def disclosure_lag(trade_date: date, reported_date: date) -> int:
    return (reported_date - trade_date).days


def _valid_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "").lower()))


def _official_source_url(source_id: str | None, source_url: str | None) -> bool:
    parsed = urlparse(str(source_url or ""))
    return (
        parsed.scheme == "https"
        and parsed.netloc in OFFICIAL_DISCLOSURE_HOSTS.get(str(source_id or ""), set())
    )


def evaluate_parser_preview_record(transaction: dict, document: dict) -> dict:
    """Evaluate a static parser-preview row without changing or promoting it."""
    source_id = document.get("source_id") or transaction.get("source_id")
    source_hash = document.get("file_hash") or document.get("source_page_sha256")
    flags = sorted(set(transaction.get("data_quality_flags") or []))
    field_confidence = transaction.get("field_confidence") or {}
    required_confidence = [
        field_confidence.get(field)
        for field in ("transaction_date", "asset", "transaction_type", "amount")
        if field in field_confidence
    ]
    review_evidence = transaction.get("review_evidence") or document.get("review_evidence") or {}
    required_fields_present = all(transaction.get(field) not in (None, "") for field in REQUIRED_PREVIEW_FIELDS)
    hash_matches = (
        _valid_sha256(source_hash)
        and transaction.get("source_file_hash") == source_hash
    )
    source_criteria = {
        "official_source_tier": document.get("source_tier") == "official"
        and transaction.get("source_tier") == "official",
        "official_source_url": _official_source_url(source_id, transaction.get("source_url"))
        and transaction.get("source_url") == document.get("source_url"),
        "source_hash_matches_document": hash_matches,
        "identity_matched": document.get("match_status") == "matched"
        and transaction.get("official_id") == document.get("official_id"),
        "parser_preview_status": document.get("parser_status") == "parser_preview"
        and transaction.get("public_production_trade") is False,
        "required_fields_present": required_fields_present,
        "source_locator_present": transaction.get("source_page") is not None
        or transaction.get("source_row") is not None,
        "minimum_parser_confidence": float(transaction.get("parsing_confidence") or 0) >= 0.9,
        "minimum_required_field_confidence": bool(required_confidence)
        and min(float(value or 0) for value in required_confidence) >= 0.9,
        "no_quality_flags": not flags,
        "not_duplicate_candidate": transaction.get("duplicate_candidate") is not True,
    }
    human_criteria = {
        "explicit_public_production_decision": review_evidence.get("decision")
        == "approve_public_production",
        "reviewer_identified": bool(review_evidence.get("reviewed_by")),
        "review_timestamp_present": bool(review_evidence.get("reviewed_at")),
        "review_hash_matches_source": review_evidence.get("source_file_hash") == source_hash,
        "review_document_matches_source": review_evidence.get("document_id")
        == document.get("document_id"),
    }
    criteria = {**source_criteria, **human_criteria}
    failed = sorted(name for name, passed in criteria.items() if not passed)
    source_pass = all(source_criteria.values())
    return {
        "eligible_for_public_production": not failed,
        "automated_source_criteria_pass": source_pass,
        "criteria": criteria,
        "failed_criteria": failed,
        "quality_flags": flags,
        "review_evidence_present": bool(review_evidence),
    }


def build_parser_preview_review_dataset(
    documents: list[dict],
    transactions: list[dict],
    *,
    generated_at: str,
    queue_limit: int = 100,
) -> dict:
    """Systematically evaluate parser previews and emit only evidence-qualified promotions."""
    documents_by_id = {document["document_id"]: document for document in documents}
    decisions = []
    promotions = []
    failed_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    source_pass_count = 0
    missing_document_count = 0
    for transaction in transactions:
        document = documents_by_id.get(transaction.get("document_id"))
        if not document:
            missing_document_count += 1
            failed_counts["document_evidence_missing"] += 1
            continue
        evaluation = evaluate_parser_preview_record(transaction, document)
        source_counts[str(document.get("source_id"))] += 1
        failed_counts.update(evaluation["failed_criteria"])
        source_pass_count += int(evaluation["automated_source_criteria_pass"])
        decision = {
            "record_id": transaction["id"],
            "document_id": document["document_id"],
            "source_id": document.get("source_id"),
            "official_id": transaction.get("official_id"),
            "filing_date": document.get("filing_date"),
            "source_url": transaction.get("source_url"),
            "source_file_hash": transaction.get("source_file_hash"),
            "parsing_confidence": transaction.get("parsing_confidence"),
            "decision": (
                "promote_public_production"
                if evaluation["eligible_for_public_production"]
                else "hold_for_evidence_review"
            ),
            **evaluation,
        }
        decisions.append(decision)
        if evaluation["eligible_for_public_production"]:
            promotions.append(
                {
                    **transaction,
                    "promotion_id": f"production-{transaction['id']}",
                    "review_status": "reviewed_public_production",
                    "record_status": "reviewed_public_production",
                    "public_production_trade": True,
                    "review_required_before_public_trade": False,
                }
            )

    queue = sorted(
        (row for row in decisions if row["automated_source_criteria_pass"] and not row["eligible_for_public_production"]),
        key=lambda row: (
            -float(row.get("parsing_confidence") or 0),
            -date.fromisoformat(row["filing_date"]).toordinal(),
            row["record_id"],
        ),
    )[:queue_limit]
    evidence_review_candidate_count = sum(
        row["automated_source_criteria_pass"] and not row["eligible_for_public_production"]
        for row in decisions
    )
    return {
        "generated_at": generated_at,
        "schema_version": "reviewed-disclosure-promotions-v2",
        "context_label": (
            "Systematic parser-preview evidence review. A row is promoted only when official-source, "
            "hash, identity, parser-quality, and explicit human review criteria all pass."
        ),
        "promotion_policy": {
            "minimum_parser_confidence": 0.9,
            "minimum_required_field_confidence": 0.9,
            "explicit_review_decision": "approve_public_production",
            "source_hash_and_document_id_must_match_review_evidence": True,
            "quality_flags_or_duplicate_candidates_block_promotion": True,
        },
        "summary": {
            "parser_preview_record_count": len(transactions),
            "evaluated_record_count": len(decisions),
            "missing_document_evidence_count": missing_document_count,
            "automated_source_criteria_pass_count": source_pass_count,
            "evidence_review_candidate_count": evidence_review_candidate_count,
            "evidence_review_queue_count": len(queue),
            "evidence_review_queue_limit": queue_limit,
            "eligible_public_production_count": len(promotions),
            "public_production_trade_count": len(promotions),
            "reviewed_fixture_promotion_count": 0,
            "source_record_counts": dict(sorted(source_counts.items())),
            "failed_criteria_counts": dict(sorted(failed_counts.items())),
            "review_required_before_public_trade": True,
        },
        "evidence_review_queue": queue,
        "promotions": sorted(promotions, key=lambda row: row["promotion_id"]),
    }


def evaluate_preview_artifact_evidence(
    preview: ParserArtifact,
    raw_document: RawDocument,
    *,
    reviewer: str,
    person_name: str | None = None,
    branch: str | None = None,
) -> list[str]:
    """Return deterministic promotion blockers for a database preview artifact."""
    parser_output = preview.parser_output or {}
    transactions = parser_output.get("transactions") or []
    evidence = parser_output.get("review_evidence") or {}
    blockers = []
    if not raw_document.provenance_complete:
        blockers.append("raw_document_provenance_incomplete")
    if not _valid_sha256(raw_document.file_hash):
        blockers.append("raw_document_hash_invalid")
    if preview.source_id != raw_document.retrieval_source:
        blockers.append("source_id_mismatch")
    if not _official_source_url(preview.source_id, raw_document.source_url):
        blockers.append("source_url_not_official")
    if not transactions:
        blockers.append("preview_has_no_transactions")
    if parser_output.get("normalized_record_count") not in (None, len(transactions)):
        blockers.append("normalized_record_count_mismatch")
    required_transaction_fields = ("asset", "transaction_type", "transaction_date", "amount")
    for row_number, row in enumerate(transactions, start=1):
        if any(row.get(field) in (None, "") for field in required_transaction_fields):
            blockers.append(f"transaction_{row_number}_required_fields_missing")
        if decimal_confidence(row, fallback="0") < Decimal("0.9"):
            blockers.append(f"transaction_{row_number}_confidence_below_threshold")
    if evidence.get("decision") != "approve_public_production":
        blockers.append("explicit_public_production_decision_missing")
    if evidence.get("reviewed_by") != reviewer:
        blockers.append("reviewer_attestation_mismatch")
    if not evidence.get("reviewed_at"):
        blockers.append("review_timestamp_missing")
    if evidence.get("raw_document_id") != str(raw_document.id):
        blockers.append("review_raw_document_id_mismatch")
    if evidence.get("source_file_hash") != raw_document.file_hash:
        blockers.append("review_source_hash_mismatch")
    if evidence.get("transaction_count") != len(transactions):
        blockers.append("review_transaction_count_mismatch")
    if person_name is not None and evidence.get("person_name") != person_name:
        blockers.append("review_person_name_mismatch")
    if branch is not None and evidence.get("branch") != branch:
        blockers.append("review_branch_mismatch")
    return sorted(blockers)


def get_or_create_person(
    session: Session,
    *,
    full_name: str,
    branch: str,
    chamber: str | None = None,
    state: str | None = None,
    party: str | None = None,
    office: str | None = None,
    agency: str | None = None,
    court: str | None = None,
) -> Person:
    existing = session.execute(
        select(Person).where(Person.full_name == full_name, Person.branch == branch)
    ).scalar_one_or_none()
    if existing:
        return existing

    person = Person(
        id=uuid4(),
        full_name=full_name,
        branch=branch,
        chamber=chamber,
        state=state,
        party=party,
        office=office,
        agency=agency,
        court=court,
        service_start=date.today(),
    )
    session.add(person)
    session.flush()
    return person


def promote_preview_artifact(
    session: Session,
    *,
    preview_artifact_id: UUID,
    reviewer: str,
    person_name: str,
    branch: str,
    chamber: str | None = None,
    state: str | None = None,
    party: str | None = None,
    office: str | None = None,
    agency: str | None = None,
    court: str | None = None,
) -> tuple[Filing, list[Trade]]:
    preview = session.get(ParserArtifact, preview_artifact_id)
    if not preview:
        raise ValueError(f"Parser artifact not found: {preview_artifact_id}")
    if preview.artifact_type != "preview":
        raise ValueError("Only preview parser artifacts can be promoted.")

    raw_document = session.get(RawDocument, preview.raw_document_id)
    if not raw_document:
        raise ValueError(f"Raw document not found: {preview.raw_document_id}")

    parser_output = preview.parser_output or {}
    transactions = parser_output.get("transactions") or []
    if not transactions:
        raise ValueError("Preview artifact contains no parsed transactions to promote.")
    blockers = evaluate_preview_artifact_evidence(
        preview,
        raw_document,
        reviewer=reviewer,
        person_name=person_name,
        branch=branch,
    )
    if blockers:
        raise ValueError(
            "Preview does not satisfy production promotion criteria: " + ", ".join(blockers)
        )

    person = get_or_create_person(
        session,
        full_name=person_name,
        branch=branch,
        chamber=chamber,
        state=state,
        party=party,
        office=office,
        agency=agency,
        court=court,
    )

    filed_date = parse_date(parser_output.get("filing_date"), fallback=raw_document.retrieved_at.date())
    filing = Filing(
        id=uuid4(),
        person_id=person.id,
        filing_type=parser_output.get("report_type") or parser_output.get("document_type") or "disclosure",
        filed_date=filed_date,
        source_url=raw_document.source_url,
        retrieved_at=raw_document.retrieved_at,
        file_hash=raw_document.file_hash,
        retrieval_source=raw_document.retrieval_source,
        raw_document_id=raw_document.id,
    )
    session.add(filing)
    session.flush()

    filing_artifact = ParserArtifact(
        id=uuid4(),
        source_id=preview.source_id,
        raw_document_id=raw_document.id,
        filing_id=filing.id,
        artifact_type="filing",
        text_span={},
        parser_output={
            "reviewed_by": reviewer,
            "promoted_from_artifact_id": str(preview.id),
            "person_name": person_name,
            "branch": branch,
            "record_status": "reviewed_promoted",
            "confidence_label": "Reviewed promoted filing",
            "review_evidence": parser_output.get("review_evidence"),
        },
        confidence=preview.confidence,
    )
    session.add(filing_artifact)

    trades = []
    for row in transactions:
        trade_date = parse_date(row.get("transaction_date"), fallback=filed_date)
        min_value, max_value = parse_value_range(row.get("amount") or "")
        confidence = decimal_confidence(row)
        trade = Trade(
            id=uuid4(),
            person_id=person.id,
            filing_id=filing.id,
            trade_date=trade_date,
            reported_date=filed_date,
            action=row.get("transaction_type") or "OTHER",
            raw_asset_text=row.get("asset") or "Unknown asset",
            asset_display_name=row.get("asset") or "Unknown asset",
            ticker=row.get("ticker"),
            asset_class="unknown",
            value_range_label=row.get("amount") or "Unknown",
            value_range_min=min_value,
            value_range_max=max_value,
            disclosure_lag_days=disclosure_lag(trade_date, filed_date),
            parsing_confidence=confidence,
            asset_match_confidence=None,
        )
        session.add(trade)
        session.flush()
        trades.append(trade)

        session.add(
            ParserArtifact(
                id=uuid4(),
                source_id=preview.source_id,
                raw_document_id=raw_document.id,
                filing_id=filing.id,
                trade_id=trade.id,
                artifact_type="trade",
                page_number=None,
                row_number=row.get("row_number"),
                text_span={"text": row.get("comment") or row.get("asset") or ""},
                parser_output={
                    "reviewed_by": reviewer,
                    "promoted_from_artifact_id": str(preview.id),
                    "record_status": "reviewed_promoted",
                    "confidence_label": "Reviewed promoted trade",
                    "review_evidence": parser_output.get("review_evidence"),
                    "row": row,
                },
                confidence=confidence,
            )
        )

    session.commit()
    session.refresh(filing)
    for trade in trades:
        session.refresh(trade)
    return filing, trades


def rollback_promoted_filing(
    session: Session,
    *,
    filing_id: UUID,
    reviewer: str,
    reason: str,
) -> dict:
    filing = session.get(Filing, filing_id)
    if not filing:
        raise ValueError(f"Filing not found: {filing_id}")

    promotion_artifact = session.execute(
        select(ParserArtifact).where(
            ParserArtifact.filing_id == filing_id,
            ParserArtifact.artifact_type == "filing",
        )
    ).scalar_one_or_none()
    if not promotion_artifact or not (
        promotion_artifact.parser_output or {}
    ).get("promoted_from_artifact_id"):
        raise ValueError("Only filings promoted from reviewed parser previews can be rolled back.")

    trade_ids = [
        trade_id
        for trade_id in session.execute(select(Trade.id).where(Trade.filing_id == filing_id)).scalars()
    ]
    artifact_count = session.execute(
        select(ParserArtifact).where(ParserArtifact.filing_id == filing_id)
    ).scalars().all()

    preview_id = promotion_artifact.parser_output.get("promoted_from_artifact_id")
    if preview_id:
        preview = session.get(ParserArtifact, UUID(preview_id))
        if preview:
            preview.parser_output = {
                **(preview.parser_output or {}),
                "review_status": "rolled_back",
                "rollback": {
                    "reviewed_by": reviewer,
                    "reason": reason,
                    "rolled_back_filing_id": str(filing_id),
                    "rolled_back_at": datetime.utcnow().isoformat(),
                },
            }

    session.execute(delete(ParserArtifact).where(ParserArtifact.filing_id == filing_id))
    session.execute(delete(Trade).where(Trade.filing_id == filing_id))
    session.delete(filing)
    session.commit()

    return {
        "filing_id": str(filing_id),
        "reviewed_by": reviewer,
        "reason": reason,
        "deleted_trade_count": len(trade_ids),
        "deleted_artifact_count": len(artifact_count),
    }


def supersede_filing(
    session: Session,
    *,
    filing_id: UUID,
    superseded_by_filing_id: UUID,
    reviewer: str,
    reason: str,
) -> Filing:
    filing = session.get(Filing, filing_id)
    replacement = session.get(Filing, superseded_by_filing_id)
    if not filing:
        raise ValueError(f"Filing not found: {filing_id}")
    if not replacement:
        raise ValueError(f"Replacement filing not found: {superseded_by_filing_id}")
    if filing.id == replacement.id:
        raise ValueError("A filing cannot supersede itself.")

    filing.superseded_by_filing_id = replacement.id
    raw_document_id = filing.raw_document_id or replacement.raw_document_id
    if raw_document_id:
        session.add(
            ParserArtifact(
                id=uuid4(),
                source_id=filing.retrieval_source,
                raw_document_id=raw_document_id,
                filing_id=filing.id,
                artifact_type="warning",
                text_span={},
                parser_output={
                    "review_status": "superseded",
                    "superseded_by_filing_id": str(replacement.id),
                    "reviewed_by": reviewer,
                    "reason": reason,
                    "reviewed_at": datetime.utcnow().isoformat(),
                },
                confidence=None,
            )
        )
    session.commit()
    session.refresh(filing)
    return filing
