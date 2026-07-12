from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_pages_dataset import (  # noqa: E402
    compact_timeline_official,
    official_involvement_index,
    trade_context_candidates,
)


def test_candidate_ranking_exposes_neutral_score_components():
    trades = [
        {
            "id": "trade-1",
            "date": "2025-05-10",
            "market_reaction": {
                "post_windows": [
                    {"session_count": 5, "benchmark_adjusted_return_pct": -4.0}
                ]
            },
        }
    ]
    relationships = [
        {
            "id": "official-record",
            "date": "2025-05-10",
            "relationship_tier": "direct",
            "relationship_tier_rank": 6,
            "relationship_reasons": ["official recorded vote"],
            "display_default": True,
        },
        {
            "id": "sector-context",
            "date": "2025-05-09",
            "relationship_tier": "sector_context",
            "relationship_tier_rank": 2,
            "relationship_reasons": ["sector scope"],
            "display_default": False,
        },
    ]
    events = {
        "official-record": {"id": "official-record", "source_tier": "official"},
        "sector-context": {"id": "sector-context", "source_tier": "official"},
    }

    trade_context_candidates(relationships, trades, events)

    direct = relationships[0]
    sector = relationships[1]
    assert direct["candidate_rank"] == 1
    assert direct["candidate_score"] > sector["candidate_score"]
    assert direct["candidate_score_components"] == {
        "relationship_specificity": 60,
        "temporal_proximity": 25.0,
        "descriptive_market_movement": 6.0,
    }
    assert direct["max_abs_benchmark_adjusted_post_return_pct"] == 4.0
    assert direct["candidate_basis"] == (
        "source_specificity_temporal_proximity_and_descriptive_market_context"
    )


def test_timeline_partition_hoists_repeated_review_state_without_losing_defaults():
    official = {
        "id": "official-1",
        "stats": {
            "record_status": "official_parser_preview_not_promoted",
            "review_required_before_public_trade": True,
        },
        "trades": [
            {
                "id": "trade-1",
                "record_status": "official_parser_preview_not_promoted",
                "review_required_before_public_trade": True,
                "public_production_trade": False,
                "action": "BUY",
            }
        ],
    }

    compact = compact_timeline_official(official)
    hydrated = {**compact["trade_record_defaults"], **compact["trades"][0]}

    assert "record_status" not in compact["trades"][0]
    assert "review_required_before_public_trade" not in compact["trades"][0]
    assert hydrated["record_status"] == "official_parser_preview_not_promoted"
    assert hydrated["review_required_before_public_trade"] is True
    assert hydrated["public_production_trade"] is False


def test_official_involvement_uses_methodology_to_classify_direct_records():
    indexed = official_involvement_index(
        {
            "methodology": {"direct_relationship_types": ["recorded_vote"]},
            "actors": [{"id": "actor-1", "external_person_id": "congress:A000001"}],
            "relationships": [
                {
                    "id": "relationship-1",
                    "event_id": "event-1",
                    "relationship_type": "recorded_vote",
                    "actor_id": "actor-1",
                    "vote_cast": "Yea",
                }
            ],
        }
    )

    row = indexed[("event-1", "congress:A000001")][0]
    assert row["relationship_class"] == "direct_official_record"
    assert row["vote_cast"] == "Yea"
