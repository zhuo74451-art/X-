from __future__ import annotations

import argparse
import json
import secrets
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


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(3)
    return f"{stamp}_{suffix}"


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


def _export_operator_summary_md(
    path: Path,
    *,
    run_id: str,
    source: str,
    fetched: int,
    clusters: int,
    buckets: dict[str, list[dict[str, Any]]],
    events: list[dict[str, Any]],
    mode: str,
    purpose: str,
    publish_enabled: bool,
    external_signal_enabled: bool,
    auto_publish_enabled: bool,
) -> None:
    qn = len(buckets.get("queue_review") or [])
    mn = len(buckets.get("monitor") or [])
    rn = len(buckets.get("reject") or [])
    sn = len(buckets.get("source_research") or [])
    wn = len(buckets.get("whale_digest") or [])

    def _fmt_sources(e: dict[str, Any]) -> str:
        sns = e.get("source_names")
        if isinstance(sns, list):
            s = ", ".join([str(x) for x in sns if str(x).strip()])
            return _clip(s, 120)
        return ""

    top_all = sorted(events, key=lambda x: int(x.get("total_score") or 0), reverse=True)[:10]
    top_qr = sorted(buckets.get("queue_review") or [], key=lambda x: int(x.get("total_score") or 0), reverse=True)[:10]

    lines: list[str] = []
    lines.append("# Hot Engine Operator Summary\n")
    lines.append(f"- run_id: {run_id}\n")
    lines.append(f"- mode: {mode}\n")
    lines.append(f"- purpose: {purpose}\n")
    lines.append(f"- publish_enabled: {str(bool(publish_enabled)).lower()}\n")
    lines.append(f"- external_signal_enabled: {str(bool(external_signal_enabled)).lower()}\n")
    lines.append(f"- auto_publish_enabled: {str(bool(auto_publish_enabled)).lower()}\n")
    lines.append(f"- generated_at_utc: {_utc_now_iso()}\n")
    lines.append(f"- source: {source}\n")
    lines.append(f"- fetched_inputs: {fetched}\n")
    lines.append(f"- clusters: {clusters}\n")
    lines.append(f"- queue_review: {qn}\n")
    lines.append(f"- source_research: {sn}\n")
    lines.append(f"- whale_digest: {wn}\n")
    lines.append(f"- monitor: {mn}\n")
    lines.append(f"- reject: {rn}\n")
    lines.append("\n## Top 10 Candidates (All)\n")
    if not top_all:
        lines.append("- (empty)\n")
    else:
        for i, e in enumerate(top_all, start=1):
            lines.append(f"\n### Candidate {i}\n")
            lines.append(f"- event_cluster_id: {e.get('event_cluster_id')}\n")
            lines.append(f"- title: {e.get('cluster_title')}\n")
            lines.append(f"- queue: {e.get('cluster_queue')}\n")
            lines.append(f"- total_score: {e.get('total_score')}\n")
            lines.append(f"- risk_level: {e.get('risk_level')}\n")
            lines.append(f"- sources: {_fmt_sources(e)}\n")
            lines.append(f"- rule_reason: {_clip(str(e.get('rule_reason') or ''), 240)}\n")

    lines.append("\n## Queue Review Top 10\n")
    if not top_qr:
        lines.append("- (empty)\n")
    else:
        for i, e in enumerate(top_qr, start=1):
            lines.append(f"\n### Queue Review {i}\n")
            lines.append(f"- event_cluster_id: {e.get('event_cluster_id')}\n")
            lines.append(f"- title: {e.get('cluster_title')}\n")
            lines.append(f"- total_score: {e.get('total_score')}\n")
            lines.append(f"- sources: {_fmt_sources(e)}\n")
            lines.append(f"- rule_reason: {_clip(str(e.get('rule_reason') or ''), 240)}\n")

    lines.append("\n## Near Miss Candidates (Almost Review)\n")
    near_pool = list(buckets.get("monitor") or []) + list(buckets.get("source_research") or [])
    near_top = sorted(near_pool, key=lambda x: int(x.get("total_score") or 0), reverse=True)[:10]
    if not near_top:
        lines.append("- (empty)\n")
    else:
        for i, e in enumerate(near_top, start=1):
            ar = int(e.get("audience_reach_score") or 0)
            pr = str(e.get("topic_priority") or "")
            total = int(e.get("total_score") or 0)
            src = int(e.get("source_score") or 0)
            fact = int(e.get("fact_score") or 0)
            best_rank = int(e.get("best_source_rank") or 9)
            decision = str(e.get("rule_reason") or "")
            selected_queue = str(e.get("cluster_queue") or "")

            missing: list[str] = []
            if ar < 70:
                missing.append("audience_reach_score>=70")
            if pr not in {"P0", "P1"}:
                missing.append("topic_priority=P0/P1")
            if fact < 70:
                missing.append("fact_score>=70")
            if best_rank >= 4:
                missing.append("best_source_rank<=3")

            mf = e.get("missing_facts")
            if isinstance(mf, list) and mf:
                missing.extend([str(x) for x in mf[:6] if str(x).strip()])

            blocked_or_demoted_by = ""
            if "：" in decision:
                blocked_or_demoted_by = decision.split("：", 1)[1].strip()
            elif decision:
                blocked_or_demoted_by = decision.strip()

            suggested = "补充一手来源与事实锚点，重跑评估"
            if selected_queue == "monitor":
                suggested = "补充用户连接点/事实锚点，确认是否值得进入 review"
            if selected_queue == "source_research":
                suggested = "优先补 missing_facts 中的一手来源/原文链接，再重跑"

            lines.append(f"\n### Near Miss {i}\n")
            lines.append(f"- event_cluster_id: {e.get('event_cluster_id')}\n")
            lines.append(f"- title: {e.get('cluster_title')}\n")
            lines.append(f"- selected_queue: {selected_queue}\n")
            lines.append(f"- total_score: {total}\n")
            lines.append(f"- hot_score(audience_reach_score): {ar}\n")
            lines.append(f"- source_score: {src}\n")
            lines.append(f"- fact_score: {fact}\n")
            lines.append(f"- sources: {_fmt_sources(e)}\n")
            lines.append(f"- decision_reason: {_clip(decision, 240)}\n")
            lines.append(f"- blocked_or_demoted_by: {_clip(blocked_or_demoted_by, 160)}\n")
            if missing:
                lines.append("- missing_requirements:\n")
                for x in missing[:10]:
                    lines.append(f"  - {_clip(str(x), 220)}\n")
            lines.append(f"- suggested_human_action: {_clip(suggested, 220)}\n")

    lines.append("\n## Notes\n")
    lines.append("- 本次为内部数据驱动 dry-run：只输出本地队列与审核摘要，不进入发布链路。\n")
    lines.append("- 未接入外部信号源（external_signal_source）到主输入。\n")
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["integration_ready", "integration_published"], default="integration_ready")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--since", type=str, default="")
    ap.add_argument("--q", type=str, default="")
    ap.add_argument("--content_type", type=str, default="")
    ap.add_argument("--api_source", type=str, default="")
    ap.add_argument("--dry-run", action="store_true", default=False)
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

    run_id = _new_run_id()
    run_root = root / "out" / "hot_engine" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    mode = "calibration"
    purpose = "internal_db_hot_engine_real_day_test"
    publish_enabled = False
    external_signal_enabled = False
    auto_publish_enabled = False
    (run_root / "run_meta.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "mode": mode,
                "purpose": purpose,
                "publish_enabled": publish_enabled,
                "external_signal_enabled": external_signal_enabled,
                "auto_publish_enabled": auto_publish_enabled,
                "generated_at_utc": _utc_now_iso(),
                "source": args.source,
                "dry_run": bool(args.dry_run),
                "fetched_inputs": len(raw_items),
                "clusters": len(clusters),
                "queue_counts": {
                    "queue_review": len(buckets["queue_review"]),
                    "source_research": len(buckets["source_research"]),
                    "whale_digest": len(buckets["whale_digest"]),
                    "monitor": len(buckets["monitor"]),
                    "reject": len(buckets["reject"]),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _export_operator_summary_md(
        run_root / "operator_summary.md",
        run_id=run_id,
        source=args.source,
        fetched=len(raw_items),
        clusters=len(clusters),
        buckets=buckets,
        events=evaluated_events,
        mode=mode,
        purpose=purpose,
        publish_enabled=publish_enabled,
        external_signal_enabled=external_signal_enabled,
        auto_publish_enabled=auto_publish_enabled,
    )
    _export_queue_md(run_root / "queue_review.md", title="Queue Review", events=buckets["queue_review"])
    _export_queue_md(run_root / "source_research.md", title="Source Research", events=buckets["source_research"])
    _export_queue_md(run_root / "monitor.md", title="Monitor", events=buckets["monitor"])
    _export_queue_md(run_root / "reject.md", title="Reject", events=buckets["reject"])
    _export_whale_digest_md(run_root / "whale_digest.md", events=buckets["whale_digest"])
    _export_rule_audit_md(run_root / "rule_audit.md", events=evaluated_events)
    _export_events_jsonl(run_root / "events.jsonl", events=evaluated_events)
    (root / "out" / "hot_engine" / "latest_run_id.txt").write_text(run_id, encoding="utf-8")

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
        f" run_dir={run_root}"
    )


if __name__ == "__main__":
    main()

