from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rules.event_cluster import cluster_hot_inputs
from rules.hot_engine_rulebook import evaluate_event


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_from_sample(item: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "input_id": f"offline_{idx}",
        "source_platform": "internal_db",
        "source_name": str(item.get("source_name") or "").strip(),
        "source_type": str(item.get("input_type") or "").strip(),
        "content_type": str(item.get("input_type") or "").strip(),
        "title": str(item.get("raw_text") or "").strip()[:60].strip(),
        "short_title": "",
        "raw_text": str(item.get("raw_text") or "").strip(),
        "source_url": str(item.get("source_url") or "").strip(),
        "raw_title": "",
        "raw_author": "",
        "received_at": "",
        "published_at": "",
        "event_fingerprint": "",
        "pipeline_stage": "",
        "category": "",
    }


def _export_queue_md(path: Path, *, title: str, events: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append(f"# {title}\n")
    lines.append(f"- Exported at (UTC): {_utc_now_iso()}\n")
    lines.append(f"- Events: {len(events)}\n")

    for idx, e in enumerate(events, start=1):
        lines.append("\n---\n")
        lines.append(f"## Event {idx}\n")
        lines.append(f"- event_cluster_id: {e.get('event_cluster_id')}\n")
        lines.append(f"- cluster_title: {e.get('cluster_title')}\n")
        lines.append(f"- cluster_queue: {e.get('cluster_queue')}\n")
        lines.append(f"- topic_priority: {e.get('topic_priority')}\n")
        lines.append(f"- audience_reach_score: {e.get('audience_reach_score')}\n")
        lines.append(f"- source_score: {e.get('source_score')}\n")
        lines.append(f"- heat_score: {e.get('heat_score')}\n")
        lines.append(f"- fact_score: {e.get('fact_score')}\n")
        lines.append(f"- content_score: {e.get('content_score')}\n")
        lines.append(f"- angle_score: {e.get('angle_score')}\n")
        lines.append(f"- total_score: {e.get('total_score')}\n")
        lines.append(f"- rule_reason: {e.get('rule_reason')}\n")
        lines.append(f"- best_source: {e.get('best_source')}\n")
        hss = e.get("hot_signal_sources")
        if isinstance(hss, list):
            lines.append(f"- hot_signal_sources: {', '.join([str(x) for x in hss if str(x).strip()])}\n")
        lines.append(f"- item_count: {e.get('item_count')}\n")
        ids = e.get("included_tweet_ids")
        if isinstance(ids, list):
            lines.append(f"- included_tweet_ids: {', '.join([str(x) for x in ids if str(x).strip()])}\n")
        mf = e.get("missing_facts")
        if isinstance(mf, list) and mf:
            lines.append("- missing_facts:\n")
            for x in mf[:8]:
                lines.append(f"  - {_clip(str(x), 180)}\n")
        lines.append("\n### 原始素材摘要\n\n```text\n")
        lines.append(_clip(str(e.get("cluster_title") or ""), 200) + "\n")
        lines.append(_clip(str(e.get("raw_summary") or ""), 900) + "\n")
        lines.append("```\n")

    path.write_text("".join(lines), encoding="utf-8")


def _export_rule_audit_md(path: Path, *, events: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# Rule Audit\n")
    lines.append(f"- Exported at (UTC): {_utc_now_iso()}\n")
    lines.append(f"- Events: {len(events)}\n")

    for idx, e in enumerate(events, start=1):
        lines.append("\n---\n")
        lines.append(f"## Audit {idx}\n")
        lines.append(f"- event_cluster_id: {e.get('event_cluster_id')}\n")
        lines.append(f"- cluster_title: {e.get('cluster_title')}\n")
        lines.append(f"- final_queue: {e.get('cluster_queue')}\n")
        lines.append(f"- topic_priority: {e.get('topic_priority')}\n")
        lines.append(f"- audience_reach_score: {e.get('audience_reach_score')}\n")
        lines.append(f"- source_score: {e.get('source_score')}\n")
        lines.append(f"- fact_score: {e.get('fact_score')}\n")
        lines.append(f"- best_source: {e.get('best_source')}\n")
        sns = e.get("source_names")
        if isinstance(sns, list):
            lines.append(f"- source_names: {', '.join([str(x) for x in sns if str(x).strip()])}\n")
        ids = e.get("included_tweet_ids")
        if isinstance(ids, list):
            lines.append(f"- included_tweet_ids: {', '.join([str(x) for x in ids if str(x).strip()])}\n")
        lines.append(f"- rule_reason: {e.get('rule_reason')}\n")
        mf = e.get("missing_facts")
        if isinstance(mf, list) and mf:
            lines.append("- missing_facts:\n")
            for x in mf[:10]:
                lines.append(f"  - {_clip(str(x), 200)}\n")

    path.write_text("".join(lines), encoding="utf-8")


def _export_events_jsonl(path: Path, *, events: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _export_operator_summary_md(path: Path, *, source_label: str, buckets: dict[str, list[dict[str, Any]]]) -> None:
    lines: list[str] = []
    lines.append("# Operator Summary\n")
    lines.append(f"- Exported at (UTC): {_utc_now_iso()}\n")
    lines.append(f"- source: {source_label}\n")
    lines.append("- queues:\n")
    for k in ["queue_review", "source_research", "whale_digest", "monitor", "reject"]:
        lines.append(f"  - {k}: {len(buckets.get(k, []))}\n")
    lines.append("\n## queue_review Top 10\n")
    qr = buckets.get("queue_review", [])
    for i, e in enumerate(qr[:10], start=1):
        lines.append(f"\n### {i}. {str(e.get('cluster_title') or '').strip()}\n")
        lines.append(f"- rule_reason: {str(e.get('rule_reason') or '').strip()}\n")
        mf = e.get("missing_facts")
        if isinstance(mf, list) and mf:
            lines.append("- missing_facts:\n")
            for x in mf[:5]:
                lines.append(f"  - {_clip(str(x), 160)}\n")
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", default="data/sample_hot_inputs.json")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    root = _project_root()
    input_path = root / str(args.input_file)
    data = _read_json(input_path)
    if not isinstance(data, list):
        print("[run_hot_engine_offline_once] invalid_input expected_list=true")
        raise SystemExit(2)

    hot_inputs: list[dict[str, Any]] = []
    for idx, x in enumerate(data, start=1):
        if isinstance(x, dict):
            hot_inputs.append(_normalize_from_sample(x, idx))

    clusters = cluster_hot_inputs(hot_inputs)
    evaluated_events: list[dict[str, Any]] = []
    for c in clusters:
        e = evaluate_event(c.__dict__)
        best_id = str(e.get("best_source_item_id") or "")
        best_item = None
        for it in c.items:
            if str(it.get("input_id") or "") == best_id:
                best_item = it
                break
        if best_item is None and c.items:
            best_item = c.items[0]
        raw_summary = ""
        if best_item is not None:
            raw_summary = str(best_item.get("raw_text") or "")
        e["raw_summary"] = raw_summary
        e["source_urls"] = [
            str(it.get("source_url") or "").strip()
            for it in c.items
            if str(it.get("source_url") or "").strip()
        ]
        e["best_source_url"] = str(best_item.get("source_url") or "").strip() if best_item is not None else ""
        evaluated_events.append(e)

    buckets: dict[str, list[dict[str, Any]]] = {
        "queue_review": [],
        "monitor": [],
        "reject": [],
        "source_research": [],
        "whale_digest": [],
    }
    for e in evaluated_events:
        q = str(e.get("cluster_queue") or "monitor")
        if q not in buckets:
            q = "monitor"
        buckets[q].append(e)

    if args.out_dir.strip():
        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = root / out_dir
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = root / "out" / "hot_engine_queues_offline" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    _export_queue_md(out_dir / "queue_review.md", title="Queue Review", events=buckets["queue_review"])
    _export_queue_md(out_dir / "source_research.md", title="Source Research", events=buckets["source_research"])
    _export_queue_md(out_dir / "monitor.md", title="Monitor", events=buckets["monitor"])
    _export_queue_md(out_dir / "reject.md", title="Reject", events=buckets["reject"])
    _export_queue_md(out_dir / "whale_digest.md", title="Whale Digest", events=buckets["whale_digest"])
    _export_rule_audit_md(out_dir / "rule_audit.md", events=evaluated_events)
    _export_events_jsonl(out_dir / "events.jsonl", events=evaluated_events)
    _export_operator_summary_md(
        out_dir / "operator_summary.md",
        source_label=f"offline:{args.input_file}",
        buckets=buckets,
    )

    print(
        "[run_hot_engine_offline_once] ok"
        f" input_file={args.input_file}"
        f" inputs={len(hot_inputs)}"
        f" clusters={len(clusters)}"
        f" queue_review={len(buckets['queue_review'])}"
        f" source_research={len(buckets['source_research'])}"
        f" whale_digest={len(buckets['whale_digest'])}"
        f" monitor={len(buckets['monitor'])}"
        f" reject={len(buckets['reject'])}"
        f" out_dir={out_dir}"
    )


if __name__ == "__main__":
    main()

