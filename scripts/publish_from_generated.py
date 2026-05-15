from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from autopublish_guard import evaluate_autopublish
from x_publisher import publish


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _strip_links(text: str) -> str:
    t = text or ""
    t = re.sub(r"https?://\S+", "", t).strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def _load_generated_items(root: Path) -> list[dict[str, Any]]:
    raw_dir = root / "out" / "generated_posts" / "raw_json"
    if not raw_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for fp in sorted(raw_dir.glob("*.json")):
        try:
            j = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(j, dict):
            j["_file_path"] = str(fp)
            items.append(j)
    return items


def _load_event_map(root: Path) -> dict[str, dict[str, Any]]:
    p = root / "out" / "hot_engine_queues" / "events.jsonl"
    if not p.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            j = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(j, dict):
            eid = str(j.get("event_cluster_id") or "").strip()
            if eid:
                out[eid] = j
    return out


def _parse_iso_utc(s: str) -> datetime | None:
    ss = (s or "").strip()
    if not ss:
        return None
    try:
        return datetime.fromisoformat(ss.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _latest_run_id(root: Path) -> str:
    p = root / "out" / "generated_posts" / "latest_run_id.txt"
    if not p.exists():
        return ""
    return (p.read_text(encoding="utf-8") or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--real-publish", action="store_true", default=False)
    ap.add_argument("--include-dry-run-history", action="store_true", default=False)
    ap.add_argument("--queue", choices=["queue_review", "enriched_queue_review", "source_research", "whale_digest"], default="")
    ap.add_argument("--run-id", type=str, default="")
    ap.add_argument("--latest-run", action="store_true", default=False)
    args = ap.parse_args()

    root = _project_root()
    if args.queue == "source_research":
        if args.real_publish:
            raise SystemExit("[publish_from_generated] source_research is preview-only; real publish is not allowed")
        print("[publish_from_generated] source_research is preview-only; skipping publish step")
        print("- suggestion: open out/generated_posts/source_research_drafts.md")
        print("- items=0 published=0 would_publish=0 blocked=0")
        return
    out_dir = root / "out" / "publish_logs"
    _ensure_dir(out_dir)

    published_jsonl = out_dir / "published_posts.jsonl"
    dryrun_jsonl = out_dir / "dryrun_posts.jsonl"
    blocked_md = out_dir / "blocked_posts.md"

    items = _load_generated_items(root)
    run_id = (args.run_id or "").strip()
    if args.latest_run and not run_id:
        run_id = _latest_run_id(root)

    if args.queue:
        items = [x for x in items if str(x.get("queue") or "") == args.queue]

    if run_id:
        items = [x for x in items if str(x.get("run_id") or "").strip() == run_id]
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        filtered: list[dict[str, Any]] = []
        for x in items:
            dt = _parse_iso_utc(str(x.get("generated_at") or ""))
            if dt is not None and dt >= cutoff:
                filtered.append(x)
        items = filtered
        print("[publish_from_generated] warning: no --run-id/--latest-run provided; only processing items generated in last 10 minutes")
        print("[publish_from_generated] warning: recommended: use --latest-run")

    events = _load_event_map(root)

    blocked_lines: list[str] = ["# Blocked Posts\n", f"- Exported at (UTC): {_utc_now_iso()}\n"]

    would_publish_count = 0
    blocked_count = 0
    published_count = 0

    dry_run_mode = not bool(args.real_publish)

    for it in items:
        eid = str(it.get("event_cluster_id") or "").strip()
        event = events.get(eid, {})
        gen = it.get("generated_json") if isinstance(it.get("generated_json"), dict) else {}
        it_run_id = str(it.get("run_id") or "").strip()
        it_queue = str(it.get("queue") or "").strip()
        guard_queue = "queue_review" if it_queue == "enriched_queue_review" else it_queue

        main_post = _strip_links(str(gen.get("main_post") or ""))
        first_comment = _strip_links(str(gen.get("first_comment") or ""))
        main_post_length = len(main_post)
        first_comment_length = len(first_comment)

        guard = evaluate_autopublish(
            generated_post=gen,
            event_cluster=event | {"cluster_queue": guard_queue},
            include_dry_run_history=bool(args.include_dry_run_history),
        )
        allowed = bool(guard.get("allowed_to_autopublish"))
        reply_allowed = bool(guard.get("reply_allowed", True))
        reply_skip_reason = str(guard.get("reply_skip_reason") or "")
        adjustment_actions = guard.get("adjustment_actions") if isinstance(guard.get("adjustment_actions"), list) else []
        reply_skipped = False

        if not allowed:
            blocked_count += 1
            blocked_lines.append("\n---\n")
            blocked_lines.append(f"## {eid}\n")
            blocked_lines.append(f"- queue: {it.get('queue')}\n")
            blocked_lines.append(f"- block_reasons: {guard.get('block_reasons')}\n")
            blocked_lines.append(f"- risk_level: {guard.get('risk_level')}\n")
            blocked_lines.append(f"- autopublish_score: {guard.get('autopublish_score')}\n")
            gd = guard.get("guard_debug") if isinstance(guard.get("guard_debug"), dict) else {}
            blocked_lines.append(f"- public_text_keyword_hits: {gd.get('public_text_keyword_hits')}\n")
            blocked_lines.append(f"- internal_warning_hits: {gd.get('internal_warning_hits')}\n")
            blocked_lines.append(f"- negated_keyword_hits: {gd.get('negated_keyword_hits')}\n")
            blocked_lines.append("\n```text\n")
            blocked_lines.append(str(gd.get("scanned_public_text_preview") or "")[:600])
            blocked_lines.append("\n```\n")
            blocked_lines.append("\n```text\n")
            blocked_lines.append(str(gd.get("scanned_internal_text_preview") or "")[:600])
            blocked_lines.append("\n```\n")
            blocked_lines.append("\n```text\n")
            blocked_lines.append((main_post[:500] + "…") if len(main_post) > 500 else main_post)
            blocked_lines.append("\n```\n")
            rec = {
                "created_at": _utc_now_iso(),
                "status": "blocked",
                "queue": it.get("queue"),
                "event_cluster_id": eid,
                "run_id": it_run_id,
                "reply_allowed": reply_allowed,
                "reply_skipped": False,
                "reply_skip_reason": "",
                "adjustment_actions": adjustment_actions,
                "main_post_length": int(main_post_length),
                "first_comment_length": int(first_comment_length),
                "block_reasons": guard.get("block_reasons"),
                "risk_level": guard.get("risk_level"),
                "autopublish_score": guard.get("autopublish_score"),
                "guard_debug": gd,
            }
            if dry_run_mode:
                with dryrun_jsonl.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({**rec, "dry_run": True}, ensure_ascii=False) + "\n")
            continue

        publish_first_comment = first_comment
        if not reply_allowed:
            publish_first_comment = ""
            reply_skipped = True

        if args.real_publish:
            print("[publish_from_generated] FINAL PREVIEW (real publish requested)")
        else:
            print("[publish_from_generated] FINAL PREVIEW (dry-run)")
        print(
            f"- run_id={it_run_id} queue={it.get('queue')} event_cluster_id={eid} reply_allowed={reply_allowed} reply_skipped={reply_skipped}"
        )
        print(f"- main_post_length={main_post_length} first_comment_length={first_comment_length}")
        print("---- main_post_preview ----")
        print(main_post[:320])
        print("---- first_comment_preview ----")
        print(publish_first_comment[:320])

        resp = publish(main_post=main_post, first_comment=publish_first_comment, dry_run=dry_run_mode)
        status = "would_publish" if resp.get("dry_run") else "published"
        if status == "published":
            published_count += 1
        else:
            would_publish_count += 1
        rec = {
            "created_at": _utc_now_iso(),
            "status": status,
            "queue": it.get("queue"),
            "event_cluster_id": eid,
            "run_id": it_run_id,
            "reply_allowed": reply_allowed,
            "reply_skipped": bool(reply_skipped),
            "reply_skip_reason": reply_skip_reason if reply_skipped else "",
            "adjustment_actions": adjustment_actions,
            "main_post_length": int(main_post_length),
            "first_comment_length": int(first_comment_length),
            "x_post_id": resp.get("x_post_id") or "",
            "x_post_url": resp.get("x_post_url") or "",
            "dry_run": bool(resp.get("dry_run")),
        }
        gd = guard.get("guard_debug") if isinstance(guard.get("guard_debug"), dict) else {}
        rec["guard_debug"] = gd
        if status == "published":
            with published_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        else:
            with dryrun_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    blocked_md.write_text("".join(blocked_lines), encoding="utf-8")
    print(
        f"[publish_from_generated] ok run_id={run_id or '(recent_10m)'} queue={args.queue or '(all)'} items={len(items)} published={published_count} would_publish={would_publish_count} blocked={blocked_count} out_dir={out_dir}"
    )
    print("[publish_from_generated] open: out/publish_logs/published_posts.jsonl")
    print("[publish_from_generated] open: out/publish_logs/dryrun_posts.jsonl")
    print("[publish_from_generated] open: out/publish_logs/blocked_posts.md")


if __name__ == "__main__":
    main()

