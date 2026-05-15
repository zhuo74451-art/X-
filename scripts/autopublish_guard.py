from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_rules() -> dict[str, Any]:
    p = _project_root() / "configs" / "autopublish_rules.json"
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        return j if isinstance(j, dict) else {}
    except json.JSONDecodeError:
        return {}


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    t = text or ""
    t_lower = t.lower()
    hits: list[str] = []
    for k in keywords:
        if not k:
            continue
        kk = str(k)
        if kk in t:
            hits.append(k)
            continue
        if any("a" <= ch.lower() <= "z" for ch in kk) and kk.lower() in t_lower:
            hits.append(k)
    return hits


def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"[。！？!?\n\r]+", t)
    return [p.strip() for p in parts if p.strip()]


def _hits_with_negation(text: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    neg_phrases = [
        "不是",
        "不像",
        "不涉及",
        "未涉及",
        "并非",
        "没有",
        "未发现",
        "暂无",
        "暂未",
        "无",
    ]
    sents = _split_sentences(text)
    eff: list[str] = []
    neg: list[str] = []
    for kw in [str(x) for x in keywords if str(x).strip()]:
        has_eff = False
        has_neg = False
        for s in sents:
            if kw not in s and kw.lower() not in s.lower():
                continue
            if any(p in s for p in neg_phrases):
                has_neg = True
            else:
                has_eff = True
        if has_eff:
            eff.append(kw)
        elif has_neg:
            neg.append(kw)
    return eff, neg


def _topic_hits_with_negation(text: str, topics: list[str]) -> tuple[list[str], list[str]]:
    t = text or ""
    topic_keywords: dict[str, list[str]] = {
        "法律/庭审": ["法院", "法官", "起诉", "庭审", "诉讼", "检方", "审判", "指控", "涉嫌", "违法", "调查"],
        "监管处罚": ["监管", "处罚", "罚款", "调查", "执法", "sec", "cftc", "fca", "mas", "sfc", "监管处罚"],
        "黑客/被盗": ["黑客", "被盗", "盗取", "攻击", "漏洞", "hack", "hacked", "exploit", "exploited"],
        "交易所风险": ["交易所风险", "暂停提现", "冻结", "挤兑", "爆雷", "破产", "清算风险"],
        "战争/制裁/地缘冲突": ["战争", "制裁", "冲突", "爆炸", "恐袭", "袭击", "导弹", "空袭", "地缘"],
    }

    hits: list[str] = []
    neg: list[str] = []
    for tp in [str(x) for x in topics if str(x).strip()]:
        kws = topic_keywords.get(tp) or []
        eff_labels, neg_labels = _hits_with_negation(t, [tp])
        if eff_labels:
            hits.append(tp)
        elif neg_labels:
            neg.append(tp)

        eff_kws, neg_kws = _hits_with_negation(t, kws)
        for kw in eff_kws:
            hits.append(f"{tp}:{kw}")
        for kw in neg_kws:
            neg.append(f"{tp}:{kw}")

    def _uniq(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    return _uniq(hits), _uniq(neg)


def _is_secondary_only(event: dict[str, Any]) -> bool:
    sns = event.get("source_names")
    if not isinstance(sns, list) or not sns:
        return True
    clean = [str(x).lower().strip() for x in sns if str(x).strip()]
    if not clean:
        return True
    if all(("tg:" in x) or ("webhook" in x) or ("jin10" in x) for x in clean):
        return True
    return False


def _strip_links(text: str) -> str:
    t = text or ""
    t = re.sub(r"https?://\S+", "", t).strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def _high_risk_hits(text: str, topics: list[str]) -> list[str]:
    t = text or ""
    t_lower = t.lower()
    topic_keywords: dict[str, list[str]] = {
        "法律/庭审": ["法院", "法官", "起诉", "庭审", "诉讼", "检方", "审判", "指控", "涉嫌", "违法", "调查"],
        "监管处罚": ["监管", "处罚", "罚款", "调查", "执法", "sec", "cftc", "fca", "mas", "sfc"],
        "黑客/被盗": ["黑客", "被盗", "盗取", "攻击", "漏洞", "hack", "hacked", "exploit", "exploited"],
        "交易所风险": ["交易所风险", "暂停提现", "冻结", "挤兑", "爆雷", "破产", "清算风险"],
        "战争/制裁/地缘冲突": ["战争", "制裁", "冲突", "爆炸", "恐袭", "袭击", "导弹", "空袭", "地缘"],
    }
    hits: list[str] = []
    for tp in topics:
        label = str(tp).strip()
        if not label:
            continue
        if label in t:
            hits.append(label)
            continue
        kws = topic_keywords.get(label) or []
        for kw in kws:
            if not kw:
                continue
            if kw in t:
                hits.append(f"{label}:{kw}")
                break
            if any("a" <= ch.lower() <= "z" for ch in kw) and kw.lower() in t_lower:
                hits.append(f"{label}:{kw}")
                break
    return hits


def _unverified_language_hits(text: str) -> list[str]:
    keywords = [
        "未经证实",
        "传闻",
        "有传",
        "坊间",
        "消息称",
        "据悉",
        "rumor",
        "unconfirmed",
        "未经确认",
    ]
    return _contains_any(text, keywords)


def _ordinary_market_flow_no_strong_hook(text: str) -> bool:
    t = text or ""
    tl = t.lower()

    etf_terms = ["etf", "现货etf", "现货 etf", "spot etf", "spot-etf"]
    flow_terms = ["净流入", "净流出", "资金流", "流入", "流出", "inflow", "outflow"]
    if not (any(k in tl for k in etf_terms) and any(k in tl for k in flow_terms)):
        return False

    strong_hook_terms = [
        "历史最大",
        "历史新高",
        "创纪录",
        "创记录",
        "上市以来最大",
        "纪录",
        "记录",
        "近3个月",
        "近 3 个月",
        "3个月",
        "近6个月",
        "近 6 个月",
        "6个月",
        "年内最大",
        "年内新高",
        "连续",
        "异常",
        "背离",
        "贝莱德",
        "blackrock",
        "ibit",
        "富达",
        "fidelity",
        "fbtc",
        "机构赎回",
        "赎回",
        "配置变化",
        "流动性冲击",
        "风险资产",
        "宏观事件",
        "价格大跌",
        "价格大涨",
        "大跌",
        "大涨",
        "暴跌",
        "暴涨",
        "btc大跌",
        "btc大涨",
        "eth大跌",
        "eth大涨",
    ]
    if any(k.lower() in tl for k in strong_hook_terms):
        return False

    return True


def _read_jsonl_log(path: Path) -> list[dict[str, Any]]:
    p = path
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
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


def _read_published_log() -> list[dict[str, Any]]:
    p = _project_root() / "out" / "publish_logs" / "published_posts.jsonl"
    return _read_jsonl_log(p)


def _read_dryrun_log() -> list[dict[str, Any]]:
    p = _project_root() / "out" / "publish_logs" / "dryrun_posts.jsonl"
    return _read_jsonl_log(p)


def _recent_posts(posts: list[dict[str, Any]], since: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in posts:
        ts = str(p.get("created_at") or "").strip()
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if dt >= since:
            out.append(p)
    return out


def evaluate_autopublish(
    *,
    generated_post: dict[str, Any],
    event_cluster: dict[str, Any],
    published_log: list[dict[str, Any]] | None = None,
    dryrun_log: list[dict[str, Any]] | None = None,
    include_dry_run_history: bool = False,
) -> dict[str, Any]:
    rules = _load_rules()
    block_reasons: list[str] = []

    queue = str(event_cluster.get("cluster_queue") or "")
    allowed_queues = rules.get("allowed_queues") if isinstance(rules.get("allowed_queues"), list) else []
    if allowed_queues and queue not in [str(x) for x in allowed_queues]:
        block_reasons.append("queue_not_allowed")

    risk_level = str(event_cluster.get("risk_level") or "low").strip() or "low"
    if risk_level != "low":
        block_reasons.append(f"risk_level_not_low:{risk_level}")

    require_anchor = bool(rules.get("require_source_anchor", True))
    best_url = str(event_cluster.get("best_source_url") or "").strip()
    if require_anchor:
        if not best_url:
            block_reasons.append("missing_best_source_url")
        if _is_secondary_only(event_cluster):
            block_reasons.append("secondary_only_source")

    public_text = "\n".join(
        [
            str(event_cluster.get("cluster_title") or ""),
            str(event_cluster.get("public_summary") or ""),
            str(generated_post.get("main_post") or ""),
            str(generated_post.get("first_comment") or ""),
        ]
    ).strip()

    internal_text = "\n".join(
        [
            str(generated_post.get("editor_risk_note") or ""),
            "\n".join([str(x) for x in (generated_post.get("weak_points") or []) if str(x).strip()])
            if isinstance(generated_post.get("weak_points"), list)
            else "",
            str(event_cluster.get("rule_reason") or ""),
            "\n".join([str(x) for x in (event_cluster.get("missing_facts") or []) if str(x).strip()])
            if isinstance(event_cluster.get("missing_facts"), list)
            else "",
            str(event_cluster.get("raw_summary") or ""),
        ]
    ).strip()

    blocked_keywords = rules.get("blocked_keywords") if isinstance(rules.get("blocked_keywords"), list) else []
    blocked_hits, negated_blocked_hits = _hits_with_negation(public_text, [str(x) for x in blocked_keywords])
    if blocked_hits:
        block_reasons.append("blocked_keywords:" + ",".join(blocked_hits[:8]))

    investment_advice_keywords = (
        rules.get("investment_advice_keywords") if isinstance(rules.get("investment_advice_keywords"), list) else []
    )
    invest_hits = _contains_any(public_text, [str(x) for x in investment_advice_keywords])
    if invest_hits:
        block_reasons.append("investment_advice_keywords:" + ",".join(invest_hits[:8]))

    high_risk_topics = rules.get("high_risk_topics") if isinstance(rules.get("high_risk_topics"), list) else []
    risk_hits, negated_risk_hits = _topic_hits_with_negation(public_text, [str(x) for x in high_risk_topics])
    if risk_hits:
        block_reasons.append("high_risk_topics:" + ",".join(risk_hits[:6]))

    unverified_hits = _unverified_language_hits(public_text)
    if unverified_hits:
        block_reasons.append("unverified_language:" + ",".join(unverified_hits[:8]))

    if _ordinary_market_flow_no_strong_hook(public_text):
        block_reasons.append("ordinary_market_flow_no_strong_hook")

    main_post_clean = _strip_links(str(generated_post.get("main_post") or "")).strip()
    first_comment_clean = _strip_links(str(generated_post.get("first_comment") or "")).strip()
    reply_allowed = True
    reply_skip_reason = ""
    adjustment_actions: list[str] = []
    if not main_post_clean:
        block_reasons.append("missing_main_post")
    if len(main_post_clean) > 280:
        block_reasons.append("main_post_too_long")

    if first_comment_clean and len(first_comment_clean) > 280:
        reply_allowed = False
        reply_skip_reason = f"first_comment_too_long:{len(first_comment_clean)}"
        adjustment_actions.append("skip_first_comment")

    now = _utcnow()
    if published_log is None:
        published_log = _read_published_log()
    history: list[dict[str, Any]] = list(published_log)
    if include_dry_run_history:
        if dryrun_log is None:
            dryrun_log = _read_dryrun_log()
        history.extend(dryrun_log)

    recent = _recent_posts(history, now - timedelta(hours=24))
    event_id = str(event_cluster.get("event_cluster_id") or "").strip()
    status_to_count = {"published"} if not include_dry_run_history else {"published", "would_publish"}
    if event_id and any((str(x.get("event_cluster_id") or "").strip() == event_id) and (x.get("status") in status_to_count) for x in recent):
        block_reasons.append("already_published_in_24h")

    max_posts = int(rules.get("max_posts_per_day") or 0) if str(rules.get("max_posts_per_day") or "").strip() else 0
    if max_posts > 0 and len([x for x in recent if x.get("status") in status_to_count]) >= max_posts:
        block_reasons.append("max_posts_per_day_reached")

    max_whale = int(rules.get("max_whale_digest_per_day") or 0) if str(rules.get("max_whale_digest_per_day") or "").strip() else 0
    if max_whale > 0 and queue == "whale_digest":
        whale_count = len([x for x in recent if x.get("queue") == "whale_digest" and x.get("status") in status_to_count])
        if whale_count >= max_whale:
            block_reasons.append("max_whale_digest_per_day_reached")

    min_minutes = int(rules.get("min_minutes_between_posts") or 0) if str(rules.get("min_minutes_between_posts") or "").strip() else 0
    if min_minutes > 0 and recent:
        latest = None
        for p in recent:
            if p.get("status") not in status_to_count:
                continue
            ts = str(p.get("created_at") or "").strip()
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if latest is None or dt > latest:
                latest = dt
        if latest is not None and now - latest < timedelta(minutes=min_minutes):
            block_reasons.append("min_interval_blocked")

    autopublish_score = 100
    if blocked_hits:
        autopublish_score -= 60
    if require_anchor and ("missing_best_source_url" in block_reasons or "secondary_only_source" in block_reasons):
        autopublish_score -= 40
    if invest_hits:
        autopublish_score -= 60
    if risk_hits:
        autopublish_score -= 60
    if unverified_hits:
        autopublish_score -= 40
    if "ordinary_market_flow_no_strong_hook" in block_reasons:
        autopublish_score -= 50
    if len(main_post_clean) > 280:
        autopublish_score -= 40
    if queue == "whale_digest":
        autopublish_score -= 10

    min_score = int(rules.get("min_autopublish_score") or 85) if str(rules.get("min_autopublish_score") or "").strip() else 85
    if autopublish_score < min_score:
        block_reasons.append("autopublish_score_too_low")

    allowed = (not block_reasons) and (risk_level == "low") and (autopublish_score >= min_score)

    internal_warning_hits = {
        "blocked_keywords": _contains_any(internal_text, [str(x) for x in blocked_keywords])[:8],
        "high_risk_topics": _high_risk_hits(internal_text, [str(x) for x in high_risk_topics])[:6],
    }

    guard_debug = {
        "public_text_keyword_hits": {
            "blocked_keywords": blocked_hits[:8],
            "investment_advice_keywords": invest_hits[:8],
            "high_risk_topics": risk_hits[:6],
            "unverified_language": unverified_hits[:8],
            "ordinary_market_flow_no_strong_hook": bool("ordinary_market_flow_no_strong_hook" in block_reasons),
        },
        "internal_warning_hits": internal_warning_hits,
        "negated_keyword_hits": {
            "blocked_keywords": negated_blocked_hits[:8],
            "high_risk_topics": negated_risk_hits[:8],
        },
        "scanned_public_text_preview": public_text[:400],
        "scanned_internal_text_preview": internal_text[:400],
    }

    return {
        "allowed_to_autopublish": bool(allowed),
        "reply_allowed": bool(reply_allowed),
        "reply_skip_reason": str(reply_skip_reason),
        "adjustment_actions": adjustment_actions,
        "autopublish_score": int(max(0, min(100, autopublish_score))),
        "risk_level": risk_level,
        "block_reasons": block_reasons,
        "guard_debug": guard_debug,
    }

