from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from fact_pack_builder import build_fact_pack, render_fact_pack_md


ROOT = Path(__file__).resolve().parents[2]
EVENTS_JSONL = ROOT / "out" / "hot_engine_queues" / "events.jsonl"
OUT_DIR = ROOT / "out" / "enriched_events"
CONFIG_DIR = ROOT / "configs"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_index_line(event_cluster: dict[str, Any], fact_pack: dict[str, Any], fact_pack_path: Path) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_path = OUT_DIR / "enriched_index.jsonl"
    rec = {
        "created_at": _utc_now_iso(),
        "event_cluster_id": str(event_cluster.get("event_cluster_id") or ""),
        "cluster_title": str(event_cluster.get("cluster_title") or ""),
        "event_type": str(fact_pack.get("event_type") or ""),
        "source_risk": str(fact_pack.get("source_risk") or ""),
        "upgrade_recommendation": str(fact_pack.get("upgrade_recommendation") or ""),
        "fact_pack_path": str(fact_pack_path),
    }
    with index_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"events.jsonl not found: {path}")
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _select_by_queue(events: list[dict[str, Any]], queue: str, limit: int) -> list[dict[str, Any]]:
    q = (queue or "").strip()
    picked = [e for e in events if str(e.get("cluster_queue") or "") == q]
    return picked[: max(0, int(limit))]


def _select_by_id(events: list[dict[str, Any]], event_id: str) -> dict[str, Any]:
    eid = (event_id or "").strip()
    for e in events:
        if str(e.get("event_cluster_id") or "") == eid:
            return e
    raise ValueError(f"event_cluster_id not found: {eid}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", default="", help="event_cluster_id")
    ap.add_argument("--queue", default="", help="queue name, e.g. source_research")
    ap.add_argument("--limit", type=int, default=1, help="limit when using --queue")
    ap.add_argument("--search-provider", default="", help="mock|tavily|brave|serpapi (override env)")
    ap.add_argument("--max-results-per-query", type=int, default=5, help="max results per query")
    ap.add_argument("--no-web-search", action="store_true", help="force mock and skip real web search")
    args = ap.parse_args()

    if not args.event_id and not args.queue:
        raise SystemExit("need --event-id or --queue")

    events = _read_events(EVENTS_JSONL)
    targets: list[dict[str, Any]] = []
    if args.event_id:
        targets = [_select_by_id(events, args.event_id)]
    else:
        targets = _select_by_queue(events, args.queue, args.limit)

    if not targets:
        print(f"[enrich_event_once] no events selected (queue={args.queue} limit={args.limit})")
        return

    for e in targets:
        eid = str(e.get("event_cluster_id") or "")
        title = str(e.get("cluster_title") or "")
        print(f"[enrich_event_once] enriching event_cluster_id={eid} title={title}")

        provider = (args.search_provider or os.getenv("ENRICHMENT_SEARCH_PROVIDER") or "mock").strip().lower()
        if args.no_web_search:
            provider = "mock"

        pack = build_fact_pack(
            event_cluster=e,
            config_dir=CONFIG_DIR,
            output_dir=OUT_DIR,
            search_provider=provider,
            max_results_per_query=int(args.max_results_per_query),
            no_web_search=bool(args.no_web_search),
        )
        md = render_fact_pack_md(event_cluster=e, fact_pack=pack)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        md_path = OUT_DIR / f"{eid}_fact_pack.md"
        md_path.write_text(md, encoding="utf-8")
        _append_index_line(e, pack, OUT_DIR / f"{eid}_fact_pack.json")

        print(f"[enrich_event_once] wrote: {OUT_DIR / (eid + '_fact_pack.json')}")
        print(f"[enrich_event_once] wrote: {md_path}")
        print(f"[enrich_event_once] upgrade_recommendation={pack.get('upgrade_recommendation')}")


if __name__ == "__main__":
    main()

