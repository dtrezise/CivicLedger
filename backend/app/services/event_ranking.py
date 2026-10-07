"""Pure trade-event ranking logic shared by data builds and release evaluation."""

from __future__ import annotations

from datetime import date


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def trade_context_candidates(
    relationships: list[dict],
    trades: list[dict],
    events_by_id: dict[str, dict],
    window_days: int = 45,
    cluster_days: int = 14,
) -> None:
    """Rank neutral context candidates near clusters of disclosed transactions.

    This function mutates ``relationships`` by design. It deliberately depends only
    on its arguments so release gates can evaluate ranking without initializing the
    application database or importing the static-site builder.
    """

    def market_movement_magnitude(trade: dict) -> float:
        reaction = trade.get("market_reaction") or {}
        values = [
            abs(float(window["benchmark_adjusted_return_pct"]))
            for window in reaction.get("post_windows", [])
            if window.get("benchmark_adjusted_return_pct") is not None
        ]
        return max(values, default=0.0)

    def source_specificity(event: dict) -> tuple[int, str]:
        source_tier = event.get("source_tier")
        if source_tier == "official":
            return (10, "official public record")
        if source_tier in {"news_publisher", "news_publisher_via_aggregator"}:
            return (5, "attributed publisher report")
        return (0, "general attributed context")

    dated_trades = sorted(
        [trade for trade in trades if trade.get("date")],
        key=lambda row: (row["date"], row["id"]),
    )
    if not dated_trades:
        return

    groups: list[list[dict]] = []
    for trade in dated_trades:
        if not groups or (
            _parse_iso_date(trade["date"]) - _parse_iso_date(groups[-1][-1]["date"])
        ).days > cluster_days:
            groups.append([])
        groups[-1].append(trade)

    selected_ids = set()
    for group in groups:
        start = _parse_iso_date(group[0]["date"])
        end = _parse_iso_date(group[-1]["date"])
        buckets = {"before": [], "during": [], "after": []}
        for relationship in relationships:
            event_date = _parse_iso_date(relationship["date"])
            if event_date < start:
                bucket = "before"
                distance = (start - event_date).days
            elif event_date > end:
                bucket = "after"
                distance = (event_date - end).days
            else:
                bucket = "during"
                distance = 0
            if distance > window_days:
                continue

            tier = relationship["relationship_tier"]
            event = events_by_id.get(relationship["id"], {})
            eligible = relationship["relationship_tier_rank"] >= 3
            eligible = eligible or (tier in {"asset_specific", "jurisdictional"} and distance <= 30)
            eligible = eligible or (tier == "sector_context" and distance <= 14)
            eligible = eligible or (tier == "general_macro" and distance <= 7)
            eligible = eligible or (
                tier == "general_context"
                and event.get("editor_status") == "curated"
                and distance <= 14
            )
            if not eligible:
                continue
            source_bonus, _ = source_specificity(event)
            movement_bonus = min(
                40,
                round(max((market_movement_magnitude(trade) for trade in group), default=0) * 2),
            )
            score = (
                relationship["relationship_tier_rank"] * 100
                - distance * 2
                + (15 if event.get("editor_status") == "curated" else 0)
                + source_bonus
                + movement_bonus
            )
            buckets[bucket].append((score, -distance, relationship["date"], relationship["id"]))

        for bucket, limit in (("during", 2), ("before", 2), ("after", 2)):
            candidates = sorted(buckets[bucket], reverse=True)[:limit]
            selected_ids.update(candidate[-1] for candidate in candidates)

    for relationship in relationships:
        if relationship["id"] not in selected_ids:
            continue
        event_date = _parse_iso_date(relationship["date"])
        nearby = []
        for trade in dated_trades:
            days_from_trade = (event_date - _parse_iso_date(trade["date"])).days
            if abs(days_from_trade) <= window_days:
                nearby.append((abs(days_from_trade), days_from_trade, trade["date"], trade["id"]))
        nearby.sort()
        nearest_days = nearby[0][1]
        if nearest_days == 0:
            timing_reason = "same day as a disclosed transaction"
        elif nearest_days > 0:
            timing_reason = f"{nearest_days} days after the nearest disclosed transaction"
        else:
            timing_reason = f"{abs(nearest_days)} days before the nearest disclosed transaction"
        relationship["trade_context_candidate"] = True
        relationship["trade_context_methodology"] = "trade-window-v3"
        relationship["candidate_basis"] = (
            "source_specificity_temporal_proximity_and_descriptive_market_context"
        )
        relationship["nearest_trade_days"] = nearest_days
        relationship["nearby_trade_count"] = len(nearby)
        relationship["nearby_trade_ids"] = [item[3] for item in nearby[:12]]
        event = events_by_id.get(relationship["id"], {})
        source_bonus, source_label = source_specificity(event)
        nearby_trade_ids = set(relationship["nearby_trade_ids"])
        movement_magnitude = max(
            (
                market_movement_magnitude(trade)
                for trade in dated_trades
                if trade["id"] in nearby_trade_ids
            ),
            default=0.0,
        )
        relationship_score = min(60, relationship["relationship_tier_rank"] * 10 + source_bonus)
        temporal_score = round(25 * (1 - min(abs(nearest_days), window_days) / window_days), 1)
        market_score = round(min(15, movement_magnitude * 1.5), 1)
        relationship["candidate_score"] = round(
            relationship_score + temporal_score + market_score,
            1,
        )
        relationship["candidate_score_components"] = {
            "relationship_specificity": relationship_score,
            "temporal_proximity": temporal_score,
            "descriptive_market_movement": market_score,
        }
        relationship["source_specificity_label"] = source_label
        relationship["max_abs_benchmark_adjusted_post_return_pct"] = round(
            movement_magnitude,
            4,
        )
        relationship["relationship_reasons"] = [
            *relationship["relationship_reasons"],
            timing_reason,
        ]
        relationship["display_default"] = True

    ranked = sorted(
        (row for row in relationships if row.get("trade_context_candidate")),
        key=lambda row: (-row.get("candidate_score", 0), row["date"], row["id"]),
    )
    for rank, relationship in enumerate(ranked, start=1):
        relationship["candidate_rank"] = rank
        relationship["display_default"] = rank <= 24
