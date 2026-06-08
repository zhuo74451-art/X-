from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.event.lifecycle import event_from_hot_engine, recommended_action
from core.event.state_store import connect, get_event, list_actions, list_events, upsert_event


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def load_inputs() -> list[dict[str, Any]]:
    events = read_jsonl(ROOT / "out" / "hot_engine_queues" / "events.jsonl")
    if events:
        return events
    q = read_json(ROOT / "reports" / "x_v2_008_chinese_sharp_test_account_queue.json")
    rows = q.get("READY_FOR_TEST_ACCOUNT") if isinstance(q.get("READY_FOR_TEST_ACCOUNT"), list) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "event_cluster_id": row.get("event_id") or "",
                "cluster_title": row.get("title") or "",
                "cluster_queue": "queue_review",
                "total_score": row.get("x_taste_score") or 70,
                "audience_reach_score": row.get("audience_context_score") or 70,
                "best_source_rank": 2,
                "risk_level": row.get("risk_level") or "low",
                "item_count": 1,
                "source_names": ["x_v2_008_queue"],
                "raw_summary": " ".join(
                    [
                        str(row.get("original_post") or ""),
                        str(row.get("personal_balanced") or ""),
                        str(row.get("personal_sharp") or ""),
                    ]
                ),
                "rule_reason": "fallback_from_x_v2_008_queue",
            }
        )
    return out


def build_payload(events: list[dict[str, Any]], db_path: Path) -> dict[str, Any]:
    conn = connect(db_path)
    updated: list[dict[str, Any]] = []
    for raw in events:
        event_id = str(raw.get("event_cluster_id") or "")
        old = get_event(conn, event_id) if event_id else None
        event = event_from_hot_engine(raw, old)
        upsert_event(conn, event)
        actions = list_actions(conn, event["event_id"])
        event["our_actions_taken"] = actions
        event["recommended_action"] = recommended_action(event, actions)
        updated.append(event)
    all_events = list_events(conn)
    counts = Counter(str(e.get("status") or "unknown") for e in all_events)
    action_counts = Counter(str(e.get("recommended_action") or "unknown") for e in updated)
    return {
        "version": "event_lifecycle_v0_2",
        "db_path": str(db_path.relative_to(ROOT)),
        "input_count": len(events),
        "updated_count": len(updated),
        "total_events": len(all_events),
        "status_counts": dict(sorted(counts.items())),
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "events": updated,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
            "daemon_started": False,
            "model_called": False,
        },
    }


def render_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Event Lifecycle Report\n\n")
    lines.append(f"- version: `{payload['version']}`\n")
    lines.append(f"- db_path: `{payload['db_path']}`\n")
    lines.append(f"- input_count: {payload['input_count']}\n")
    lines.append(f"- updated_count: {payload['updated_count']}\n")
    lines.append(f"- total_events: {payload['total_events']}\n")
    lines.append(f"- status_counts: `{json.dumps(payload['status_counts'], ensure_ascii=False)}`\n")
    lines.append(f"- recommended_action_counts: `{json.dumps(payload['recommended_action_counts'], ensure_ascii=False)}`\n")
    lines.append("\n## Events\n")
    for e in payload.get("events", []):
        lines.append(f"\n### {e.get('title') or e.get('event_id')}\n")
        lines.append(f"- event_id: `{e.get('event_id')}`\n")
        lines.append(f"- status: `{e.get('status')}`\n")
        lines.append(f"- fact_anchor: `{e.get('fact_anchor')}`\n")
        lines.append(f"- heat_score: {e.get('heat_score')}\n")
        lines.append(f"- heat_velocity: {e.get('heat_velocity')}\n")
        lines.append(f"- source_diversity: {e.get('source_diversity')}\n")
        lines.append(f"- signal_count: {e.get('signal_count')}\n")
        lines.append(f"- recommended_action: `{e.get('recommended_action')}`\n")
        lines.append(f"- actions_taken: {len(e.get('our_actions_taken') or [])}\n")
        if e.get("risk_flags"):
            lines.append(f"- risk_flags: `{', '.join(e.get('risk_flags') or [])}`\n")
    lines.append("\n## Safety\n")
    for k, v in payload.get("safety", {}).items():
        lines.append(f"- {k}: `{str(bool(v)).lower()}`\n")
    return "".join(lines)


def main() -> int:
    inputs = load_inputs()
    db_path = ROOT / "state" / "events.db"
    payload = build_payload(inputs, db_path)
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "event_lifecycle_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (reports / "event_lifecycle_report.md").write_text(render_md(payload), encoding="utf-8")
    print(f"[event_update] ok updated={payload['updated_count']} total={payload['total_events']} db={db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
