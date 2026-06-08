from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.decision.decision_engine import build_decision
from core.event.state_store import connect, list_actions, list_events


def build_plan() -> dict:
    db_path = ROOT / "state" / "events.db"
    conn = connect(db_path)
    events = list_events(conn)
    decisions = []
    for e in events:
        actions = list_actions(conn, e["event_id"])
        decisions.append(build_decision(e, actions))
    counts = Counter(d["decision"] for d in decisions)
    return {
        "version": "daily_operator_plan_v0_3",
        "db_path": str(db_path.relative_to(ROOT)),
        "event_count": len(events),
        "decision_count": len(decisions),
        "decision_counts": dict(sorted(counts.items())),
        "decisions": decisions,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
            "daemon_started": False,
            "model_called": False,
        },
    }


def render_md(plan: dict) -> str:
    lines = []
    lines.append("# Daily Operator Plan\n\n")
    lines.append(f"- version: `{plan['version']}`\n")
    lines.append(f"- db_path: `{plan['db_path']}`\n")
    lines.append(f"- event_count: {plan['event_count']}\n")
    lines.append(f"- decision_counts: `{json.dumps(plan['decision_counts'], ensure_ascii=False)}`\n")
    sections = [
        ("Official Post", "official_post"),
        ("Reply Or Quote", "reply_or_quote"),
        ("Editor Take", "editor_take"),
        ("Monitor Only", "monitor_only"),
        ("Reject", "reject"),
    ]
    for title, action in sections:
        rows = [d for d in plan["decisions"] if d["decision"] == action]
        lines.append(f"\n## {title}\n")
        if not rows:
            lines.append("- none\n")
            continue
        for d in rows:
            lines.append(f"\n### {d['title']}\n")
            lines.append(f"- event_id: `{d['event_id']}`\n")
            lines.append(f"- status: `{d['status']}`\n")
            lines.append(f"- fact_anchor: `{d['fact_anchor']}`\n")
            lines.append(f"- account: `{d['account']}`\n")
            lines.append(f"- confidence: {d['confidence']}\n")
            lines.append(f"- requires_human: `{str(bool(d['requires_human'])).lower()}`\n")
            lines.append(f"- user_hook: {d['user_hook']}\n")
            lines.append(f"- reason: {d['account_fit_reason']}\n")
            lines.append(f"- publish_window: {d['publish_window']}\n")
            lines.append(f"- expected_metric: `{json.dumps(d['expected_metric'], ensure_ascii=False)}`\n")
            if d.get("dedup_against"):
                lines.append(f"- dedup_against: `{', '.join(str(x) for x in d['dedup_against'])}`\n")
    lines.append("\n## Safety\n")
    for k, v in plan["safety"].items():
        lines.append(f"- {k}: `{str(bool(v)).lower()}`\n")
    return "".join(lines)


def main() -> int:
    plan = build_plan()
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "daily_operator_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (reports / "daily_operator_plan.md").write_text(render_md(plan), encoding="utf-8")
    print(f"[daily_operator] ok decisions={plan['decision_count']} counts={plan['decision_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
