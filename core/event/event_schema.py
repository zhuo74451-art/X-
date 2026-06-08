from __future__ import annotations

EVENT_STATUS = ("emerging", "hot", "peaking", "cooling", "dead")
FACT_ANCHOR = ("confirmed", "multi_source", "single_source", "rumor_only")
ACTION_TYPES = ("official_post", "editor_take", "reply_or_quote", "monitor_only", "reject")


def clamp_score(value: int | float | str, default: int = 0) -> int:
    try:
        n = int(float(value))
    except Exception:
        n = default
    return max(0, min(100, n))


def normalize_status(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in EVENT_STATUS else "emerging"


def normalize_fact_anchor(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in FACT_ANCHOR else "single_source"
