from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.feedback.learning_report import render_markdown, summarize_metrics
from core.feedback.metrics_store import connect, list_metrics, metrics_by_template


def main() -> int:
    db_path = ROOT / "state" / "post_metrics.db"
    conn = connect(db_path)
    metrics = list_metrics(conn)
    by_template = metrics_by_template(conn)
    summary = summarize_metrics(metrics, by_template)
    summary["version"] = "weekly_learning_report_v0_4"
    summary["db_path"] = str(db_path.relative_to(ROOT))
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "weekly_learning_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (reports / "weekly_learning_report.md").write_text(render_markdown(summary), encoding="utf-8")
    print(f"[weekly_learning] ok posts={summary['post_count']} avg_er={summary['avg_engagement_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
