from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read_events_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _count_queues(events: list[dict[str, Any]]) -> dict[str, int]:
    qs = ["queue_review", "source_research", "monitor", "reject", "whale_digest"]
    out = {q: 0 for q in qs}
    for e in events:
        q = str(e.get("cluster_queue") or "").strip()
        if q in out:
            out[q] += 1
    out["total"] = len(events)
    return out


def _count_drafts(md_path: Path) -> int:
    if not md_path.exists():
        return 0
    return md_path.read_text(encoding="utf-8").count("\n## Draft ")


def _read_publish_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            j = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(j, dict):
            out.append(j)
    return out


def _parse_iso_utc(s: str) -> datetime | None:
    ss = (s or "").strip()
    if not ss:
        return None
    try:
        return datetime.fromisoformat(ss.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _count_log_since(items: list[dict[str, Any]], since: datetime) -> dict[str, int]:
    out = {"would_publish": 0, "published": 0, "blocked": 0, "total": 0}
    for it in items:
        dt = _parse_iso_utc(str(it.get("created_at") or ""))
        if dt is None or dt < since:
            continue
        st = str(it.get("status") or "")
        out["total"] += 1
        if st in out:
            out[st] += 1
    return out


def _run_step(args: list[str], *, cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), check=True)


def _sum_item_count(events: list[dict[str, Any]]) -> int:
    total = 0
    for e in events:
        try:
            total += int(e.get("item_count") or 0)
        except Exception:
            continue
    return total


def _write_no_candidate_summary(
    *,
    root: Path,
    input_limit: int,
    events: list[dict[str, Any]],
    qdist: dict[str, int],
) -> Path:
    out_dir = root / "out" / "review_queue"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "no_autopublish_candidates.md"

    item_total = _sum_item_count(events)
    lines: list[str] = []
    lines.append("# No Auto-publish Candidates\n")
    lines.append(f"- input_limit: {int(input_limit)}\n")
    lines.append(f"- scanned_items_total: {item_total}\n")
    lines.append(f"- events_total: {qdist.get('total')}\n")
    lines.append("\n## Queue Distribution\n")
    for k in ["queue_review", "source_research", "monitor", "reject", "whale_digest"]:
        lines.append(f"- {k}: {qdist.get(k, 0)}\n")

    lines.append("\n## Why No Candidates\n")
    lines.append("- queue_review=0 且 whale_digest=0：本轮没有适合自动发布的候选。\n")
    lines.append("- 常规 BTC/ETH 现货 ETF 资金流已默认降级到 monitor/reject（除非出现强钩子）。\n")
    lines.append("- auto-publish 仍要求：低风险、来源锚点、非二手来源、长度合规、无敏感主题/投顾暗示等。\n")

    def _top5(queue: str) -> list[dict[str, Any]]:
        xs = [e for e in events if str(e.get("cluster_queue") or "") == queue]
        return xs[:5]

    def _fmt_event(e: dict[str, Any]) -> str:
        return (
            f"- {e.get('event_cluster_id')} | "
            f"{str(e.get('cluster_title') or '').strip()[:80]} | "
            f"score={e.get('total_score')} | "
            f"risk={e.get('risk_level')} | "
            f"best_source={str(e.get('best_source_url') or '').strip()}\n"
            f"  - rule_reason: {str(e.get('rule_reason') or '').strip()}\n"
        )

    lines.append("\n## monitor Top 5\n")
    ms = _top5("monitor")
    if not ms:
        lines.append("- (empty)\n")
    else:
        for e in ms:
            lines.append(_fmt_event(e))

    lines.append("\n## source_research Top 5\n")
    ss = _top5("source_research")
    if not ss:
        lines.append("- (empty)\n")
    else:
        for e in ss:
            lines.append(_fmt_event(e))

    lines.append("\n## Suggestions\n")
    lines.append("- 扩大输入范围：提高 --limit（例如 200）或改用更丰富的输入源。\n")
    lines.append("- 等待新素材：当前素材偏常规，缺少可传播钩子。\n")
    lines.append("- 人工挑选 source_research：补一手来源/数据对比/价格背离证据后再评估。\n")

    p.write_text("".join(lines), encoding="utf-8")
    return p


def _latest_run_id(root: Path) -> str:
    p = root / "out" / "generated_posts" / "latest_run_id.txt"
    if not p.exists():
        return ""
    return (p.read_text(encoding="utf-8") or "").strip()


def _count_raw_json_for_run(root: Path, *, run_id: str, queue: str) -> int:
    raw_dir = root / "out" / "generated_posts" / "raw_json"
    if not raw_dir.exists():
        return 0
    c = 0
    for fp in raw_dir.glob("*.json"):
        try:
            j = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(j, dict):
            continue
        if str(j.get("run_id") or "").strip() != run_id:
            continue
        if str(j.get("queue") or "").strip() != queue:
            continue
        c += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    root = _project_root()
    run_started_at = _utcnow()

    limit = max(0, int(args.limit))
    print(f"[dryrun_once] step1: run_hot_engine_once.py --source integration_published --limit {limit}")
    _run_step(
        [
            sys.executable,
            str(root / "scripts" / "run_hot_engine_once.py"),
            "--source",
            "integration_published",
            "--limit",
            str(limit),
        ],
        cwd=root,
    )

    events_path = root / "out" / "hot_engine_queues" / "events.jsonl"
    events = _read_events_jsonl(events_path)
    qdist = _count_queues(events)
    print("[dryrun_once] queue_distribution:", qdist)

    def _generate(queue: str) -> tuple[str, int]:
        print(f"[dryrun_once] generate: queue={queue} limit=1 runtime=mock clean_before_generate=true")
        _run_step(
            [
                sys.executable,
                str(root / "scripts" / "generate_from_queue.py"),
                "--queue",
                queue,
                "--limit",
                "1",
                "--runtime",
                "mock",
                "--clean-before-generate",
            ],
            cwd=root,
        )
        rid = _latest_run_id(root)
        return rid, _count_raw_json_for_run(root, run_id=rid, queue=queue) if rid else 0

    run_id, generated_n = _generate("queue_review")
    chosen_queue = "queue_review"
    if generated_n == 0:
        run_id, generated_n = _generate("whale_digest")
        chosen_queue = "whale_digest"

    if generated_n == 0:
        p = _write_no_candidate_summary(root=root, input_limit=limit, events=events, qdist=qdist)
        print(f"[dryrun_once] no candidates: {p}")
        print("[dryrun_once] skip publish_from_generated (no candidates)")
        return

    out_gen = root / "out" / "generated_posts"
    qrev_md = out_gen / "queue_review_drafts.md"
    whale_md = out_gen / "whale_digest_drafts.md"
    gen_counts = {"queue_review": _count_drafts(qrev_md), "whale_digest": _count_drafts(whale_md)}
    print("[dryrun_once] generated_drafts:", gen_counts)

    print(f"[dryrun_once] publish: queue={chosen_queue} latest_run=true dry_run=true")
    _run_step(
        [
            sys.executable,
            str(root / "scripts" / "publish_from_generated.py"),
            "--dry-run",
            "--queue",
            chosen_queue,
            "--latest-run",
        ],
        cwd=root,
    )

    dry_log = root / "out" / "publish_logs" / "dryrun_posts.jsonl"
    dry_items = _read_publish_log(dry_log)
    dry_counts = _count_log_since(dry_items, run_started_at)
    print("[dryrun_once] dryrun_log_since_start:", dry_counts)

    print("[dryrun_once] outputs:")
    print("- out/hot_engine_queues/events.jsonl")
    print("- out/generated_posts/queue_review_drafts.md")
    print("- out/generated_posts/whale_digest_drafts.md")
    print("- out/publish_logs/published_posts.jsonl")
    print("- out/publish_logs/dryrun_posts.jsonl")
    print("- out/publish_logs/blocked_posts.md")


if __name__ == "__main__":
    main()

