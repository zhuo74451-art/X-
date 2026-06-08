from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_metrics(metrics: list[dict[str, Any]], by_template: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(metrics)
    drift = Counter(str(m.get("self_score_vs_real") or "unknown") for m in metrics)
    avg_er = round(sum(float(m.get("engagement_rate") or 0) for m in metrics) / total, 6) if total else 0.0
    avg_real = round(sum(float(m.get("real_score") or 0) for m in metrics) / total, 2) if total else 0.0
    return {
        "post_count": total,
        "avg_engagement_rate": avg_er,
        "avg_real_score": avg_real,
        "self_score_vs_real_counts": dict(sorted(drift.items())),
        "templates": by_template,
        "suggestions": build_suggestions(metrics, by_template),
    }


def build_suggestions(metrics: list[dict[str, Any]], by_template: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    overrated = [m for m in metrics if m.get("self_score_vs_real") == "overrated"]
    if overrated:
        out.append(f"{len(overrated)} posts were overrated: lower decision confidence for similar topics until real data improves.")
    for tpl in by_template:
        sample = int(tpl.get("sample_size") or 0)
        er = float(tpl.get("avg_engagement_rate") or 0)
        tid = tpl.get("template_id")
        if sample >= 3 and er >= 0.03:
            out.append(f"Template {tid} looks promising: consider marking it validated after manual review.")
        if sample >= 3 and er < 0.01:
            out.append(f"Template {tid} underperformed: keep it testing or deprecate it.")
    if not out:
        out.append("Not enough real metrics yet. Keep assisted/manual feedback collection before enabling automation.")
    return out


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Weekly Learning Report\n\n")
    lines.append(f"- post_count: {summary.get('post_count')}\n")
    lines.append(f"- avg_engagement_rate: {summary.get('avg_engagement_rate')}\n")
    lines.append(f"- avg_real_score: {summary.get('avg_real_score')}\n")
    lines.append(f"- self_score_vs_real_counts: `{summary.get('self_score_vs_real_counts')}`\n")
    lines.append("\n## Template Performance\n")
    templates = summary.get("templates") or []
    if not templates:
        lines.append("- no template metrics yet\n")
    for tpl in templates:
        lines.append(f"- `{tpl.get('template_id')}` account={tpl.get('account')} sample={tpl.get('sample_size')} avg_er={tpl.get('avg_engagement_rate')} avg_real={tpl.get('avg_real_score')}\n")
    lines.append("\n## Rule Suggestions\n")
    for s in summary.get("suggestions") or []:
        lines.append(f"- {s}\n")
    return "".join(lines)
