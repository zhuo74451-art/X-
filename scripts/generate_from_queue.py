from __future__ import annotations

import argparse
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_client import call_llm


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


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


def _read_event_map(path: Path) -> dict[str, dict[str, Any]]:
    mp: dict[str, dict[str, Any]] = {}
    for e in _read_events_jsonl(path):
        eid = str(e.get("event_cluster_id") or "").strip()
        if eid:
            mp[eid] = e
    return mp


def _safe_filename(s: str) -> str:
    t = (s or "").strip()
    t = re.sub(r"[^a-zA-Z0-9_\-]+", "_", t)
    return t.strip("_") or "item"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(3)
    return f"{stamp}_{suffix}"


def _clean_old_raw_json_for_queue(raw_dir: Path, queue: str) -> int:
    removed = 0
    for fp in sorted(raw_dir.glob("*.json")):
        try:
            j = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            j = None
        if isinstance(j, dict):
            if str(j.get("queue") or "") == queue:
                try:
                    fp.unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
            continue
        name = fp.name
        if f"_{queue}_" in name:
            try:
                fp.unlink()
                removed += 1
            except FileNotFoundError:
                pass
    return removed


def _build_event_pack(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_cluster_id": e.get("event_cluster_id") or "",
        "cluster_title": e.get("cluster_title") or "",
        "cluster_queue": e.get("cluster_queue") or "",
        "topic_priority": e.get("topic_priority") or "",
        "audience_reach_score": e.get("audience_reach_score") or 0,
        "risk_level": e.get("risk_level") or "",
        "best_source_url": e.get("best_source_url") or "",
        "source_urls": e.get("source_urls") or [],
        "source_names": e.get("source_names") or [],
        "included_tweet_ids": e.get("included_tweet_ids") or [],
        "rule_reason": e.get("rule_reason") or "",
        "missing_facts": e.get("missing_facts") or [],
        "raw_summary": e.get("raw_summary") or "",
    }


def _write_md(path: Path, title: str, rows: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append(f"# {title}\n")
    lines.append(f"- Items: {len(rows)}\n")
    for i, r in enumerate(rows, start=1):
        lines.append("\n---\n")
        lines.append(f"## Draft {i}\n")
        lines.append(f"- event_cluster_id: {r.get('event_cluster_id')}\n")
        lines.append(f"- queue: {r.get('queue')}\n")
        lines.append(f"- skill_name: {r.get('skill_name')}\n")
        lines.append(f"- prompt_version: {r.get('prompt_version')}\n")
        su = r.get("source_urls")
        if isinstance(su, list):
            lines.append(f"- source_urls: {', '.join([str(x) for x in su if str(x).strip()])}\n")
        lines.append(f"- risk_level: {r.get('risk_level')}\n")
        lines.append(f"- raw_output_path: {r.get('raw_output_path')}\n")
        lines.append("\n```json\n")
        lines.append(json.dumps(r.get("generated_json") or {}, ensure_ascii=False, indent=2) + "\n")
        lines.append("```\n")
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", choices=["queue_review", "source_research", "enriched_queue_review", "whale_digest"], required=True)
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--runtime", choices=["mock", "openrouter"], default="mock")
    ap.add_argument("--prompt-version", type=str, default="v0.1")
    ap.add_argument("--clean-before-generate", action="store_true", default=False)
    ap.add_argument("--require-fact-pack", action="store_true", default=False)
    args = ap.parse_args()

    if args.runtime == "openrouter" and not (os.getenv("OPENROUTER_API_KEY") or "").strip():
        print("[generate_from_queue] missing OPENROUTER_API_KEY (need manual PowerShell env)")
        raise SystemExit(2)

    prev_runtime = os.environ.get("MODEL_RUNTIME")
    os.environ["MODEL_RUNTIME"] = args.runtime
    try:
        root = _project_root()
        events_path = root / "out" / "hot_engine_queues" / "events.jsonl"
        event_map = _read_event_map(events_path)
        if args.queue == "enriched_queue_review":
            events = _read_events_jsonl(root / "out" / "hot_engine_queues" / "enriched_queue_review.jsonl")
        else:
            events = _read_events_jsonl(events_path)
            events = [e for e in events if str(e.get("cluster_queue") or "") == args.queue]

        out_dir = root / "out" / "generated_posts"
        raw_dir = out_dir / "raw_json"
        enriched_dir = root / "out" / "enriched_events"
        _ensure_dir(out_dir)
        _ensure_dir(raw_dir)

        run_id = _new_run_id()
        generated_at = _utc_now_iso()
        (out_dir / "latest_run_id.txt").write_text(run_id, encoding="utf-8")

        if args.clean_before_generate:
            removed = _clean_old_raw_json_for_queue(raw_dir, args.queue)
            print(f"[generate_from_queue] cleaned old raw_json queue={args.queue} removed={removed}")

        if args.queue in ("queue_review", "source_research", "enriched_queue_review"):
            skill_name = "coinmeta_hot_post"
            md_path = out_dir / (f"{args.queue}_drafts.md")
        else:
            skill_name = "coinmeta_whale_digest"
            md_path = out_dir / "whale_digest_drafts.md"

        rows: list[dict[str, Any]] = []
        for e in events:
            if len(rows) >= max(0, int(args.limit)):
                break
            if args.queue == "enriched_queue_review":
                eid = str(e.get("event_cluster_id") or "").strip()
                base = event_map.get(eid) or {}
                if not base:
                    continue
                event_pack = _build_event_pack(base)
                event_pack["cluster_queue"] = "queue_review"
                event_pack["enriched_queue"] = "enriched_queue_review"
                event_pack["original_queue"] = str(base.get("cluster_queue") or "")
            else:
                event_pack = _build_event_pack(e)
            event_id = str(event_pack.get("event_cluster_id") or "")

            fact_pack_path = enriched_dir / f"{event_id}_fact_pack.json"
            fact_pack_used = False
            fact_pack_obj: dict[str, Any] | None = None
            if fact_pack_path.exists():
                try:
                    fact_pack_obj = json.loads(fact_pack_path.read_text(encoding="utf-8"))
                    if isinstance(fact_pack_obj, dict):
                        fact_pack_used = True
                    else:
                        fact_pack_obj = None
                except json.JSONDecodeError:
                    fact_pack_obj = None

            require_fact = bool(args.require_fact_pack) or (args.queue == "enriched_queue_review")
            if require_fact and not fact_pack_used:
                continue

            input_pack: dict[str, Any] = dict(event_pack)
            if fact_pack_used and fact_pack_obj is not None:
                input_pack["event_cluster"] = dict(event_pack)
                input_pack["fact_pack"] = fact_pack_obj

            r = call_llm(skill_name=skill_name, input_pack=input_pack, prompt_version=args.prompt_version)
            ok = bool(r.get("ok"))
            generated = r.get("output") if isinstance(r.get("output"), dict) else {}
            raw_output_path = str(r.get("raw_output_path") or "")

            fp_upgrade = ""
            fp_source_risk = ""
            fp_event_type = ""
            if fact_pack_used and isinstance(fact_pack_obj, dict):
                fp_upgrade = str(fact_pack_obj.get("upgrade_recommendation") or "")
                fp_source_risk = str(fact_pack_obj.get("source_risk") or "")
                fp_event_type = str(fact_pack_obj.get("event_type") or "")

            meta = {
                "run_id": run_id,
                "generated_at": generated_at,
                "event_cluster_id": event_pack.get("event_cluster_id"),
                "queue": args.queue,
                "skill_name": skill_name,
                "prompt_version": args.prompt_version,
                "source_urls": event_pack.get("source_urls") or [],
                "risk_level": event_pack.get("risk_level") or "",
                "fact_pack_used": bool(fact_pack_used),
                "fact_pack_path": str(fact_pack_path) if fact_pack_used else "",
                "fact_pack_upgrade_recommendation": fp_upgrade,
                "fact_pack_source_risk": fp_source_risk,
                "event_type": fp_event_type,
                "generated_json": generated,
                "raw_output_path": raw_output_path,
                "ok": ok,
                "error": str(r.get("error") or ""),
            }

            fp = raw_dir / f"{_safe_filename(str(event_pack.get('event_cluster_id') or 'event'))}_{args.queue}_{skill_name}.json"
            fp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.append(meta)

        _write_md(md_path, f"{args.queue} drafts", rows)
        if not rows:
            print(f"[generate_from_queue] {args.queue} is empty, no drafts generated")
        print(
            f"[generate_from_queue] ok run_id={run_id} queue={args.queue} runtime={args.runtime} generated={len(rows)} out_dir={out_dir}"
        )
        print("[generate_from_queue] preview: out/generated_posts/queue_review_drafts.md")
        print("[generate_from_queue] preview: out/generated_posts/source_research_drafts.md")
        print("[generate_from_queue] preview: out/generated_posts/whale_digest_drafts.md")
    finally:
        if prev_runtime is None:
            os.environ.pop("MODEL_RUNTIME", None)
        else:
            os.environ["MODEL_RUNTIME"] = prev_runtime


if __name__ == "__main__":
    main()

