from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from search_query_builder import build_search_queries
from source_ranker import rank_sources
from web_search_adapter import run_multi_search
from event_type_classifier import classify_event_type


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _domain(url: str) -> str:
    try:
        p = urlparse(url)
        h = (p.netloc or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _seed_urls(event_cluster: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    if event_cluster.get("best_source_url"):
        urls.append(str(event_cluster.get("best_source_url") or ""))
    for u in (event_cluster.get("source_urls") or []):
        if u and str(u).strip():
            urls.append(str(u).strip())
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _split_claims(text: str) -> tuple[list[str], list[str]]:
    t = (text or "").strip()
    if not t:
        return [], []

    sentences = [s.strip() for s in re.split(r"[。！？!?\n\r]+", t) if s.strip()]
    confirmed: list[str] = []
    unconfirmed: list[str] = []

    uncertain_markers = ["据", "传", "可能", "声称", "市场消息", "消息人士", "尚未", "未证实", "预计", "或将"]
    for s in sentences:
        if any(m in s for m in uncertain_markers):
            unconfirmed.append(s)
        else:
            confirmed.append(s)

    return confirmed[:6], unconfirmed[:6]


def _build_timeline(event_cluster: dict[str, Any]) -> list[dict[str, str]]:
    urls = [str(u) for u in (event_cluster.get("source_urls") or []) if str(u).strip()]
    best = str(event_cluster.get("best_source_url") or "").strip()
    out: list[dict[str, str]] = []
    if best:
        out.append({"t": "", "event": "当前最佳来源", "source": best})
    for u in urls[:5]:
        if best and u == best:
            continue
        out.append({"t": "", "event": "相关线索", "source": u})
    return out


def _load_rules(rules_path: Path) -> dict[str, Any]:
    if not rules_path.exists():
        return {}
    return json.loads(rules_path.read_text(encoding="utf-8"))


def _has_extreme_or_hook(text: str) -> bool:
    t = (text or "").lower()
    hooks = ["创纪录", "历史最大", "年内最大", "近3个月", "近 3 个月", "近6个月", "近 6 个月", "异常", "连续", "背离"]
    return any(h.lower() in t for h in hooks)


def _has_angle_hook(event_type: str, title: str, raw_summary: str) -> bool:
    t = (title or "") + "\n" + (raw_summary or "")
    if event_type in ("stablecoin_policy", "crypto_regulation"):
        return any(x in t for x in ["上限", "限制", "放宽", "降低要求", "规则", "框架", "处罚", "罚款", "执法", "法案"])
    if event_type == "ai_crypto_story":
        return any(x in t for x in ["找回", "恢复", "助记词", "钱包"]) and any(ch.isdigit() for ch in t)
    if event_type == "whale_onchain":
        return any(x in t for x in ["巨鲸", "清算", "杠杆", "多单", "空单", "转入", "转出"])
    if event_type == "security_incident":
        return any(x in t for x in ["黑客", "被盗", "漏洞", "攻击", "exploit"])
    if event_type == "macro_market":
        if "etf" in t.lower() and not _has_extreme_or_hook(t):
            return False
        return any(x in t for x in ["大涨", "大跌", "流动性", "风险资产", "收益率", "通胀", "利率"])
    return bool(title.strip())


def _count_tiers(best_sources: list[dict[str, Any]]) -> tuple[bool, int]:
    tiers = [str(s.get("tier") or "unknown") for s in best_sources]
    has_p0 = any(t == "P0" for t in tiers)
    p1_count = sum(1 for t in tiers if t == "P1")
    return has_p0, p1_count


def _required_facts_status(
    event_cluster: dict[str, Any],
    event_type: str,
    rules: dict[str, Any],
    best_sources: list[dict[str, Any]],
    raw_summary: str,
    base_missing: list[str],
) -> dict[str, Any]:
    type_cfg = {}
    et = rules.get("event_types")
    if isinstance(et, dict):
        type_cfg = et.get(event_type) or et.get("unknown") or {}

    required = [str(x) for x in (type_cfg.get("required_facts") or []) if str(x).strip()]
    not_required = [str(x) for x in (type_cfg.get("not_required") or []) if str(x).strip()]

    satisfied: list[str] = []
    missing_required: list[str] = []

    any_url = any(str(s.get("url") or "").strip() for s in best_sources) or bool(str(event_cluster.get("best_source_url") or "").strip())
    has_p0, p1_count = _count_tiers(best_sources)
    title = str(event_cluster.get("cluster_title") or "")

    for rf in required:
        ok = False
        if rf in ("原始报道链接", "官方发布链接", "原始通报/公告链接", "交易所官方公告或权威报道"):
            ok = any_url
        elif rf in ("官方文件或央行原话", "官方文件/执法公告"):
            ok = has_p0 or ("英格兰银行" in title and "表示" in raw_summary)
        elif rf in ("具体规则变化", "具体条款/处罚点"):
            ok = any(x in raw_summary for x in ["上限", "限制", "要求", "至少", "降低", "放宽", "条款", "罚款", "处罚"]) or any(
                ch.isdigit() for ch in raw_summary
            )
        elif rf.startswith("影响对象"):
            ok = any(x in raw_summary for x in ["发行方", "交易所", "用户", "支付", "机构", "银行"])
        elif rf == "数据来源":
            ok = any_url or any(x in raw_summary for x in ["Reuters", "Bloomberg", "CoinDesk", "Cointelegraph", "数据"])
        elif rf == "时间范围":
            ok = any(x in raw_summary for x in ["过去", "今日", "单日", "小时", "周", "月", "年"])
        elif rf == "是否历史极值":
            ok = _has_extreme_or_hook(raw_summary)
        elif rf == "与价格/流动性/风险资产的关系":
            ok = any(x in raw_summary for x in ["价格", "大涨", "大跌", "流动性", "风险资产", "收益率"])
        elif rf in ("地址或看板链接",):
            ok = any(x in str(event_cluster.get("dashboard_url") or "") for x in ["http", "https"]) or any(
                x in str(event_cluster.get("source_url") or "") for x in ["http", "https"]
            )
        elif rf in ("资产", "动作", "金额", "时间"):
            ok = bool(event_cluster.get("asset")) or any(x in raw_summary for x in ["BTC", "ETH", "USDC", "USDT"]) if rf == "资产" else False
            if rf == "动作":
                ok = any(x in raw_summary for x in ["转入", "转出", "买入", "卖出", "清算", "开仓", "平仓"])
            if rf == "金额":
                ok = any(ch.isdigit() for ch in raw_summary) or bool(event_cluster.get("amount_usd"))
            if rf == "时间":
                ok = any(x in raw_summary for x in ["小时", "今日", "昨天", "日期", "UTC", "北京时间"])
        elif rf == "是否连续行为":
            ok = any(x in raw_summary for x in ["连续", "多次", "过去", "近"]) or False
        elif rf == "当事人自述或采访":
            ok = any(x in raw_summary for x in ["自述", "表示", "称", "采访", "讲述"])
        elif rf == "可验证数字":
            ok = any(ch.isdigit() for ch in raw_summary)
        elif rf == "社区争议点":
            ok = any(x in raw_summary for x in ["争议", "质疑", "社区", "认为", "夸大"])
        elif rf == "受影响范围与损失金额":
            ok = any(ch.isdigit() for ch in raw_summary) and any(x in raw_summary for x in ["美元", "US$", "损失", "被盗", "影响"])
        elif rf == "是否已修复/处置":
            ok = any(x in raw_summary for x in ["已修复", "修复", "补丁", "暂停", "冻结", "处置", "调查中"])
        elif rf == "用户影响与风险提示":
            ok = any(x in raw_summary for x in ["用户", "提现", "资金安全", "风险", "影响"])
        elif rf == "受影响对象与时间表":
            ok = any(x in raw_summary for x in ["生效", "时间表", "将于", "在本周", "下月", "年内", "适用"])
        elif rf == "关键变更点":
            ok = any(x in raw_summary for x in ["升级", "变更", "改动", "迁移", "上线"])
        elif rf == "影响对象与上线节奏":
            ok = any(x in raw_summary for x in ["上线", "测试", "主网", "灰度", "分批"])
        else:
            ok = False

        if ok:
            satisfied.append(rf)
        else:
            missing_required.append(rf)

    not_required_removed: list[str] = []
    filtered_base_missing: list[str] = []
    for m in base_missing:
        if any(nr in m for nr in not_required):
            not_required_removed.append(m)
            continue
        filtered_base_missing.append(m)

    missing_final: list[str] = []
    for x in filtered_base_missing + missing_required:
        xx = str(x).strip()
        if not xx:
            continue
        if xx not in missing_final:
            missing_final.append(xx)

    return {
        "satisfied": satisfied,
        "missing": missing_required,
        "not_required_removed": not_required_removed,
        "missing_facts_final": missing_final,
    }


def _upgrade_recommendation_v2(
    cluster_queue: str,
    event_type: str,
    source_risk: str,
    best_sources: list[dict[str, Any]],
    required_status: dict[str, Any],
    title: str,
    raw_summary: str,
    rules: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    if cluster_queue != "source_research":
        return "keep_source_research", "仅对 source_research 队列做富集升级判断", {"decision": "keep_source_research"}

    has_p0, p1_count = _count_tiers(best_sources)
    missing_required = required_status.get("missing") or []
    miss_n = len(missing_required)
    upgrade_cfg = rules.get("upgrade") if isinstance(rules.get("upgrade"), dict) else {}
    max_miss = int(upgrade_cfg.get("max_missing_required_facts_for_queue_review") or 1)

    angle_ok = _has_angle_hook(event_type, title, raw_summary)
    tier_ok = bool(has_p0 or (p1_count >= 2))
    source_ok = source_risk in ("low", "medium")
    miss_ok = miss_n <= max_miss

    gate = {
        "source_risk_ok": bool(source_ok),
        "tier_ok": bool(tier_ok),
        "missing_required_ok": bool(miss_ok),
        "angle_ok": bool(angle_ok),
        "missing_required_count": int(miss_n),
        "max_missing_required": int(max_miss),
        "has_p0": bool(has_p0),
        "p1_count": int(p1_count),
    }

    if event_type == "macro_market" and ("etf" in (title or "").lower()) and not _has_extreme_or_hook(title + "\n" + raw_summary):
        return "monitor", "宏观/ETF 资金流属常规信息，缺少异常钩子，建议监控而非升级", gate

    if source_risk == "high":
        return "monitor", "来源线索不足（source_risk=high），建议监控等待更硬一手来源", gate

    if source_ok and tier_ok and miss_ok and angle_ok:
        return "queue_review", "满足升级门：来源层级/风险可控 + required_facts 缺口少 + 有传播角度", gate

    if (not tier_ok) or (source_risk in ("high",)):
        return "keep_source_research", "来源层级不足以升级，继续补一手来源与关键事实", gate

    if not miss_ok:
        return "keep_source_research", "required_facts 缺口仍明显，继续 source_research 补齐关键缺口", gate

    if not angle_ok:
        return "monitor", "事实线索较硬但传播角度不足，建议先 monitor 或等待更强连接点", gate

    return "keep_source_research", "继续 source_research（需要更硬的一手来源/更清晰的用户影响）", gate


def build_fact_pack(
    event_cluster: dict[str, Any],
    config_dir: Path,
    output_dir: Path,
    search_provider: str = "mock",
    max_results_per_query: int = 5,
    no_web_search: bool = False,
) -> dict[str, Any]:
    event_id = str(event_cluster.get("event_cluster_id") or "")
    cluster_title = str(event_cluster.get("cluster_title") or "").strip()
    raw_summary = str(event_cluster.get("raw_summary") or "").strip()
    base_missing = [str(x) for x in (event_cluster.get("missing_facts") or []) if str(x).strip()]

    rules_path = config_dir / "enrichment_rules.json"
    registry_path = config_dir / "source_registry.json"
    rules = _load_rules(rules_path)

    query_pack = build_search_queries(event_cluster, max_queries=5)
    queries = query_pack.get("queries") or []

    provider = (search_provider or "mock").strip().lower()
    if no_web_search:
        provider = "mock"
    search_bundle = run_multi_search(
        queries=queries,
        provider=provider,
        max_results_per_query=max_results_per_query,
        seed_urls=_seed_urls(event_cluster),
    )
    search_packs = search_bundle.get("query_packs") or []
    ranked = rank_sources(
        search_results=search_packs,
        source_names=[str(x) for x in (event_cluster.get("source_names") or [])],
        registry_path=registry_path,
    )

    confirmed_facts, unconfirmed_claims = _split_claims(raw_summary)

    snippet_claims: list[str] = []
    timeline: list[dict[str, str]] = []
    for it in ranked.get("best_sources") or []:
        sn = str(it.get("snippet") or "").strip()
        if sn:
            snippet_claims.append(f"(snippet) {sn}")
        t = str(it.get("published_at") or "").strip()
        if it.get("url"):
            timeline.append({"t": t, "event": "外部搜索线索", "source": str(it.get("url") or "")})
    if not timeline:
        timeline = _build_timeline(event_cluster)

    best_sources = ranked.get("best_sources") or []
    source_risk = str(ranked.get("source_risk") or "high")
    source_risk_reason = str(ranked.get("source_risk_reason") or "")

    et = classify_event_type(event_cluster)
    event_type = str(et.get("event_type") or "unknown")
    et_conf = int(et.get("confidence") or 0)
    et_reason = str(et.get("reason") or "")

    req_status = _required_facts_status(
        event_cluster=event_cluster,
        event_type=event_type,
        rules=rules,
        best_sources=best_sources,
        raw_summary=raw_summary,
        base_missing=base_missing,
    )
    missing = req_status.get("missing_facts_final") or []

    upgrade_rec, reason, upgrade_gate = _upgrade_recommendation_v2(
        cluster_queue=str(event_cluster.get("cluster_queue") or ""),
        event_type=event_type,
        source_risk=source_risk,
        best_sources=best_sources,
        required_status=req_status,
        title=cluster_title,
        raw_summary=raw_summary,
        rules=rules,
    )

    angle_candidates: list[str] = []
    if cluster_title:
        angle_candidates.append(f"一眼看懂：{cluster_title} 到底意味着什么？")
    if req_status.get("missing"):
        angle_candidates.append("补齐关键缺口后再写：优先补官方原文/关键数字/时间点，再做传播角度")

    pack = {
        "event_cluster_id": event_id,
        "generated_at": _utc_now_iso(),
        "core_claim": cluster_title or (raw_summary[:60] if raw_summary else ""),
        "event_type": event_type,
        "event_type_confidence": et_conf,
        "event_type_reason": et_reason,
        "required_facts_status": {
            "satisfied": req_status.get("satisfied") or [],
            "missing": req_status.get("missing") or [],
            "not_required_removed": req_status.get("not_required_removed") or [],
        },
        "upgrade_gate": upgrade_gate,
        "search_queries": queries,
        "search_provider": provider,
        "search_results": ranked.get("ranked_results") or [],
        "best_sources": best_sources,
        "confirmed_facts": confirmed_facts,
        "unconfirmed_claims": (unconfirmed_claims + snippet_claims)[:12],
        "missing_facts": missing,
        "timeline": timeline,
        "related_context": [],
        "angle_candidates": angle_candidates[:6],
        "image_candidates": [],
        "source_risk": source_risk,
        "source_risk_reason": source_risk_reason,
        "upgrade_recommendation": upgrade_rec,
        "reason": reason,
        "snippet_based": True,
        "fulltext_fetched": False,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{event_id}_fact_pack.json"
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")

    return pack


def render_fact_pack_md(event_cluster: dict[str, Any], fact_pack: dict[str, Any]) -> str:
    title = str(event_cluster.get("cluster_title") or "").strip()
    event_id = str(event_cluster.get("event_cluster_id") or "")
    queue = str(event_cluster.get("cluster_queue") or "")
    source_names = ", ".join([str(x) for x in (event_cluster.get("source_names") or [])])

    lines: list[str] = []
    lines.append(f"# Fact Pack｜{event_id}\n")
    lines.append(f"- title: {title}\n")
    lines.append(f"- original_queue: {queue}\n")
    lines.append(f"- source_names: {source_names}\n")
    lines.append(f"- source_risk: {fact_pack.get('source_risk')}\n")
    if fact_pack.get("source_risk_reason"):
        lines.append(f"- source_risk_reason: {fact_pack.get('source_risk_reason')}\n")
    lines.append(f"- upgrade_recommendation: {fact_pack.get('upgrade_recommendation')}\n")
    lines.append(f"- reason: {fact_pack.get('reason')}\n")
    lines.append(f"- snippet_based: {bool(fact_pack.get('snippet_based'))}\n")
    lines.append(f"- fulltext_fetched: {bool(fact_pack.get('fulltext_fetched'))}\n")

    lines.append("\n## Event Type\n")
    lines.append(f"- event_type: {fact_pack.get('event_type')}\n")
    lines.append(f"- confidence: {fact_pack.get('event_type_confidence')}\n")
    lines.append(f"- reason: {fact_pack.get('event_type_reason')}\n")

    lines.append("\n## Required Facts Status\n")
    rfs = fact_pack.get("required_facts_status") or {}
    lines.append(f"- satisfied: {rfs.get('satisfied')}\n")
    lines.append(f"- missing: {rfs.get('missing')}\n")
    lines.append(f"- not_required_removed: {rfs.get('not_required_removed')}\n")

    lines.append("\n## Core Claim\n")
    lines.append(str(fact_pack.get("core_claim") or "") + "\n")

    lines.append("\n## Confirmed Facts\n")
    cfs = fact_pack.get("confirmed_facts") or []
    if cfs:
        for x in cfs:
            lines.append(f"- {x}\n")
    else:
        lines.append("- (empty)\n")

    lines.append("\n## Unconfirmed Claims\n")
    ucs = fact_pack.get("unconfirmed_claims") or []
    if ucs:
        for x in ucs:
            lines.append(f"- {x}\n")
    else:
        lines.append("- (empty)\n")

    lines.append("\n## Missing Facts\n")
    mfs = fact_pack.get("missing_facts") or []
    if mfs:
        for x in mfs:
            lines.append(f"- {x}\n")
    else:
        lines.append("- (empty)\n")

    lines.append("\n## Best Sources (Ranked)\n")
    bss = fact_pack.get("best_sources") or []
    if bss:
        for s in bss:
            lines.append(
                f"- {s.get('tier')} {s.get('source_name')} score={s.get('source_score')} domain={s.get('domain')} url={s.get('url')}\n"
            )
    else:
        lines.append("- (empty)\n")

    lines.append("\n## Search Queries\n")
    sqs = fact_pack.get("search_queries") or []
    for q in sqs:
        lines.append(f"- {q.get('type')}: {q.get('query')}\n")

    lines.append("\n## Search Results\n")
    srs = fact_pack.get("search_results") or []
    if srs:
        for r in srs[:25]:
            lines.append(f"- title: {r.get('title')}\n")
            lines.append(f"  - domain: {r.get('domain')}\n")
            lines.append(f"  - tier: {r.get('tier')}\n")
            lines.append(f"  - score: {r.get('source_score')}\n")
            lines.append(f"  - url: {r.get('url')}\n")
            lines.append(f"  - snippet: {str(r.get('snippet') or '')[:260]}\n")
    else:
        lines.append("- (empty)\n")

    lines.append("\n## Source Risk\n")
    lines.append(f"- source_risk: {fact_pack.get('source_risk')}\n")
    if fact_pack.get("source_risk_reason"):
        lines.append(f"- reason: {fact_pack.get('source_risk_reason')}\n")

    lines.append("\n## Upgrade Recommendation\n")
    lines.append(f"- upgrade_recommendation: {fact_pack.get('upgrade_recommendation')}\n")
    lines.append(f"- reason: {fact_pack.get('reason')}\n")

    lines.append("\n## Upgrade Gate\n")
    ug = fact_pack.get("upgrade_gate") or {}
    lines.append(f"- gate: {ug}\n")

    lines.append("\n## Timeline (MVP)\n")
    tl = fact_pack.get("timeline") or []
    if tl:
        for it in tl:
            lines.append(f"- {it.get('t') or ''} {it.get('event')}: {it.get('source')}\n")
    else:
        lines.append("- (empty)\n")

    lines.append("\n## Angle Candidates\n")
    acs = fact_pack.get("angle_candidates") or []
    if acs:
        for a in acs:
            lines.append(f"- {a}\n")
    else:
        lines.append("- (empty)\n")

    return "".join(lines)

