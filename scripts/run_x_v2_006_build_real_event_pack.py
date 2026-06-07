from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.import_integration_api import fetch_pool


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()


def _parse_rfc822_date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z")
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return ""


def _strip_html(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fetch_rss(url: str, timeout_s: int = 20) -> list[dict[str, str]]:
    req = urllib.request.Request(url=url, method="GET", headers={"User-Agent": "x_automation_v2"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    root = ET.fromstring(body)
    items: list[dict[str, str]] = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        items.append(
            {
                "title": title,
                "url": link,
                "published_at": _parse_rfc822_date(pub),
                "summary": _strip_html(desc),
            }
        )
    return items


def _guess_event_type(title: str, summary: str) -> str:
    t = (title + " " + summary).lower()
    if any(k in t for k in ["etf", "sec", "fed", "rate", "inflation", "cpi", "macro", "treasury"]):
        return "macro"
    if any(k in t for k in ["ofac", "sanction", "lawsuit", "regulation", "regulatory", "compliance", "enforcement"]):
        return "case_data_regulation"
    if any(k in t for k in ["exchange", "binance", "coinbase", "fee", "trading", "order", "futures", "spot"]):
        return "industry_structure"
    if any(k in t for k in ["whale", "lookonchain", "arkham", "on-chain", "onchain", "transfer"]):
        return "whale"
    return "hot"


def _source_type_from_url(url: str) -> str:
    u = (url or "").lower()
    if any(x in u for x in ["reuters.com", "bloomberg.com", "wsj.com", "ft.com"]):
        return "tier1_media"
    if any(x in u for x in ["coindesk.com", "decrypt.co", "cointelegraph.com", "theblock.co"]):
        return "tier1_media"
    if any(x in u for x in ["gov", "sec.gov", "ofac", "treasury.gov", "europa.eu"]):
        return "official"
    return "unknown"


def _build_event_pack(
    *,
    event_id: str,
    title: str,
    summary: str,
    url: str,
    observed_at: str,
    source_mode: str,
) -> dict[str, Any]:
    event_type = _guess_event_type(title, summary)
    confirmed = []
    if title:
        confirmed.append(_clip(title, 160))
    if summary:
        confirmed.append(_clip(summary, 200))
    should_not_claim = [
        "不要把二手传播写成确定事实",
        "不要写投资建议/喊单/价格预测",
        "不要断言主力操盘/洗盘/爆空",
    ]
    return {
        "event_id": event_id,
        "title": _clip(title, 220),
        "summary": _clip(summary, 360),
        "event_type": event_type,
        "assets": [],
        "source_pack": [
            {
                "title": _clip(title, 200),
                "url": url,
                "source_type": _source_type_from_url(url),
                "facts_supported": confirmed[:2],
            }
        ],
        "fact_pack": {
            "confirmed": confirmed[:3],
            "uncertain": [],
            "should_not_claim": should_not_claim,
        },
        "risk_flags": [],
        "image_candidates": [],
        "recommended_outputs": ["x_post", "reply"],
        "review_required": True,
        "created_at": _utc_now_iso(),
        "observed_at": observed_at or _utc_now_iso(),
        "source_mode": source_mode,
    }


def _try_integration_published(limit: int = 20) -> tuple[list[dict[str, Any]], str]:
    try:
        items = fetch_pool(pool="published", limit=limit)
    except Exception as e:
        return [], f"integration_published_fetch_failed: {str(e)}"

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        dp = it.get("delivery_payload") if isinstance(it.get("delivery_payload"), dict) else {}
        title = (dp.get("title") or it.get("zh_title") or "").strip()
        body = (dp.get("body") or it.get("zh_body") or "").strip()
        url = (it.get("canonical_url") or it.get("article_url") or "").strip()
        observed_at = str(it.get("published_at") or it.get("received_at") or "").strip()
        tweet_id = str(it.get("tweet_id") or "").strip()
        if not (tweet_id and title and body):
            continue
        out.append(
            _build_event_pack(
                event_id=f"real_v006_int_{tweet_id}",
                title=title,
                summary=body,
                url=url,
                observed_at=observed_at,
                source_mode="integration_published_real",
            )
        )
        if len(out) >= 5:
            break
    return out, ""


def _try_rss_fallback(min_events: int = 3) -> tuple[list[dict[str, Any]], str, list[str]]:
    feeds = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
    ]
    fetched: list[dict[str, Any]] = []
    errors: list[str] = []
    used_feeds: list[str] = []

    for url in feeds:
        try:
            items = _fetch_rss(url)
            used_feeds.append(url)
            fetched.extend(items[:8])
        except Exception as e:
            errors.append(f"rss_fetch_failed:{url}:{str(e)}")
        time.sleep(0.2)

    out: list[dict[str, Any]] = []
    for it in fetched:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        summary = (it.get("summary") or "").strip()
        observed_at = (it.get("published_at") or "").strip()
        if not (title and url):
            continue
        eid = "real_v006_rss_" + _sha1(url + "|" + (observed_at or ""))[:12]
        out.append(
            _build_event_pack(
                event_id=eid,
                title=title,
                summary=summary,
                url=url,
                observed_at=observed_at,
                source_mode="local_latest_stream_real",
            )
        )
        if len(out) >= 5:
            break

    if len(out) < min_events:
        return out, "rss_real_source_insufficient", used_feeds + errors
    return out, "", used_feeds


def main() -> None:
    root = _project_root()
    data_dir = root / "data"
    reports_dir = root / "reports"
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    event_packs: list[dict[str, Any]] = []
    source_mode = "blocked_no_real_source"
    blocked_reason = ""
    source_trace: list[str] = []

    int_events, int_err = _try_integration_published()
    if int_events:
        event_packs = int_events
        source_mode = "integration_published_real"
    else:
        blocked_reason = int_err or "integration_published_empty"
        source_trace.append(blocked_reason)

    if len(event_packs) < 3:
        rss_events, rss_err, trace = _try_rss_fallback()
        source_trace.extend(trace)
        if rss_events:
            event_packs = rss_events
            source_mode = "local_latest_stream_real"
        else:
            source_mode = "blocked_no_real_source"
            blocked_reason = blocked_reason or rss_err or "BLOCKED_NO_REAL_EVENT_SOURCE"

    out_jsonl = data_dir / "real_event_pack_v006.jsonl"
    if source_mode == "blocked_no_real_source" or len(event_packs) < 3:
        report = {
            "task_id": "x_v2_006_real_event_pack",
            "generated_at_utc": _utc_now_iso(),
            "status": "BLOCKED_NO_REAL_EVENT_SOURCE",
            "source_mode": "blocked_no_real_source",
            "real_event_count": len(event_packs),
            "blocked_reason": blocked_reason or "BLOCKED_NO_REAL_EVENT_SOURCE",
            "source_trace": source_trace[:20],
        }
        _write_json(reports_dir / "x_v2_006_real_event_pack_report.json", report)
        (reports_dir / "x_v2_006_real_event_pack_report.md").write_text(
            "# X v2-006 Real Event Pack Report\n\n"
            f"- status: blocked\n- source_mode: blocked_no_real_source\n- real_event_count: {len(event_packs)}\n"
            f"- blocked_reason: {report['blocked_reason']}\n",
            encoding="utf-8",
        )
        if out_jsonl.exists():
            out_jsonl.unlink()
        raise SystemExit(2)

    with out_jsonl.open("w", encoding="utf-8") as f:
        for e in event_packs:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    report = {
        "task_id": "x_v2_006_real_event_pack",
        "generated_at_utc": _utc_now_iso(),
        "status": "DONE",
        "source_mode": source_mode,
        "real_event_count": len(event_packs),
        "blocked_reason": blocked_reason,
        "source_trace": source_trace[:20],
        "output_jsonl": str(out_jsonl),
        "sample_event_ids": [str(x.get("event_id") or "") for x in event_packs[:5]],
    }
    _write_json(reports_dir / "x_v2_006_real_event_pack_report.json", report)

    md: list[str] = []
    md.append("# X v2-006 Real Event Pack Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- status: {report.get('status')}\n")
    md.append(f"- source_mode: {report.get('source_mode')}\n")
    md.append(f"- real_event_count: {report.get('real_event_count')}\n")
    if blocked_reason:
        md.append(f"- blocked_reason: {blocked_reason}\n")
    md.append("\n## Sample Events\n")
    for e in event_packs[:5]:
        md.append("\n---\n")
        md.append(f"- event_id: {e.get('event_id')}\n")
        md.append(f"- observed_at: {e.get('observed_at')}\n")
        md.append(f"- event_type: {e.get('event_type')}\n")
        md.append(f"- title: {e.get('title')}\n")
        sp = (e.get("source_pack") or [])
        if isinstance(sp, list) and sp:
            md.append(f"- source_url: {sp[0].get('url')}\n")
    (reports_dir / "x_v2_006_real_event_pack_report.md").write_text("".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()

