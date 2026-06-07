from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _load_banned(root: Path) -> dict[str, Any]:
    p = root / "configs" / "x_taste_banned_phrases_v005.json"
    return _read_json(p) if p.exists() else {}


def _count_quotes(s: str) -> dict[str, int]:
    return {
        "corner_quotes": s.count("「") + s.count("」") + s.count("『") + s.count("』"),
        "double_quotes": s.count('"'),
    }


def _find_violations(text: str, banned: dict[str, Any]) -> list[str]:
    s = text or ""
    v: list[str] = []

    for p in banned.get("banned_phrases") or []:
        if isinstance(p, str) and p and p in s:
            v.append(f"banned_phrase:{p}")

    for p in banned.get("banned_claim_phrases") or []:
        if isinstance(p, str) and p and p in s:
            v.append(f"banned_claim:{p}")

    for p in banned.get("banned_advice_phrases") or []:
        if isinstance(p, str) and p and p in s:
            v.append(f"banned_advice:{p}")

    if re.search(r"(?m)^\s*[-*]\s+\S+", s):
        v.append("markdown_list_detected")

    if re.search(r"(?i)\b(buy|sell|long|short)\b", s):
        v.append("explicit_buy_sell_en")
    if re.search(r"(?i)(投资建议|喊单|买入|卖出|做多|做空|抄底|梭哈|必涨|必跌)", s):
        v.append("explicit_buy_sell_zh")

    if re.search(r"(主力|庄家).{0,6}(拉盘|洗盘|爆空|控盘)", s):
        v.append("manipulation_claim_detected")

    if re.search(r"(你(们)?|他(们)?)(就是|这种|这类).{0,10}(废物|傻|蠢|脑残|小丑|韭菜)", s):
        v.append("personal_attack_detected")
    if re.search(r"(先去学学|你懂不懂|小白才会)", s):
        v.append("patronizing_attack_detected")

    q = _count_quotes(s)
    if q["double_quotes"] > 0:
        v.append("double_quotes_present")
    if q["corner_quotes"] >= 8:
        v.append("too_many_corner_quotes")

    if re.search(r"(据(称|报道)|最新消息|宣布|正式上线|全面升级|重磅|引发热议)", s):
        v.append("news_tone_detected")

    if re.search(r"score\s*:\s*\d+\s*/\s*\d+", s):
        v.append("score_format_slash_detected")

    return v


def _len_violation(s: str, limit: int) -> bool:
    return len((s or "").strip()) > limit


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    src = reports_dir / "x_v2_006_real_event_persona_dryrun_report.json"
    if not src.exists():
        raise SystemExit(2)

    banned = _load_banned(root)
    report = _read_json(src)
    items = report.get("items") if isinstance(report.get("items"), list) else []

    allowed_source_modes = {
        "integration_published_real",
        "shared_event_pack_real",
        "article_hotspot_export_real",
        "local_latest_stream_real",
        "blocked_no_real_source",
    }
    forbidden_source_modes = {"mock_sample", "fake_demo", "hand_written_only"}

    gate_results: list[dict[str, Any]] = []
    queue = {"ready": [], "need_rewrite": [], "downgraded": []}

    for it in items:
        if not isinstance(it, dict):
            continue
        event_id = str(it.get("event_id") or "")
        if str(it.get("route") or "") == "DOWNGRADE_TO_ARTICLE_OR_NEWS":
            queue["downgraded"].append({"event_id": event_id, "reason": str(it.get("reason") or "")})
            gate_results.append({"event_id": event_id, "route": "DOWNGRADE_TO_ARTICLE_OR_NEWS", "passed": True, "violations": []})
            continue

        persona = it.get("persona_writer_result") if isinstance(it.get("persona_writer_result"), dict) else {}
        fin = it.get("final") if isinstance(it.get("final"), dict) else {}

        source_mode = str(fin.get("source_mode") or "")
        observed_at = str(fin.get("observed_at") or "")
        violations: list[str] = []
        if not source_mode:
            violations.append("missing_source_mode")
        elif source_mode in forbidden_source_modes:
            violations.append(f"forbidden_source_mode:{source_mode}")
        elif source_mode not in allowed_source_modes:
            violations.append(f"unknown_source_mode:{source_mode}")
        if not observed_at:
            violations.append("missing_observed_at")

        personal_sharp = str(persona.get("personal_sharp") or "").strip()
        personal_balanced = str(persona.get("personal_balanced") or "").strip()
        reply = persona.get("reply_hot_take") if isinstance(persona.get("reply_hot_take"), dict) else {}
        rh = {
            "sarcastic": str(reply.get("sarcastic") or "").strip(),
            "sharp_but_safe": str(reply.get("sharp_but_safe") or "").strip(),
            "og_explainer": str(reply.get("og_explainer") or "").strip(),
        }

        if personal_sharp and _len_violation(personal_sharp, 120):
            violations.append("personal_sharp_len>120")
        if personal_balanced and _len_violation(personal_balanced, 140):
            violations.append("personal_balanced_len>140")
        for k, v0 in rh.items():
            if v0 and _len_violation(v0, 80):
                violations.append(f"reply_hot_take.{k}_len>80")

        merged = "\n".join([personal_sharp, personal_balanced, rh["sarcastic"], rh["sharp_but_safe"], rh["og_explainer"]]).strip()
        violations.extend(_find_violations(merged, banned))

        if "sample_shared_event_pack" in merged:
            violations.append("static_sample_detected")
        if event_id.startswith("evt_") and source_mode != "integration_published_real":
            violations.append("static_mock_event_id_detected")
        if "offline_" in merged.lower():
            violations.append("offline_placeholder_detected")

        passed = len(violations) == 0
        gate_results.append({"event_id": event_id, "route": "X_PERSONA_GENERATION", "passed": passed, "violations": violations})

        status = str(fin.get("status") or "NEED_REWRITE")
        if not passed:
            status = "NEED_REWRITE"

        post = personal_sharp or personal_balanced
        if status == "APPROVED_FOR_X_DRYRUN":
            queue["ready"].append(
                {
                    "event_id": event_id,
                    "source_mode": source_mode,
                    "observed_at": observed_at,
                    "persona": str(fin.get("primary_persona") or ""),
                    "post": post,
                    "reply_hot_take": rh,
                    "score": _safe_int(fin.get("score"), 0),
                    "threshold": 80,
                    "decision": str(fin.get("decision") or ""),
                    "risk_level": str(fin.get("risk_level") or ""),
                    "recommended_publish_mode": "manual_test_account_only",
                    "publish_status": "not_published",
                }
            )
        else:
            reason = ";".join(list(fin.get("reasons") or []) + (["taste_gate_failed"] if not passed else []))
            queue["need_rewrite"].append({"event_id": event_id, "source_mode": source_mode, "observed_at": observed_at, "reason": reason})

    taste_report = {
        "task_id": "x_v2_006_real_event_persona_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "passed": len([x for x in gate_results if x.get("route") == "X_PERSONA_GENERATION" and x.get("passed") is not True]) == 0,
        "results": gate_results,
    }
    _write_json(reports_dir / "x_v2_006_taste_gate_report.json", taste_report)

    md: list[str] = []
    md.append("# X v2-006 Taste Gate Report\n\n")
    md.append(f"- generated_at_utc: {taste_report.get('generated_at_utc')}\n")
    md.append(f"- passed: {str(taste_report.get('passed')).lower()}\n\n")
    md.append("## Failed\n")
    failed = [x for x in gate_results if x.get("route") == "X_PERSONA_GENERATION" and x.get("passed") is not True]
    if not failed:
        md.append("- (none)\n")
    else:
        for x in failed:
            md.append(f"- {x.get('event_id')}: {json.dumps(x.get('violations') or [], ensure_ascii=False)}\n")
    (reports_dir / "x_v2_006_taste_gate_report.md").write_text("".join(md), encoding="utf-8")

    queue_out = {
        "task_id": "x_v2_006_real_event_persona_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "ready": queue["ready"],
        "need_rewrite": queue["need_rewrite"],
        "downgrade_to_article_news": queue["downgraded"],
        "safety": {"x_published": False, "x_api_connected": False},
    }
    _write_json(reports_dir / "x_v2_006_test_account_queue.json", queue_out)

    qm: list[str] = []
    qm.append("# X v2-006 Test Account Queue\n\n")
    qm.append(f"- generated_at_utc: {queue_out.get('generated_at_utc')}\n\n")

    qm.append("## Ready for test account draft queue\n\n")
    if not queue["ready"]:
        qm.append("- (none)\n\n")
    else:
        for r in queue["ready"]:
            qm.append("---\n\n")
            qm.append(f"- event_id: {r.get('event_id')}\n")
            qm.append(f"- source_mode: {r.get('source_mode')}\n")
            qm.append(f"- observed_at: {r.get('observed_at')}\n")
            qm.append(f"- persona: {r.get('persona')}\n")
            qm.append(f"- score: {r.get('score')}\n")
            qm.append(f"- threshold: {r.get('threshold')}\n")
            qm.append(f"- decision: {r.get('decision')}\n")
            qm.append(f"- risk_level: {r.get('risk_level')}\n")
            qm.append(f"- recommended_publish_mode: {r.get('recommended_publish_mode')}\n")
            qm.append(f"- publish_status: {r.get('publish_status')}\n\n")
            qm.append("Post:\n\n")
            qm.append(str(r.get("post") or "").strip() + "\n\n")
            rh = r.get("reply_hot_take") if isinstance(r.get("reply_hot_take"), dict) else {}
            qm.append("Reply hot take:\n")
            qm.append(f"- sarcastic: {str(rh.get('sarcastic') or '').strip()}\n")
            qm.append(f"- sharp_but_safe: {str(rh.get('sharp_but_safe') or '').strip()}\n")
            qm.append(f"- og_explainer: {str(rh.get('og_explainer') or '').strip()}\n\n")

    qm.append("## Need rewrite\n\n")
    if not queue["need_rewrite"]:
        qm.append("- (none)\n\n")
    else:
        for r in queue["need_rewrite"]:
            qm.append(f"- {r.get('event_id')}: {r.get('reason')}\n")
        qm.append("\n")

    qm.append("## Downgrade to article/news\n\n")
    if not queue["downgraded"]:
        qm.append("- (none)\n")
    else:
        for r in queue["downgraded"]:
            qm.append(f"- {r.get('event_id')}: {r.get('reason')}\n")

    (reports_dir / "x_v2_006_test_account_queue.md").write_text("".join(qm), encoding="utf-8")


if __name__ == "__main__":
    main()
