from __future__ import annotations

from typing import Any

from core.event.lifecycle import recommended_action


def account_for_action(action: str) -> str:
    if action == "official_post":
        return "coinmeta_official"
    if action in {"editor_take", "reply_or_quote"}:
        return "editor_persona" if action == "editor_take" else "reply_quote"
    return "none"


def requires_human(event: dict[str, Any], action: str) -> bool:
    flags = set(event.get("risk_flags") or [])
    if event.get("risk_level") == "high":
        return True
    if flags.intersection({"security", "exchange_risk", "regulation"}):
        return True
    if event.get("fact_anchor") == "rumor_only":
        return True
    return action in {"editor_take"}


def decision_reason(event: dict[str, Any], action: str, actions: list[dict[str, Any]]) -> str:
    if action == "reject":
        if any(a.get("action_type") == "official_post" for a in actions):
            return "已对该事件做过官号主帖，当前无明显新增热度，避免重复发。"
        return "事件不适合继续运营或已经错过窗口。"
    if action == "official_post":
        return "事件处于 hot 阶段，具备多源事实锚点，适合官号主帖。"
    if action == "reply_or_quote":
        return "事件已进入发酵后段，适合用引用或评论承接，不必再正面主帖。"
    if action == "editor_take":
        return "事件存在观点空间，但不适合官号直接定性。"
    return "事件仍需观察，暂不进入发布动作。"


def user_hook(event: dict[str, Any]) -> str:
    flags = set(event.get("risk_flags") or [])
    title = str(event.get("title") or "")
    if "stablecoin" in flags:
        return "稳定币从交易工具进入真实使用场景，用户会关心它到底怎么用。"
    if "onchain" in flags:
        return "链上异动的重点不是金额本身，而是它是否变成市场行为信号。"
    if "regulation" in flags:
        return "监管事件影响的是交易入口和合规边界。"
    return title[:80]


def expected_metric(event: dict[str, Any], action: str) -> dict[str, str]:
    flags = set(event.get("risk_flags") or [])
    if action == "official_post" and "stablecoin" in flags:
        return {"primary": "bookmark_or_reply", "reason": "现实应用类内容更容易被收藏和讨论"}
    if action == "reply_or_quote":
        return {"primary": "reply", "reason": "引用/评论承接应优先看讨论量"}
    if "onchain" in flags:
        return {"primary": "bookmark", "reason": "链上观察清单更偏收藏"}
    return {"primary": "impression", "reason": "冷启动阶段先看展示和互动基线"}


def build_decision(event: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    action = recommended_action(event, actions)
    return {
        "event_id": event.get("event_id"),
        "title": event.get("title"),
        "decision": action,
        "account": account_for_action(action),
        "confidence": confidence_for(event, action),
        "fact_anchor": event.get("fact_anchor"),
        "status": event.get("status"),
        "account_fit_reason": decision_reason(event, action, actions),
        "user_hook": user_hook(event),
        "risk_level": event.get("risk_level"),
        "risk_flags": event.get("risk_flags") or [],
        "requires_human": requires_human(event, action),
        "publish_window": publish_window_for(event, action),
        "expected_metric": expected_metric(event, action),
        "dedup_against": [a.get("action_type") for a in actions],
    }


def confidence_for(event: dict[str, Any], action: str) -> float:
    base = 0.35
    if event.get("fact_anchor") in {"confirmed", "multi_source"}:
        base += 0.25
    if event.get("status") == "hot":
        base += 0.2
    if action == "official_post":
        base += 0.1
    if event.get("risk_level") == "high":
        base -= 0.25
    return round(max(0.0, min(0.95, base)), 2)


def publish_window_for(event: dict[str, Any], action: str) -> str:
    if action == "official_post":
        return "20:00-22:00 local, unless event velocity spikes earlier"
    if action == "reply_or_quote":
        return "within 30-90 minutes after the source post becomes active"
    return "not scheduled"
