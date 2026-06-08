from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from core.event.event_schema import clamp_score


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", s)
    s = s.strip("_")[:80]
    if s:
        return s
    return hashlib.sha1((text or "event").encode("utf-8")).hexdigest()[:16]


def event_id_from_title(title: str) -> str:
    digest = hashlib.sha1((title or "event").encode("utf-8")).hexdigest()[:10]
    return f"evt_{slug(title)[:40]}_{digest}"


def source_diversity(source_names: list[str]) -> int:
    cleaned = {str(x or "").strip().lower() for x in source_names if str(x or "").strip()}
    return max(1, len(cleaned))


def fact_anchor(source_count: int, best_source_rank: int, risk_level: str) -> str:
    if best_source_rank <= 1 and source_count >= 2:
        return "confirmed"
    if source_count >= 2 and best_source_rank <= 3:
        return "multi_source"
    if (risk_level or "").lower() == "high" and source_count <= 1:
        return "rumor_only"
    return "single_source"


def lifecycle_status(heat_score: int, velocity: float, anchor: str, existing_status: str = "") -> str:
    if existing_status == "dead":
        return "dead"
    if anchor == "rumor_only" and heat_score < 75:
        return "emerging"
    if heat_score >= 75 and velocity >= 0:
        return "hot"
    if heat_score >= 65 and velocity < 0:
        return "peaking"
    if heat_score >= 35:
        return "cooling"
    return "emerging"


def heat_velocity(new_heat: int, old_event: dict[str, Any] | None) -> float:
    if not old_event:
        return float(new_heat)
    old_heat = int(old_event.get("heat_score") or 0)
    return float(new_heat - old_heat)


def risk_flags_from_text(text: str) -> list[str]:
    t = (text or "").lower()
    flags: list[str] = []
    if any(x in t for x in ["sec", "监管", "法院", "起诉", "法案"]):
        flags.append("regulation")
    if any(x in t for x in ["黑客", "被黑", "hack", "exploit", "漏洞"]):
        flags.append("security")
    if any(x in t for x in ["交易所", "暂停提币", "挤兑", "暴雷"]):
        flags.append("exchange_risk")
    if any(x in t for x in ["巨鲸", "链上", "0x", "whale"]):
        flags.append("onchain")
    if any(x in t for x in ["稳定币", "stablecoin", "usdc", "usdt"]):
        flags.append("stablecoin")
    return sorted(set(flags))


def event_from_hot_engine(raw: dict[str, Any], old_event: dict[str, Any] | None = None) -> dict[str, Any]:
    title = str(raw.get("cluster_title") or raw.get("title") or "Untitled event").strip()
    event_id = str(raw.get("event_cluster_id") or "").strip() or event_id_from_title(title)
    source_names = raw.get("source_names") if isinstance(raw.get("source_names"), list) else []
    src_div = source_diversity([str(x) for x in source_names])
    best_rank = int(raw.get("best_source_rank") or 9)
    risk_level = str(raw.get("risk_level") or "medium")
    total_score = clamp_score(raw.get("total_score") or raw.get("audience_reach_score") or 0)
    signal_count = int(raw.get("item_count") or len(raw.get("included_tweet_ids") or []) or 1)
    anchor = fact_anchor(src_div, best_rank, risk_level)
    velocity = heat_velocity(total_score, old_event)
    old_status = str(old_event.get("status") or "") if old_event else ""
    status = lifecycle_status(total_score, velocity, anchor, old_status)
    stamp = now_iso()
    first_seen = old_event.get("first_seen") if old_event else stamp
    text = " ".join([title, str(raw.get("raw_summary") or ""), str(raw.get("rule_reason") or "")])
    return {
        "event_id": event_id,
        "title": title,
        "status": status,
        "first_seen": first_seen,
        "last_update": stamp,
        "signal_count": signal_count,
        "source_diversity": src_div,
        "fact_anchor": anchor,
        "entities": raw.get("entities") if isinstance(raw.get("entities"), list) else [],
        "heat_score": total_score,
        "heat_velocity": velocity,
        "risk_level": risk_level,
        "risk_flags": risk_flags_from_text(text),
        "summary": str(raw.get("raw_summary") or raw.get("rule_reason") or ""),
        "created_at": old_event.get("created_at") if old_event else stamp,
        "updated_at": stamp,
    }


def recommended_action(event: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    previous = {str(x.get("action_type") or "") for x in actions}
    if "official_post" in previous and event.get("heat_velocity", 0) <= 5:
        return "reject"
    if event.get("fact_anchor") == "rumor_only":
        return "monitor_only"
    if event.get("status") == "hot" and event.get("fact_anchor") in {"confirmed", "multi_source"}:
        return "official_post"
    if event.get("status") == "peaking":
        return "reply_or_quote"
    if event.get("status") == "cooling":
        return "monitor_only"
    return "monitor_only"
