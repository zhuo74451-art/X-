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

    return v


def _len_violation(s: str, limit: int) -> bool:
    return len((s or "").strip()) > limit


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    src = reports_dir / "x_v2_005_persona_split_report.json"
    if not src.exists():
        raise SystemExit(2)

    banned = _load_banned(root)
    report = _read_json(src)
    items = report.get("items") if isinstance(report.get("items"), list) else []

    gate_results: list[dict[str, Any]] = []
    final_groups = {
        "ready": [],
        "need_rewrite": [],
        "downgraded": [],
        "blocked_by_risk": [],
        "rejected_by_reviewer": [],
    }

    for it in items:
        if not isinstance(it, dict):
            continue
        event_id = str(it.get("event_id") or "")
        route = str(it.get("route") or it.get("status") or "")

        if route == "DOWNGRADE_TO_ARTICLE_OR_NEWS" or str(it.get("status") or "") == "DOWNGRADE_TO_ARTICLE_OR_NEWS":
            reason = str(it.get("reason") or "")
            final_groups["downgraded"].append({"event_id": event_id, "reason": reason})
            gate_results.append({"event_id": event_id, "route": "DOWNGRADE_TO_ARTICLE_OR_NEWS", "passed": True, "violations": []})
            continue

        persona = it.get("persona_writer_result") if isinstance(it.get("persona_writer_result"), dict) else {}
        fin = it.get("final") if isinstance(it.get("final"), dict) else {}
        reviewer = it.get("reviewer_result") if isinstance(it.get("reviewer_result"), dict) else {}
        risk = it.get("risk_result") if isinstance(it.get("risk_result"), dict) else {}

        personal_sharp = str(persona.get("personal_sharp") or "").strip()
        personal_balanced = str(persona.get("personal_balanced") or "").strip()
        reply = persona.get("reply_hot_take") if isinstance(persona.get("reply_hot_take"), dict) else {}
        rh = {
            "sarcastic": str(reply.get("sarcastic") or "").strip(),
            "sharp_but_safe": str(reply.get("sharp_but_safe") or "").strip(),
            "og_explainer": str(reply.get("og_explainer") or "").strip(),
        }

        violations: list[str] = []
        if personal_sharp and _len_violation(personal_sharp, 120):
            violations.append("personal_sharp_len>120")
        if personal_balanced and _len_violation(personal_balanced, 140):
            violations.append("personal_balanced_len>140")
        for k, v0 in rh.items():
            if v0 and _len_violation(v0, 80):
                violations.append(f"reply_hot_take.{k}_len>80")

        merged = "\n".join([personal_sharp, personal_balanced, rh["sarcastic"], rh["sharp_but_safe"], rh["og_explainer"]]).strip()
        violations.extend(_find_violations(merged, banned))

        passed = len(violations) == 0
        gate_results.append({"event_id": event_id, "route": "X_PERSONA_GENERATION", "passed": passed, "violations": violations})

        status = str(fin.get("status") or "NEED_REWRITE")
        risk_decision = str(fin.get("risk_decision") or risk.get("risk_decision") or "")
        review_decision = str(fin.get("reviewer_decision") or reviewer.get("review_decision") or "")

        final_status = status
        reasons = list(fin.get("reasons") or [])

        if not passed:
            final_status = "NEED_REWRITE"
            reasons = reasons + ["taste_gate_failed:" + ",".join(violations)]

        if final_status == "APPROVED_FOR_X_DRYRUN":
            final_groups["ready"].append(
                {
                    "event_id": event_id,
                    "persona": str(fin.get("primary_persona") or ""),
                    "post": personal_sharp or personal_balanced,
                    "reply_hot_take": rh,
                    "score": {
                        "x_taste_score": fin.get("x_taste_score"),
                        "human_taste_score": fin.get("human_taste_score"),
                        "reviewer_decision": review_decision,
                    },
                    "risk": {
                        "risk_level": fin.get("risk_level"),
                        "risk_decision": risk_decision,
                    },
                }
            )
        elif final_status == "BLOCKED_BY_RISK":
            final_groups["blocked_by_risk"].append({"event_id": event_id, "reason": ";".join(reasons) or "blocked_by_risk"})
        elif final_status == "REJECTED_BY_REVIEWER":
            final_groups["rejected_by_reviewer"].append({"event_id": event_id, "reason": ";".join(reasons) or "rejected_by_reviewer"})
        else:
            final_groups["need_rewrite"].append({"event_id": event_id, "reason": ";".join(reasons) or "need_rewrite"})

    taste_report = {
        "task_id": "x_v2_005_persona_split_test_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "passed": len([x for x in gate_results if x.get("route") == "X_PERSONA_GENERATION" and x.get("passed") is not True]) == 0,
        "results": gate_results,
    }
    _write_json(reports_dir / "x_v2_005_taste_gate_report.json", taste_report)

    md: list[str] = []
    md.append("# X v2-005 Taste Gate Report\n\n")
    md.append(f"- generated_at_utc: {taste_report.get('generated_at_utc')}\n")
    md.append(f"- passed: {str(taste_report.get('passed')).lower()}\n\n")
    md.append("## Failed\n")
    failed = [x for x in gate_results if x.get("route") == "X_PERSONA_GENERATION" and x.get("passed") is not True]
    if not failed:
        md.append("- (none)\n")
    else:
        for x in failed:
            md.append(f"- {x.get('event_id')}: {json.dumps(x.get('violations') or [], ensure_ascii=False)}\n")
    (reports_dir / "x_v2_005_taste_gate_report.md").write_text("".join(md), encoding="utf-8")

    package = {
        "task_id": "x_v2_005_persona_split_test_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "groups": final_groups,
        "safety": {"x_published": False, "x_api_connected": False},
    }
    _write_json(reports_dir / "x_v2_005_final_test_account_dryrun_package.json", package)

    pm: list[str] = []
    pm.append("# X v2-005 Final Test Account Dry-run Package\n\n")
    pm.append(f"- generated_at_utc: {package.get('generated_at_utc')}\n\n")

    pm.append("## 可进入测试号发布前准备\n\n")
    ready = final_groups["ready"]
    if not ready:
        pm.append("- (none)\n\n")
    else:
        for r in ready:
            pm.append(f"---\n\n### {r.get('event_id')} | persona={r.get('persona')}\n\n")
            pm.append(str(r.get("post") or "").strip() + "\n\n")
            rh = r.get("reply_hot_take") if isinstance(r.get("reply_hot_take"), dict) else {}
            pm.append("Reply hot take:\n")
            pm.append(f"- sarcastic: {str(rh.get('sarcastic') or '').strip()}\n")
            pm.append(f"- sharp_but_safe: {str(rh.get('sharp_but_safe') or '').strip()}\n")
            pm.append(f"- og_explainer: {str(rh.get('og_explainer') or '').strip()}\n\n")
            sc = r.get("score") if isinstance(r.get("score"), dict) else {}
            rk = r.get("risk") if isinstance(r.get("risk"), dict) else {}
            pm.append(f"score: {sc.get('x_taste_score')}/{sc.get('human_taste_score')} | decision={sc.get('reviewer_decision')}\n")
            pm.append(f"risk: {rk.get('risk_level')} | decision={rk.get('risk_decision')}\n\n")

    pm.append("## 仍需重写\n\n")
    nr = final_groups["need_rewrite"]
    if not nr:
        pm.append("- (none)\n\n")
    else:
        for r in nr:
            pm.append(f"- {r.get('event_id')}: {r.get('reason')}\n")
        pm.append("\n")

    pm.append("## 不适合 X，转文章/新闻\n\n")
    dg = final_groups["downgraded"]
    if not dg:
        pm.append("- (none)\n")
    else:
        for r in dg:
            pm.append(f"- {r.get('event_id')}: {r.get('reason')}\n")

    (reports_dir / "x_v2_005_final_test_account_dryrun_package.md").write_text("".join(pm), encoding="utf-8")


if __name__ == "__main__":
    main()

