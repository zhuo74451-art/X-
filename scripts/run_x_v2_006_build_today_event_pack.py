from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from adapters.import_integration_api import fetch_pool


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()


def _parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _pick_observed_at(obj: dict[str, Any]) -> datetime | None:
    for k in ["observed_at", "published_at", "received_at", "created_at", "ts", "time"]:
        dt = _parse_dt(str(obj.get(k) or ""))
        if dt is not None:
            return dt
    return None


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _is_web3_relevant(title: str, summary: str) -> bool:
    t = (title + " " + summary).lower()
    keywords = [
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "sol",
        "solana",
        "usdc",
        "usdt",
        "stablecoin",
        "sec",
        "etf",
        "crypto",
        "web3",
        "defi",
        "exchange",
        "binance",
        "coinbase",
        "layer2",
        "l2",
        "ton",
        "telegram",
        "wallet",
        "hack",
        "exploit",
    ]
    return any(k in t for k in keywords)


def _guess_event_type(title: str, summary: str) -> str:
    t = (title + " " + summary).lower()
    if any(k in t for k in ["whale", "onchain", "on-chain", "tx hash", "transfer", "lookonchain", "arkham"]):
        return "onchain"
    if any(k in t for k in ["etf", "sec", "fed", "cpi", "inflation", "rate", "macro"]):
        return "etf_macro"
    if any(k in t for k in ["sanction", "ofac", "lawsuit", "regulation", "regulatory", "compliance", "enforcement"]):
        return "regulation"
    if any(k in t for k in ["hack", "exploit", "drain", "breach", "stolen"]):
        return "security"
    if any(k in t for k in ["exchange", "trading", "fee", "order", "futures", "spot", "listing"]):
        return "market_structure"
    return "hot"


def _source_type_from_url(url: str) -> str:
    u = (url or "").lower()
    if any(x in u for x in ["sec.gov", "treasury.gov", "europa.eu", ".gov"]):
        return "official"
    if any(x in u for x in ["reuters.com", "bloomberg.com", "wsj.com", "ft.com"]):
        return "tier1_media"
    if any(x in u for x in ["coindesk.com", "decrypt.co", "cointelegraph.com", "theblock.co"]):
        return "tier1_media"
    if any(x in u for x in ["twitter.com", "x.com", "t.me", "telegram.me"]):
        return "community"
    return "unknown"


def _http_get_json(url: str, timeout_s: int = 8) -> Any:
    req = urllib.request.Request(url=url, method="GET", headers={"User-Agent": "x_automation_v2"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    return json.loads(body)


def _build_event_pack(
    *,
    event_id: str,
    title: str,
    summary: str,
    observed_at: str,
    source_mode: str,
    source_url: str,
) -> dict[str, Any]:
    et = _guess_event_type(title, summary)
    confirmed: list[str] = []
    if title:
        confirmed.append(_clip(title, 180))
    if summary:
        confirmed.append(_clip(summary, 220))
    should_not_claim = [
        "不要把二手传播写成确定事实",
        "不要写投资建议/喊单/价格预测",
        "不要断言主力操盘/洗盘/爆空",
    ]
    if et == "security":
        should_not_claim.append("安全事件不要定性跑路/归因具体团队/个人，除非 source_pack 明确支持")
    return {
        "event_id": event_id,
        "title": _clip(title, 220),
        "summary": _clip(summary, 420),
        "event_type": et,
        "assets": [],
        "source_pack": [
            {
                "title": _clip(title, 200),
                "url": source_url,
                "source_type": _source_type_from_url(source_url),
                "facts_supported": confirmed[:2],
            }
        ],
        "fact_pack": {"confirmed": confirmed[:3], "uncertain": [], "should_not_claim": should_not_claim},
        "risk_flags": [],
        "recommended_outputs": ["x_post", "reply"],
        "observed_at": observed_at,
        "source_mode": source_mode,
        "source_url": source_url,
        "source_url_missing": bool(not source_url),
    }


def _load_probe(root: Path) -> dict[str, Any]:
    p = root / "reports" / "x_v2_006_today_source_probe_report.json"
    if not p.exists():
        return {}
    obj = json.loads(p.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}


def _fetch_from_integration(pool: str) -> tuple[list[dict[str, Any]], str]:
    try:
        items = fetch_pool(pool=pool, limit=60)
        if not isinstance(items, list):
            return [], "invalid_response"
        return [x for x in items if isinstance(x, dict)], ""
    except Exception as e:
        return [], str(e)


def _fetch_from_server_streams(source_name: str) -> tuple[list[dict[str, Any]], str]:
    try:
        data = _http_get_json(source_name)
        items = []
        if isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            if isinstance(data.get("items"), list):
                items = [x for x in data["items"] if isinstance(x, dict)]
            elif isinstance(data.get("data"), list):
                items = [x for x in data["data"] if isinstance(x, dict)]
        return items, ""
    except Exception as e:
        return [], str(e)


def _fetch_from_article_export(path_str: str) -> tuple[list[dict[str, Any]], str]:
    p = Path(path_str)
    if not p.exists():
        return [], "export_not_found"
    out: list[dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
        return out, ""
    except Exception as e:
        return [], str(e)


def _dedupe_and_filter(
    raw: list[dict[str, Any]],
    *,
    source_mode: str,
    max_events: int = 5,
) -> list[dict[str, Any]]:
    now = _utc_now()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_6h = now - timedelta(hours=6)

    candidates: list[tuple[int, dict[str, Any]]] = []
    for it in raw:
        dt = _pick_observed_at(it)
        if dt is None or dt < cutoff_24h:
            continue

        title = ""
        summary = ""
        url = ""

        dp = it.get("delivery_payload") if isinstance(it.get("delivery_payload"), dict) else {}
        title = (dp.get("title") or it.get("zh_title") or it.get("title") or "").strip()
        summary = (dp.get("body") or it.get("zh_body") or it.get("summary") or it.get("content") or "").strip()
        url = (it.get("canonical_url") or it.get("article_url") or it.get("url") or it.get("link") or "").strip()

        if not title:
            continue
        if not _is_web3_relevant(title, summary):
            continue

        freshness_bucket = 2 if dt >= cutoff_6h else 1
        candidates.append(
            (
                freshness_bucket,
                {
                    "raw": it,
                    "title": title,
                    "summary": summary,
                    "source_url": url,
                    "observed_at": dt.replace(microsecond=0).isoformat(),
                    "source_mode": source_mode,
                },
            )
        )

    candidates.sort(key=lambda x: (x[0], x[1]["observed_at"]), reverse=True)

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for _, c in candidates:
        key = _sha1((c.get("source_url") or "") + "|" + c.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        eid = "today_v006_" + _sha1((c.get("source_url") or "") + "|" + c.get("observed_at", "") + "|" + c.get("title", ""))[:12]
        out.append(
            _build_event_pack(
                event_id=eid,
                title=c.get("title") or "",
                summary=c.get("summary") or "",
                observed_at=c.get("observed_at") or _utc_now_iso(),
                source_mode=source_mode,
                source_url=c.get("source_url") or "",
            )
        )
        if len(out) >= max_events:
            break
    return out


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    data_dir = root / "data"
    reports_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    probe = _load_probe(root)
    selected = probe.get("selected_source") if isinstance(probe.get("selected_source"), dict) else {}
    source_mode = str(selected.get("selected_source_mode") or "blocked_no_real_source")
    source_name = str(selected.get("source_name") or "")

    raw: list[dict[str, Any]] = []
    err = ""
    if source_mode == "integration_published_real":
        raw, err = _fetch_from_integration("published")
    elif source_mode == "integration_ready_real":
        raw, err = _fetch_from_integration("ready")
    elif source_mode == "server_streams_real":
        raw, err = _fetch_from_server_streams(source_name)
    elif source_mode == "article_hotspot_export_real":
        raw, err = _fetch_from_article_export(source_name)
    else:
        err = "BLOCKED_NO_REAL_SOURCE"

    events = _dedupe_and_filter(raw, source_mode=source_mode, max_events=5)
    out_jsonl = data_dir / "today_real_event_pack_v006.jsonl"

    if len(events) < 3:
        report = {
            "task_id": "x_v2_006_today_real_hotspot_dryrun",
            "generated_at_utc": _utc_now_iso(),
            "status": "BLOCKED_NO_REAL_SOURCE",
            "selected_source_mode": source_mode,
            "source_name": source_name,
            "blocked_reason": err or "insufficient_today_events",
            "event_count": len(events),
        }
        _write_json(reports_dir / "x_v2_006_today_event_pack_report.json", report)
        (reports_dir / "x_v2_006_today_event_pack_report.md").write_text(
            "# X v2-006 Today Event Pack Report\n\n"
            f"- status: blocked\n- selected_source_mode: {source_mode}\n- event_count: {len(events)}\n- blocked_reason: {report['blocked_reason']}\n",
            encoding="utf-8",
        )
        if out_jsonl.exists():
            out_jsonl.unlink()
        raise SystemExit(2)

    with out_jsonl.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    observed = [e.get("observed_at") for e in events if isinstance(e.get("observed_at"), str) and e.get("observed_at")]
    latest = max(observed) if observed else ""
    oldest = min(observed) if observed else ""
    event_types = sorted({str(e.get("event_type") or "") for e in events})

    report = {
        "task_id": "x_v2_006_today_real_hotspot_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "status": "DONE",
        "selected_source_mode": source_mode,
        "source_name": source_name,
        "event_count": len(events),
        "event_types": event_types,
        "latest_event_at": latest,
        "oldest_event_at": oldest,
        "output_jsonl": str(out_jsonl),
    }
    _write_json(reports_dir / "x_v2_006_today_event_pack_report.json", report)

    md: list[str] = []
    md.append("# X v2-006 Today Event Pack Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- status: {report.get('status')}\n")
    md.append(f"- selected_source_mode: {report.get('selected_source_mode')}\n")
    md.append(f"- event_count: {report.get('event_count')}\n")
    md.append(f"- event_types: {', '.join(event_types)}\n")
    md.append(f"- latest_event_at: {latest}\n")
    md.append(f"- oldest_event_at: {oldest}\n\n")
    md.append("## Events\n")
    for e in events:
        md.append("\n---\n")
        md.append(f"- event_id: {e.get('event_id')}\n")
        md.append(f"- observed_at: {e.get('observed_at')}\n")
        md.append(f"- event_type: {e.get('event_type')}\n")
        md.append(f"- title: {e.get('title')}\n")
        md.append(f"- source_url: {e.get('source_url')}\n")
        md.append(f"- source_url_missing: {str(e.get('source_url_missing')).lower()}\n")
    (reports_dir / "x_v2_006_today_event_pack_report.md").write_text("".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()

