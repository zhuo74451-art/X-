from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.import_integration_api import fetch_pool, normalize_to_hot_input
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
        lines.append(f"- publish_mode: {e.get('cluster_queue')}\n")
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


def _export_whale_digest_md(path: Path, *, events: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# Whale Digest\n")
    lines.append(f"- Exported at (UTC): {_utc_now_iso()}\n")
    lines.append(f"- Events: {len(events)}\n")

    for idx, e in enumerate(events, start=1):
        lines.append("\n---\n")
        lines.append(f"## Whale {idx}\n")
        lines.append(f"- event_cluster_id: {e.get('event_cluster_id')}\n")
        lines.append(f"- cluster_title: {e.get('cluster_title')}\n")
        lines.append(f"- actor_label: {e.get('actor_label')}\n")
        lines.append(f"- asset: {e.get('asset')}\n")
        lines.append(f"- action: {e.get('action')}\n")
        lines.append(f"- amount_usd: {e.get('amount_usd')}\n")
        lines.append(f"- pnl_usd: {e.get('pnl_usd')}\n")
        lines.append(f"- liquidation_price: {e.get('liquidation_price')}\n")
        lines.append(f"- source_url: {e.get('source_url')}\n")
        lines.append(f"- dashboard_url: {e.get('dashboard_url')}\n")
        lines.append(f"- rule_reason: {e.get('rule_reason')}\n")
        lines.append(f"- comment_angle: {e.get('comment_angle')}\n")
        lines.append(f"- item_count: {e.get('item_count')}\n")
        ids = e.get("included_tweet_ids")
        if isinstance(ids, list):
            lines.append(f"- included_tweet_ids: {', '.join([str(x) for x in ids if str(x).strip()])}\n")
        lines.append("\n```text\n")
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["integration_ready", "integration_published"], required=True)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--since", type=str, default="")
    ap.add_argument("--q", type=str, default="")
    ap.add_argument("--content_type", type=str, default="")
    ap.add_argument("--api_source", type=str, default="")
    args = ap.parse_args()

    pool = "ready" if args.source == "integration_ready" else "published"
    try:
        raw_items = fetch_pool(
            pool=pool,
            limit=args.limit,
            offset=args.offset,
            since=args.since or None,
            source=args.api_source or None,
            content_type=args.content_type or None,
            q=args.q or None,
        )
    except RuntimeError as e:
        print(f"[run_hot_engine_once] fetch_failed source={args.source} error={e}")
        print("[run_hot_engine_once] 请确认 configs/integration_sources.json 中 base_url 可访问")
        raise SystemExit(2)
    hot_inputs = [normalize_to_hot_input(x) for x in raw_items]

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
        e["source_urls"] = [str(it.get("source_url") or "").strip() for it in c.items if str(it.get("source_url") or "").strip()]
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

    root = _project_root()
    out_dir = root / "out" / "hot_engine_queues"
    out_dir.mkdir(parents=True, exist_ok=True)

    _export_queue_md(out_dir / "queue_review.md", title="Queue Review", events=buckets["queue_review"])
    _export_queue_md(out_dir / "source_research.md", title="Source Research", events=buckets["source_research"])
    _export_queue_md(out_dir / "monitor.md", title="Monitor", events=buckets["monitor"])
    _export_queue_md(out_dir / "reject.md", title="Reject", events=buckets["reject"])
    _export_whale_digest_md(out_dir / "whale_digest.md", events=buckets["whale_digest"])
    _export_rule_audit_md(out_dir / "rule_audit.md", events=evaluated_events)
    _export_events_jsonl(out_dir / "events.jsonl", events=evaluated_events)

    print(
        "[run_hot_engine_once] ok"
        f" source={args.source}"
        f" fetched={len(raw_items)}"
        f" queue_review={len(buckets['queue_review'])}"
        f" source_research={len(buckets['source_research'])}"
        f" whale_digest={len(buckets['whale_digest'])}"
        f" monitor={len(buckets['monitor'])}"
        f" reject={len(buckets['reject'])}"
        f" out_dir={out_dir}"
    )


if __name__ == "__main__":
    main()

