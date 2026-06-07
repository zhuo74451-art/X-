from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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


def _parse_rfc822_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"]:
        try:
            return datetime.strptime(s, fmt).astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _strip_html(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fetch_rss(url: str, timeout_s: int = 20) -> list[dict[str, Any]]:
    req = urllib.request.Request(url=url, method="GET", headers={"User-Agent": "x_automation_v2"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    root = ET.fromstring(body)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        dt = _parse_rfc822_date(pub)
        items.append(
            {
                "title": title,
                "url": link,
                "observed_at": dt.replace(microsecond=0).isoformat() if dt else "",
                "summary": _strip_html(desc),
            }
        )
    return items


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
    return "unknown"


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _build_event_pack(*, title: str, summary: str, url: str, observed_at: str) -> dict[str, Any]:
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
    event_id = "rss_v007_" + _sha1(url + "|" + (observed_at or ""))[:12]
    return {
        "event_id": event_id,
        "title": _clip(title, 220),
        "summary": _clip(summary, 420),
        "event_type": et,
        "assets": [],
        "source_pack": [
            {"title": _clip(title, 200), "url": url, "source_type": _source_type_from_url(url), "facts_supported": confirmed[:2]}
        ],
        "fact_pack": {"confirmed": confirmed[:3], "uncertain": [], "should_not_claim": should_not_claim},
        "risk_flags": [],
        "recommended_outputs": ["x_post", "reply"],
        "observed_at": observed_at,
        "source_mode": "public_rss_real",
        "source_url": url,
        "source_url_missing": False,
    }


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    data_dir = root / "data"
    reports_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    allowlist = [
        {"name": "Coindesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss"},
        {"name": "Decrypt", "url": "https://decrypt.co/feed"},
    ]

    now = _utc_now()
    cutoff = now - timedelta(hours=24)

    fetched: list[dict[str, Any]] = []
    errors: list[str] = []
    for src in allowlist:
        try:
            items = _fetch_rss(src["url"])
            fetched.extend([{**x, "feed_name": src["name"], "feed_url": src["url"]} for x in items[:20]])
        except Exception as e:
            errors.append(f"{src['name']}:{str(e)}")
        time.sleep(0.2)

    filtered: list[dict[str, Any]] = []
    for it in fetched:
        title = str(it.get("title") or "").strip()
        url = str(it.get("url") or "").strip()
        observed_at = str(it.get("observed_at") or "").strip()
        dt = None
        if observed_at:
            try:
                dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                dt = None
        if not (title and url and dt is not None and dt >= cutoff):
            continue
        filtered.append(it)

    filtered.sort(key=lambda x: x.get("observed_at") or "", reverse=True)

    out_events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in filtered:
        if len(out_events) >= 5:
            break
        url = str(it.get("url") or "")
        key = _sha1(url)
        if key in seen:
            continue
        seen.add(key)
        out_events.append(
            _build_event_pack(
                title=str(it.get("title") or ""),
                summary=str(it.get("summary") or ""),
                url=url,
                observed_at=str(it.get("observed_at") or ""),
            )
        )

    out_jsonl = data_dir / "public_rss_event_pack_v007.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for e in out_events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    report = {
        "task_id": "x_v2_007_real_hotspot_rewrite_and_rss_fallback",
        "generated_at_utc": _utc_now_iso(),
        "source_mode": "public_rss_real",
        "allowlist": allowlist,
        "pulled_items_total": len(fetched),
        "filtered_last_24h": len(filtered),
        "selected_count": len(out_events),
        "latest_observed_at": (out_events[0].get("observed_at") if out_events else ""),
        "errors": errors,
        "output_jsonl": str(out_jsonl),
        "safety": {"x_api_connected": False, "x_published": False},
    }
    _write_json(reports_dir / "x_v2_007_public_rss_fallback_report.json", report)

    md: list[str] = []
    md.append("# X v2-007 Public RSS Fallback Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- source_mode: public_rss_real\n")
    md.append(f"- pulled_items_total: {report.get('pulled_items_total')}\n")
    md.append(f"- filtered_last_24h: {report.get('filtered_last_24h')}\n")
    md.append(f"- selected_count: {report.get('selected_count')}\n")
    md.append(f"- latest_observed_at: {report.get('latest_observed_at')}\n")
    if errors:
        md.append(f"- errors: {json.dumps(errors, ensure_ascii=False)}\n")
    md.append("\n## Selected Events\n")
    for e in out_events:
        md.append("\n---\n")
        md.append(f"- event_id: {e.get('event_id')}\n")
        md.append(f"- observed_at: {e.get('observed_at')}\n")
        md.append(f"- event_type: {e.get('event_type')}\n")
        md.append(f"- title: {e.get('title')}\n")
        md.append(f"- source_url: {e.get('source_url')}\n")
    (reports_dir / "x_v2_007_public_rss_fallback_report.md").write_text("".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()

