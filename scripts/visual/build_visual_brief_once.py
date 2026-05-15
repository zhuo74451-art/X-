from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "out" / "visual_briefs"

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
VISUAL_DIR = Path(__file__).resolve().parent
for p in [str(SCRIPTS_DIR), str(VISUAL_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from visual.image_brief_builder import build_visual_brief

from visual.template_card_renderer import render_template_card


EVENTS_JSONL = ROOT / "out" / "hot_engine_queues" / "events.jsonl"
ENRICHED_QUEUE_JSONL = ROOT / "out" / "hot_engine_queues" / "enriched_queue_review.jsonl"
ENRICHED_DIR = ROOT / "out" / "enriched_events"
OUT_CARDS_DIR = ROOT / "out" / "visual_cards"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
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


def _event_map() -> dict[str, dict[str, Any]]:
    mp: dict[str, dict[str, Any]] = {}
    for e in _read_jsonl(EVENTS_JSONL):
        eid = str(e.get("event_cluster_id") or "").strip()
        if eid:
            mp[eid] = e
    return mp


def _load_fact_pack(event_cluster_id: str) -> dict[str, Any] | None:
    path = ENRICHED_DIR / f"{event_cluster_id}_fact_pack.json"
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    obj["_fact_pack_path"] = str(path)
    return obj


def _sorted_events_for_queue(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(e: dict[str, Any]) -> tuple[int, int]:
        total = e.get("total_score")
        angle = e.get("angle_score")
        try:
            return (int(total) if total is not None else 0, int(angle) if angle is not None else 0)
        except (TypeError, ValueError):
            return (0, 0)

    return sorted(events, key=key, reverse=True)


def _select_event_ids(*, queue: str, limit: int) -> list[str]:
    q = (queue or "").strip()
    if q == "enriched_queue_review":
        ids: list[str] = []
        for r in _read_jsonl(ENRICHED_QUEUE_JSONL):
            eid = str(r.get("event_cluster_id") or "").strip()
            if eid:
                ids.append(eid)
            if len(ids) >= limit:
                break
        return ids

    ids: list[str] = []
    rows = [e for e in _read_jsonl(EVENTS_JSONL) if str(e.get("cluster_queue") or "").strip() == q]
    for e in _sorted_events_for_queue(rows)[:limit]:
        eid = str(e.get("event_cluster_id") or "").strip()
        if eid:
            ids.append(eid)
    return ids


def _render_md(brief: dict[str, Any]) -> str:
    eid = str(brief.get("event_cluster_id") or "").strip()
    title = str(brief.get("cluster_title") or "").strip()
    queue = str(brief.get("queue") or "").strip()
    event_type = str(brief.get("event_type") or "").strip()
    visual_mode = str(brief.get("visual_mode") or "").strip()
    usage_risk = str(brief.get("usage_risk") or "").strip()
    visual_strategy = str(brief.get("visual_strategy") or "").strip()
    auto_generate_allowed = bool(brief.get("auto_generate_allowed"))
    auto_publish_allowed = bool(brief.get("auto_publish_allowed"))

    out: list[str] = []
    out.append("# Visual Brief\n\n")
    out.append(f"- event_cluster_id: {eid}\n")
    out.append(f"- title: {title}\n")
    out.append(f"- queue: {queue}\n")
    out.append(f"- event_type: {event_type}\n")
    out.append(f"- visual_mode: {visual_mode}\n")
    out.append(f"- usage_risk: {usage_risk}\n")

    out.append("\n## Visual Strategy\n")
    out.append(f"- visual_strategy: {visual_strategy}\n")
    out.append(f"- auto_generate_allowed: {auto_generate_allowed}\n")
    out.append(f"- auto_publish_allowed: {auto_publish_allowed}\n")

    out.append("\n## Recommended Visual\n")
    out.append(f"{brief.get('recommended_visual') or ''}\n")

    out.append("\n## Image Search Queries\n")
    qs = brief.get("image_search_queries") or []
    if isinstance(qs, list) and qs:
        for q in qs[:8]:
            out.append(f"- {q}\n")
    else:
        out.append("- (empty)\n")

    out.append("\n## Meme / Image2 Direction\n")
    meme_angle = str(brief.get("meme_angle") or "").strip()
    if meme_angle:
        out.append(f"- meme_angle: {meme_angle}\n")
    image2_prompt = str(brief.get("image2_prompt") or "").strip()
    if image2_prompt:
        out.append("\n### image2_prompt\n")
        out.append(image2_prompt + "\n")
    else:
        out.append("- image2_prompt: (empty)\n")

    out.append("\n## Asset Usage Note\n")
    out.append(str(brief.get("asset_usage_note") or "").strip() + "\n")

    if visual_mode in {"data_card", "template_card"}:
        out.append("\n## Card Copy\n")
        out.append(f"- card_title: {brief.get('card_title') or ''}\n")
        out.append(f"- card_subtitle: {brief.get('card_subtitle') or ''}\n")
        out.append("\n### card_bullets\n")
        for x in (brief.get("card_bullets") or [])[:8]:
            out.append(f"- {x}\n")

    if visual_mode == "generated_image":
        out.append("\n## Generated Image Prompt\n")
        out.append("仅为候选，不自动生成，不自动发布。\n\n")
        out.append(str(brief.get("visual_prompt") or "").strip() + "\n")

    out.append("\n## Generated Card\n")
    gp = str(brief.get("generated_card_path") or "").strip()
    if gp:
        out.append(f"- {gp}\n")
    else:
        out.append("- (empty)\n")

    out.append("\n## Risk Notes\n")
    rrs = brief.get("risk_reasons") or []
    if rrs:
        for r in rrs[:12]:
            out.append(f"- {r}\n")
    else:
        out.append("- (empty)\n")

    out.append("\n## Reason\n")
    out.append(str(brief.get("reason") or "").strip() + "\n")

    out.append("\n## Image Candidates\n")
    cands = brief.get("image_candidates") or []
    if isinstance(cands, list) and cands:
        for c in cands[:10]:
            if not isinstance(c, dict):
                continue
            out.append(f"- {c.get('type')} url={c.get('url')} notes={c.get('notes')}\n")
    else:
        out.append("- (empty)\n")

    out.append(f"\n---\nGenerated at: {_utc_now_iso()}\n")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--queue",
        choices=["queue_review", "enriched_queue_review", "whale_digest", "source_research"],
        help="Build visual briefs for a queue",
    )
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--event-id", dest="event_id", default="")
    args = ap.parse_args()

    event_id = str(args.event_id or "").strip()
    queue = str(args.queue or "").strip()
    limit = int(args.limit or 0)
    if limit <= 0:
        limit = 3

    if not event_id and not queue:
        raise SystemExit("need --queue or --event-id")

    events_mp = _event_map()

    if event_id:
        eids = [event_id]
    else:
        eids = _select_event_ids(queue=queue, limit=limit)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    for eid in eids:
        ev = events_mp.get(eid)
        if not isinstance(ev, dict):
            continue
        q = queue or str(ev.get("cluster_queue") or "").strip()
        fp = _load_fact_pack(eid)
        brief = build_visual_brief(event=ev, queue=q, fact_pack=fp)
        if fp and isinstance(fp.get("_fact_pack_path"), str):
            brief["fact_pack_path"] = fp.get("_fact_pack_path")

        if bool(brief.get("auto_generate_allowed")) and str(brief.get("visual_strategy") or "") == "auto_template":
            tname = str(brief.get("template_name") or "").strip()
            if tname:
                card_path = render_template_card(
                    out_dir=OUT_CARDS_DIR,
                    event_cluster_id=eid,
                    template_name=tname,
                    brief=brief,
                )
                brief["generated_card_path"] = str(card_path)

        json_path = OUT_DIR / f"{eid}_visual_brief.json"
        md_path = OUT_DIR / f"{eid}_visual_brief.md"

        json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(_render_md(brief), encoding="utf-8")
        written += 1

    print(f"[build_visual_brief_once] ok queue={queue or '(by_event)'} requested={len(eids)} written={written} out_dir={OUT_DIR}")
    if not written:
        if queue:
            print(f"[build_visual_brief_once] queue={queue} is empty or no matching events found")


if __name__ == "__main__":
    main()

