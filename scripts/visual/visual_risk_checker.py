from __future__ import annotations

from typing import Any


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


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords if k)


def evaluate_visual_usage_risk(visual_brief: dict[str, Any]) -> tuple[str, list[str]]:
    mode = str(visual_brief.get("visual_mode") or "").strip()
    event_type = str(visual_brief.get("event_type") or "").strip()
    title = str(visual_brief.get("cluster_title") or "").strip()
    prompt = str(visual_brief.get("visual_prompt") or "").strip()
    recommended = str(visual_brief.get("recommended_visual") or "").strip()

    candidates = visual_brief.get("image_candidates")
    if not isinstance(candidates, list):
        candidates = []

    all_text = _norm_text(title, recommended, prompt)

    reasons: list[str] = []
    risk = "low"

    if mode == "generated_image":
        risk = "medium"
        reasons.append("ai_generated_image_may_be_misinterpreted_as_real")

    if mode in {"source_screenshot"}:
        risk = "medium"
        reasons.append("source_screenshot_may_be_misinterpreted_as_official_or_on_scene")

    if event_type in {"exchange_risk", "security_incident"} and mode in {"generated_image"}:
        risk = "high"
        reasons.append("incident_visual_may_create_panic_or_mislead")

    if _contains_any(all_text, ["黑客", "被盗", "攻击", "漏洞", "exploit", "phishing"]) and mode == "generated_image":
        risk = "high"
        reasons.append("avoid_exaggerated_hacker_scene")

    if _contains_any(all_text, ["总统", "法官", "议员", "监管", "sec", "cftc", "央行行长", "财长"]) and mode in {
        "generated_image",
        "source_screenshot",
    }:
        risk = "high"
        reasons.append("political_or_regulator_portrait_may_be_misleading_without_authorization")

    if candidates:
        reasons.append("image_candidates_copyright_unclear_do_not_download_or_reuse_directly")
        if mode in {"generated_image", "source_screenshot"} and risk == "low":
            risk = "medium"

    has_sources = bool(visual_brief.get("image_candidates"))
    if mode in {"data_card", "template_card"} and not has_sources:
        risk = "medium" if risk == "low" else risk
        reasons.append("data_source_anchor_missing_for_card")

    uniq = []
    for r in reasons:
        if r and r not in uniq:
            uniq.append(r)
    return risk, uniq

