from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVENTS_JSONL = ROOT / "out" / "hot_engine_queues" / "events.jsonl"
ENRICHED_INDEX = ROOT / "out" / "enriched_events" / "enriched_index.jsonl"
ENRICHED_DIR = ROOT / "out" / "enriched_events"
OUT_JSONL = ROOT / "out" / "hot_engine_queues" / "enriched_queue_review.jsonl"
OUT_MD = ROOT / "out" / "hot_engine_queues" / "enriched_queue_review.md"
OUT_NOT_PROMOTED_JSONL = ROOT / "out" / "hot_engine_queues" / "enriched_not_promoted.jsonl"
OUT_NOT_PROMOTED_MD = ROOT / "out" / "hot_engine_queues" / "enriched_not_promoted.md"


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


def _latest_index_by_event() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for rec in _read_jsonl(ENRICHED_INDEX):
        eid = str(rec.get("event_cluster_id") or "").strip()
        if not eid:
            continue
        latest[eid] = rec
    return latest


def _event_ids_with_fact_pack() -> list[str]:
    out: list[str] = []
    for fp in sorted(ENRICHED_DIR.glob("*_fact_pack.json")):
        name = fp.name
        if not name.endswith("_fact_pack.json"):
            continue
        eid = name[: -len("_fact_pack.json")]
        if eid:
            out.append(eid)
    return out


def _count_tiers(best_sources: list[dict[str, Any]]) -> tuple[int, int]:
    p0 = 0
    p1 = 0
    for s in best_sources:
        t = str(s.get("tier") or "")
        if t == "P0":
            p0 += 1
        elif t == "P1":
            p1 += 1
    return p0, p1


def _missing_required_count(fact_pack: dict[str, Any]) -> int:
    rfs = fact_pack.get("required_facts_status")
    if isinstance(rfs, dict):
        missing = rfs.get("missing")
        if isinstance(missing, list):
            return len([x for x in missing if str(x).strip()])
    return 999


def _as_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return int(x)
        return int(x)
    except (TypeError, ValueError):
        return default


def _norm_text(*parts: Any) -> str:
    segs: list[str] = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, str):
            s = p.strip()
            if s:
                segs.append(s)
        else:
            s = str(p).strip()
            if s and s != "None":
                segs.append(s)
    return "\n".join(segs)


def _topic_priority_is_high(tp: str) -> bool:
    s = (tp or "").strip().lower()
    if s in {"top", "high"}:
        return True
    if s.startswith("p"):
        try:
            n = int(s[1:])
            return n <= 1
        except ValueError:
            return False
    return False


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords if k)


def _has_nonnegated_occurrence(text: str, keyword: str) -> bool:
    if not keyword:
        return False
    neg_markers = ["无", "不", "未", "没有", "暂无", "并非"]
    i = 0
    while True:
        j = text.find(keyword, i)
        if j < 0:
            return False
        window = text[max(0, j - 6) : j]
        if not _contains_any(window, neg_markers):
            return True
        i = j + max(1, len(keyword))


def _has_strong_exchange_hook(text: str) -> bool:
    strong = [
        "暂停提款",
        "暂停提币",
        "提币暂停",
        "充提关闭",
        "暂停充提",
        "暂停充币",
        "暂停提币",
        "提款关闭",
        "无法提款",
        "无法提币",
        "被盗",
        "黑客",
        "攻击",
        "漏洞",
        "exploit",
        "phishing",
        "监管",
        "执法",
        "罚款",
        "起诉",
        "调查",
        "冻结",
        "破产",
        "挤兑",
        "清算",
        "爆仓",
        "宕机",
        "无法登录",
        "资产损失",
        "用户资金",
        "资金安全",
        "恐慌",
        "价格异常",
        "暴跌",
        "暴涨",
    ]
    return _contains_any(text, strong)


def _is_routine_exchange_update(event: dict[str, Any], fact_pack: dict[str, Any]) -> bool:
    txt = _norm_text(
        event.get("cluster_title"),
        event.get("raw_summary"),
        " ".join(event.get("source_names") or []) if isinstance(event.get("source_names"), list) else "",
        fact_pack.get("event_type"),
        " ".join([str(x) for x in (fact_pack.get("angle_candidates") or [])]) if isinstance(fact_pack.get("angle_candidates"), list) else "",
    )
    routine = [
        "交易对",
        "交易对调整",
        "永续合约下架",
        "下架永续",
        "下架",
        "delist",
        "下线",
        "上线",
        "上落价位",
        "价格档位",
        "手续费调整",
        "费率调整",
        "系统维护",
        "钱包维护",
        "维护公告",
        "普通公告",
        "公告",
        "api 调整",
        "api调整",
        "合约参数调整",
        "合约参数",
        "杠杆调整",
        "保证金调整",
        "资金费率调整",
        "产品更新",
    ]
    return _contains_any(txt, routine)


def _is_routine_market_flow(event: dict[str, Any], fact_pack: dict[str, Any]) -> bool:
    txt = _norm_text(
        event.get("cluster_title"),
        event.get("raw_summary"),
        fact_pack.get("event_type"),
        " ".join([str(x) for x in (fact_pack.get("confirmed_facts") or [])]) if isinstance(fact_pack.get("confirmed_facts"), list) else "",
        " ".join([str(x) for x in (fact_pack.get("angle_candidates") or [])]) if isinstance(fact_pack.get("angle_candidates"), list) else "",
    )
    flow_markers = ["etf", "现货 etf", "现货etf", "净流入", "净流出", "资金流", "flow", "inflow", "outflow"]
    if not _contains_any(txt, flow_markers):
        return False
    strong_hooks = [
        "创纪录",
        "历史最大",
        "历史新高",
        "连续",
        "异常",
        "背离",
        "价格大跌",
        "价格大涨",
        "暴跌",
        "暴涨",
        "流动性冲击",
        "机构赎回",
        "贝莱德",
        "ibit",
        "富达",
        "fbtc",
    ]
    has_strong = False
    for kw in strong_hooks:
        if kw in {"ibit", "fbtc"}:
            if kw in txt.lower():
                has_strong = True
                break
            continue
        if _has_nonnegated_occurrence(txt, kw):
            has_strong = True
            break
    return not has_strong


def _has_user_or_market_impact(fact_pack: dict[str, Any], event: dict[str, Any]) -> bool:
    txt = _norm_text(
        event.get("cluster_title"),
        event.get("raw_summary"),
        " ".join([str(x) for x in (fact_pack.get("angle_candidates") or [])]) if isinstance(fact_pack.get("angle_candidates"), list) else "",
        " ".join([str(x) for x in (fact_pack.get("confirmed_facts") or [])]) if isinstance(fact_pack.get("confirmed_facts"), list) else "",
    )
    signals = [
        "用户",
        "散户",
        "恐慌",
        "资金安全",
        "资产",
        "提款",
        "提币",
        "充提",
        "冻结",
        "无法登录",
        "宕机",
        "清算",
        "爆仓",
        "价格",
        "暴跌",
        "暴涨",
        "流动性",
    ]
    return _contains_any(txt, signals)


def should_promote_enriched_event(event: dict[str, Any], fact_pack: dict[str, Any]) -> dict[str, Any]:
    audience_reach_score = _as_int(event.get("audience_reach_score"), 0)
    angle_score = _as_int(event.get("angle_score"), 0)
    content_score = _as_int(event.get("content_score"), 0)
    total_score = _as_int(event.get("total_score"), 0)
    topic_priority = str(event.get("topic_priority") or "").strip()

    event_type = str(fact_pack.get("event_type") or event.get("event_type") or "").strip()
    combined_text = _norm_text(event.get("cluster_title"), event.get("raw_summary"))

    demotion_reasons: list[str] = []
    promotion_reasons: list[str] = []

    if _is_routine_market_flow(event, fact_pack):
        demotion_reasons.append("routine_market_flow_low_virality")

    routine_exchange_update = _is_routine_exchange_update(event, fact_pack)
    if routine_exchange_update:
        if _has_strong_exchange_hook(combined_text) or _contains_any(
            event_type, ["security_incident", "exchange_risk", "crypto_regulation"]
        ):
            promotion_reasons.append("routine_exchange_update_but_strong_hook")
        else:
            demotion_reasons.append("routine_exchange_update_low_virality")

    user_impact_ok = _has_user_or_market_impact(fact_pack, event)
    if user_impact_ok:
        promotion_reasons.append("has_user_or_market_impact")

    gate_a = audience_reach_score >= 70
    gate_b = angle_score >= 75
    gate_c = total_score >= 76
    gate_d = _topic_priority_is_high(topic_priority)
    gate_e = (event_type in {"ai_crypto_story", "security_incident", "exchange_risk", "macro_market"}) and user_impact_ok

    angle_candidates = fact_pack.get("angle_candidates") if isinstance(fact_pack.get("angle_candidates"), list) else []
    gate_f = _contains_any(_norm_text(" ".join([str(x) for x in angle_candidates])), ["用户", "资金", "提款", "恐慌", "价格", "市场", "流动性"])

    if gate_a:
        promotion_reasons.append("audience_reach_score>=70")
    if gate_b:
        promotion_reasons.append("angle_score>=75")
    if gate_c:
        promotion_reasons.append("total_score>=76")
    if gate_d:
        promotion_reasons.append("topic_priority_high_or_top")
    if gate_e:
        promotion_reasons.append("strong_event_type_with_user_impact")
    if gate_f:
        promotion_reasons.append("angle_candidates_show_impact")

    promotion_score = max(audience_reach_score, angle_score, content_score, total_score, 0)
    if gate_d:
        promotion_score += 5
    if gate_e:
        promotion_score += 5
    promotion_score = min(100, promotion_score)

    score_gate_ok = gate_a or gate_b or gate_c or gate_d or gate_e or gate_f
    routine_blocked = "routine_exchange_update_low_virality" in demotion_reasons
    promote = bool(score_gate_ok and not routine_blocked and not ("routine_market_flow_low_virality" in demotion_reasons))

    lack_reasons: list[str] = []
    if not score_gate_ok:
        lack_reasons.append("promotion_gate_not_met")
    demotion_reasons = [x for x in demotion_reasons if str(x).strip()]
    promotion_reasons = list(dict.fromkeys([x for x in promotion_reasons if str(x).strip()]))

    why_not = ""
    if not promote:
        why_not = "; ".join(demotion_reasons + lack_reasons) if (demotion_reasons or lack_reasons) else "not_promoted"

    return {
        "promote": promote,
        "promotion_score": promotion_score,
        "promotion_reasons": promotion_reasons,
        "demotion_reasons": demotion_reasons,
        "why_not_promoted": why_not,
        "audience_reach_score": audience_reach_score,
        "angle_score": angle_score,
        "content_score": content_score,
        "total_score": total_score,
        "topic_priority": topic_priority,
        "event_type": event_type,
    }


def main() -> None:
    events = _event_map()
    latest_idx = _latest_index_by_event()

    promoted_rows: list[dict[str, Any]] = []
    not_promoted_rows: list[dict[str, Any]] = []
    candidate_ids = set(latest_idx.keys()) | set(_event_ids_with_fact_pack())
    for eid in sorted(candidate_ids):
        idx = latest_idx.get(eid) or {}
        ev = events.get(eid)
        if not isinstance(ev, dict):
            continue

        original_queue = str(ev.get("cluster_queue") or "")
        if original_queue != "source_research":
            continue

        fact_path = ENRICHED_DIR / f"{eid}_fact_pack.json"
        if not fact_path.exists():
            continue
        try:
            fact_pack = json.loads(fact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(fact_pack, dict):
            continue

        if str(fact_pack.get("upgrade_recommendation") or "") != "queue_review":
            continue
        if str(fact_pack.get("source_risk") or "") == "high":
            continue
        if _missing_required_count(fact_pack) > 1:
            continue

        best_sources = fact_pack.get("best_sources") if isinstance(fact_pack.get("best_sources"), list) else []
        p0, p1 = _count_tiers([x for x in best_sources if isinstance(x, dict)])
        source_risk = str(fact_pack.get("source_risk") or "")
        tier_ok = (p0 >= 1) or (p1 >= 2) or (source_risk == "low")
        if not tier_ok:
            continue

        gate = should_promote_enriched_event(ev, fact_pack)

        row = {
            "event_cluster_id": eid,
            "cluster_title": str(ev.get("cluster_title") or fact_pack.get("core_claim") or ""),
            "original_queue": original_queue,
            "enriched_queue": "enriched_queue_review",
            "event_type": str(gate.get("event_type") or ""),
            "source_risk": source_risk,
            "upgrade_recommendation": str(fact_pack.get("upgrade_recommendation") or ""),
            "best_sources": best_sources,
            "confirmed_facts": fact_pack.get("confirmed_facts") or [],
            "missing_facts": fact_pack.get("missing_facts") or [],
            "angle_candidates": fact_pack.get("angle_candidates") or [],
            "fact_pack_path": str(fact_path),
            "upgrade_reason": str(fact_pack.get("reason") or ""),
            "promotion_score": gate.get("promotion_score"),
            "promotion_reasons": gate.get("promotion_reasons"),
            "demotion_reasons": gate.get("demotion_reasons"),
            "audience_reach_score": gate.get("audience_reach_score"),
            "angle_score": gate.get("angle_score"),
            "content_score": gate.get("content_score"),
            "total_score": gate.get("total_score"),
            "topic_priority": gate.get("topic_priority"),
            "created_at": _utc_now_iso(),
        }

        if bool(gate.get("promote")):
            promoted_rows.append(row)
        else:
            not_promoted_rows.append(
                {
                    "event_cluster_id": eid,
                    "cluster_title": row.get("cluster_title"),
                    "upgrade_recommendation": row.get("upgrade_recommendation"),
                    "event_type": row.get("event_type"),
                    "promotion_score": row.get("promotion_score"),
                    "demotion_reasons": row.get("demotion_reasons"),
                    "why_not_promoted": gate.get("why_not_promoted"),
                    "fact_pack_path": row.get("fact_pack_path"),
                    "created_at": row.get("created_at"),
                }
            )

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in promoted_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lines: list[str] = []
    lines.append("# enriched_queue_review\n")
    lines.append(f"- Items: {len(promoted_rows)}\n")
    for i, r in enumerate(promoted_rows[:50], start=1):
        lines.append("\n---\n")
        lines.append(f"## Candidate {i}\n")
        lines.append(f"- event_cluster_id: {r.get('event_cluster_id')}\n")
        lines.append(f"- cluster_title: {r.get('cluster_title')}\n")
        lines.append(f"- original_queue: {r.get('original_queue')}\n")
        lines.append(f"- enriched_queue: {r.get('enriched_queue')}\n")
        lines.append(f"- event_type: {r.get('event_type')}\n")
        lines.append(f"- promotion_score: {r.get('promotion_score')}\n")
        lines.append(f"- promotion_reasons: {r.get('promotion_reasons')}\n")
        lines.append(f"- audience_reach_score: {r.get('audience_reach_score')}\n")
        lines.append(f"- angle_score: {r.get('angle_score')}\n")
        lines.append(f"- total_score: {r.get('total_score')}\n")
        lines.append(f"- source_risk: {r.get('source_risk')}\n")
        lines.append(f"- upgrade_recommendation: {r.get('upgrade_recommendation')}\n")
        lines.append(f"- upgrade_reason: {r.get('upgrade_reason')}\n")
        lines.append(f"- fact_pack_path: {r.get('fact_pack_path')}\n")
        lines.append("\n### Best Sources\n")
        for s in (r.get("best_sources") or [])[:5]:
            if not isinstance(s, dict):
                continue
            lines.append(
                f"- {s.get('tier')} {s.get('source_name')} score={s.get('source_score')} domain={s.get('domain')} url={s.get('url')}\n"
            )
        lines.append("\n### Confirmed Facts\n")
        for x in (r.get("confirmed_facts") or [])[:6]:
            lines.append(f"- {x}\n")
        lines.append("\n### Missing Facts\n")
        mfs = r.get("missing_facts") or []
        if mfs:
            for x in mfs[:6]:
                lines.append(f"- {x}\n")
        else:
            lines.append("- (empty)\n")
        lines.append("\n### Angle Candidates\n")
        for x in (r.get("angle_candidates") or [])[:6]:
            lines.append(f"- {x}\n")

    OUT_MD.write_text("".join(lines), encoding="utf-8")

    with OUT_NOT_PROMOTED_JSONL.open("w", encoding="utf-8") as f:
        for r in not_promoted_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    npl: list[str] = []
    npl.append("# enriched_not_promoted\n")
    npl.append(f"- Items: {len(not_promoted_rows)}\n")
    for i, r in enumerate(not_promoted_rows[:80], start=1):
        npl.append("\n---\n")
        npl.append(f"## Item {i}\n")
        npl.append(f"- event_cluster_id: {r.get('event_cluster_id')}\n")
        npl.append(f"- cluster_title: {r.get('cluster_title')}\n")
        npl.append(f"- upgrade_recommendation: {r.get('upgrade_recommendation')}\n")
        npl.append(f"- event_type: {r.get('event_type')}\n")
        npl.append(f"- promotion_score: {r.get('promotion_score')}\n")
        npl.append(f"- demotion_reasons: {r.get('demotion_reasons')}\n")
        npl.append(f"- why_not_promoted: {r.get('why_not_promoted')}\n")
        npl.append(f"- fact_pack_path: {r.get('fact_pack_path')}\n")

    OUT_NOT_PROMOTED_MD.write_text("".join(npl), encoding="utf-8")

    print(
        f"[build_enriched_queue] ok promoted={len(promoted_rows)} not_promoted={len(not_promoted_rows)} "
        f"wrote={OUT_MD} and {OUT_JSONL}; audit={OUT_NOT_PROMOTED_MD} and {OUT_NOT_PROMOTED_JSONL}"
    )


if __name__ == "__main__":
    main()

