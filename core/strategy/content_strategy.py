from __future__ import annotations

import hashlib
from typing import Any


def package_id(event_id: str, decision: str) -> str:
    seed = f"{event_id}:{decision}"
    return "pkg_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]


def hook_type_for(decision: dict[str, Any]) -> str:
    flags = set(decision.get("risk_flags") or [])
    if "stablecoin" in flags:
        return "real_use"
    if "onchain" in flags:
        return "data_watch"
    if decision.get("decision") == "reply_or_quote":
        return "angle_reply"
    return "context_explainer"


def template_id_for(decision: dict[str, Any]) -> str:
    action = decision.get("decision")
    hook = hook_type_for(decision)
    if action == "official_post":
        return f"tmpl_official_{hook}_v1"
    if action == "reply_or_quote":
        return f"tmpl_reply_{hook}_v1"
    if action == "editor_take":
        return f"tmpl_editor_{hook}_v1"
    return "tmpl_monitor_note_v1"


def main_post_text(decision: dict[str, Any]) -> str:
    title = str(decision.get("title") or "")
    hook = str(decision.get("user_hook") or title)
    action = decision.get("decision")
    if action == "official_post":
        return f"{hook}\n\n这条事件真正值得看的，不是标题本身，而是它对用户使用路径、资金行为或市场结构的影响。\n\n后续重点看：事实是否继续被多源确认、资金/用户行为是否跟进。"
    if action == "reply_or_quote":
        return f"补一个角度：{hook}\n\n现在更适合做引用或评论承接，不必重复发一条完整主帖。"
    if action == "editor_take":
        return f"我更关注的是：{hook}\n\n这个角度有讨论价值，但不适合官号直接定性。"
    return ""


def first_comment_text(decision: dict[str, Any]) -> str:
    metric = decision.get("expected_metric") or {}
    primary = metric.get("primary") if isinstance(metric, dict) else ""
    if decision.get("decision") == "official_post":
        return f"首评观察点：这条内容目标指标是 {primary or 'impression'}。如果后续出现新事实，再补一条跟进。"
    if decision.get("decision") == "reply_or_quote":
        return "评论区可以追问：这是短期噪音，还是事件发酵后的真实行为变化？"
    return ""


def build_content_package(event: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    action = str(decision.get("decision") or "monitor_only")
    tpl = template_id_for(decision)
    return {
        "content_package_id": package_id(str(event.get("event_id") or ""), action),
        "event_id": event.get("event_id"),
        "decision": action,
        "account": decision.get("account"),
        "main_post": {"text": main_post_text(decision), "hook_type": hook_type_for(decision)},
        "first_comment": {"text": first_comment_text(decision), "role": "fact_anchor_or_discussion"},
        "quote_text": main_post_text(decision) if action == "reply_or_quote" else "",
        "thread_questions": ["这个事件后续最该看哪个确认信号？"],
        "cta": "欢迎补充一手来源或反例。" if action in {"official_post", "reply_or_quote"} else "",
        "style_template_used": tpl,
        "char_count": len(main_post_text(decision)),
        "risk_boundary": risk_boundary_for(decision),
    }


def risk_boundary_for(decision: dict[str, Any]) -> str:
    if decision.get("requires_human"):
        return "requires_human=true: only write confirmed facts; no auto publish."
    if decision.get("fact_anchor") in {"single_source", "rumor_only"}:
        return "single source: use cautious wording and avoid official assertion."
    return "no price prediction; no causal overclaim; keep source boundary clear."
