from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.event.lifecycle import event_from_hot_engine, recommended_action
from core.event.state_store import add_action, connect, get_event, list_actions, list_events, upsert_event


def sample_raw(score: int = 82) -> dict:
    return {
        "event_cluster_id": "evt_test_stablecoin_payment",
        "cluster_title": "Meta pays creators in USDC",
        "total_score": score,
        "best_source_rank": 2,
        "risk_level": "low",
        "item_count": 2,
        "source_names": ["coindesk", "coinmeta"],
        "raw_summary": "Meta uses USDC for creator payment. Stablecoin real use case.",
    }


def test_event_upsert_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "events.db")
    event = event_from_hot_engine(sample_raw(), None)
    upsert_event(conn, event)
    upsert_event(conn, event)
    rows = list_events(conn)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "evt_test_stablecoin_payment"


def test_hot_multisource_event_recommends_official_post(tmp_path: Path) -> None:
    conn = connect(tmp_path / "events.db")
    event = event_from_hot_engine(sample_raw(86), None)
    upsert_event(conn, event)
    actions = list_actions(conn, event["event_id"])
    assert event["status"] == "hot"
    assert event["fact_anchor"] == "multi_source"
    assert recommended_action(event, actions) == "official_post"


def test_previous_official_post_prevents_repeat(tmp_path: Path) -> None:
    conn = connect(tmp_path / "events.db")
    event = event_from_hot_engine(sample_raw(86), None)
    upsert_event(conn, event)
    add_action(
        conn,
        {
            "action_id": "act_1",
            "event_id": event["event_id"],
            "action_type": "official_post",
            "account": "coinmeta_official",
            "publish_status": "published",
            "reason": "already posted",
            "created_at": event["updated_at"],
        },
    )
    repeated = event_from_hot_engine(sample_raw(87), get_event(conn, event["event_id"]))
    actions = list_actions(conn, event["event_id"])
    assert recommended_action(repeated, actions) == "reject"


def test_lower_score_moves_to_cooling_or_peaking(tmp_path: Path) -> None:
    conn = connect(tmp_path / "events.db")
    first = event_from_hot_engine(sample_raw(86), None)
    upsert_event(conn, first)
    second = event_from_hot_engine(sample_raw(66), get_event(conn, first["event_id"]))
    assert second["heat_velocity"] < 0
    assert second["status"] in {"peaking", "cooling"}
