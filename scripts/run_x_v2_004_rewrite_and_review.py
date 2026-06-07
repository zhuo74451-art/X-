from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_client import call_llm_task, load_openrouter_api_key


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(_read_text(path))
    return obj if isinstance(obj, dict) else {}


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _load_prompt(root: Path, rel_path: str) -> str:
    return _read_text(root / rel_path)


def _build_event_pack(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(event.get("input_id") or "").strip(),
        "title": str(event.get("title") or "").strip(),
        "summary": str(event.get("summary") or "").strip(),
        "event_type": str(event.get("event_type") or "").strip(),
        "assets": event.get("asset_symbols") if isinstance(event.get("asset_symbols"), list) else [],
        "source_pack": event.get("source_pack") if isinstance(event.get("source_pack"), list) else [],
        "fact_pack": event.get("fact_pack") if isinstance(event.get("fact_pack"), dict) else {},
        "risk_flags": event.get("risk_flags") if isinstance(event.get("risk_flags"), list) else [],
        "image_candidates": event.get("image_candidates") if isinstance(event.get("image_candidates"), list) else [],
        "recommended_outputs": event.get("recommended_outputs") if isinstance(event.get("recommended_outputs"), list) else [],
        "review_required": bool(event.get("review_required")) if isinstance(event.get("review_required"), bool) else True,
    }


def _approved_row_from_v3(row: dict[str, Any]) -> dict[str, Any]:
    writer = row.get("writer") if isinstance(row.get("writer"), dict) else {}
    reviewer = row.get("reviewer") if isinstance(row.get("reviewer"), dict) else {}
    risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
    ra = writer.get("reply_angle") if isinstance(writer.get("reply_angle"), dict) else {}
    why = []
    why.append("v2_002_hard_gate_passed=true (from v003 pipeline)")
    why.append(f"reviewer_decision={str(reviewer.get('review_decision') or '')}")
    why.append(f"risk_decision={str(risk.get('risk_decision') or '')}")
    why.append(f"x_taste_score={_safe_int(reviewer.get('x_taste_score'), 0)}>=80")
    why.append(f"human_taste_score={_safe_int(reviewer.get('human_taste_score'), 0)}>=80")
    why.append(f"ai_taste_risk={str(reviewer.get('ai_taste_risk') or '')}!=high")
    why.append(f"boring_risk={str(reviewer.get('boring_risk') or '')}!=high")
    why.append(f"risk_level={str(risk.get('risk_level') or '')}!=high")
    return {
        "event_id": str(row.get("event_id") or ""),
        "title": str(row.get("title") or ""),
        "personal_post": str(writer.get("personal_post") or ""),
        "reply_angle": {
            "aggressive": str(ra.get("aggressive") or ""),
            "sarcastic": str(ra.get("sarcastic") or ""),
            "og_explainer": str(ra.get("og_explainer") or ""),
        },
        "x_taste_score": _safe_int(reviewer.get("x_taste_score"), 0),
        "human_taste_score": _safe_int(reviewer.get("human_taste_score"), 0),
        "risk_level": str(risk.get("risk_level") or ""),
        "reviewer_decision": str(reviewer.get("review_decision") or ""),
        "risk_decision": str(risk.get("risk_decision") or ""),
        "why_approved": why,
    }


def _render_approved_export_md(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# X v2-004 Approved Dry-run Export\n\n")
    lines.append(f"- generated_at_utc: {_utc_now_iso()}\n")
    lines.append(f"- approved_count: {len(rows)}\n\n")
    for idx, r in enumerate(rows, start=1):
        lines.append(f"---\n\n## Approved {idx}\n")
        lines.append(f"- event_id: {r.get('event_id')}\n")
        lines.append(f"- title: {r.get('title')}\n")
        lines.append(f"- reviewer_decision: {r.get('reviewer_decision')}\n")
        lines.append(f"- risk_decision: {r.get('risk_decision')}\n")
        lines.append(f"- x_taste_score: {r.get('x_taste_score')}\n")
        lines.append(f"- human_taste_score: {r.get('human_taste_score')}\n")
        lines.append(f"- risk_level: {r.get('risk_level')}\n")
        lines.append("\n### Personal Post\n\n")
        lines.append(str(r.get("personal_post") or "").strip() + "\n")
        ra = r.get("reply_angle") if isinstance(r.get("reply_angle"), dict) else {}
        lines.append("\n### Reply Angles\n\n")
        lines.append("Aggressive：\n" + str(ra.get("aggressive") or "").strip() + "\n\n")
        lines.append("Sarcastic：\n" + str(ra.get("sarcastic") or "").strip() + "\n\n")
        lines.append("OG Explainer：\n" + str(ra.get("og_explainer") or "").strip() + "\n")
        lines.append("\n### Why Approved\n\n")
        for x in r.get("why_approved") or []:
            lines.append(f"- {str(x)}\n")
        lines.append("\n")
    return "".join(lines)


def _rewriter_user_prompt(payload: dict[str, Any]) -> str:
    return (
        "input:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\n"
        + "只能基于 input，不得编造。只输出 JSON。\n"
    )


def _review_user_prompt(event_pack: dict[str, Any], writer_result: dict[str, Any]) -> str:
    return (
        "input_event_pack:\n"
        + json.dumps(event_pack, ensure_ascii=False)
        + "\n\n"
        + "writer_result:\n"
        + json.dumps(writer_result, ensure_ascii=False)
        + "\n\n"
        + "只输出 JSON。\n"
    )


def _final_status_for_event(
    *,
    v2_002_hard_gate_passed: bool,
    writer_ok: bool,
    reviewer: dict[str, Any],
    risk: dict[str, Any],
) -> tuple[str, list[str]]:
    if not v2_002_hard_gate_passed:
        return "NEED_REWRITE_AGAIN", ["v2_002_hard_gate_failed"]
    if not writer_ok:
        return "NEED_REWRITE_AGAIN", ["rewriter_failed_or_invalid_json"]

    reviewer_decision = str(reviewer.get("review_decision") or "").strip()
    risk_decision = str(risk.get("risk_decision") or "").strip()

    if risk_decision == "BLOCK":
        return "BLOCKED_BY_RISK", ["risk_decision=BLOCK"]
    if reviewer_decision == "REJECT":
        return "REJECTED_BY_REVIEWER", ["review_decision=REJECT"]

    x_taste = _safe_int(reviewer.get("x_taste_score"), 0)
    human = _safe_int(reviewer.get("human_taste_score"), 0)
    ai_risk = str(reviewer.get("ai_taste_risk") or "").strip()
    boring = str(reviewer.get("boring_risk") or "").strip()
    risk_level = str(risk.get("risk_level") or "").strip()

    ok = (
        reviewer_decision == "APPROVE_FOR_DRYRUN"
        and risk_decision == "PASS"
        and x_taste >= 80
        and human >= 80
        and ai_risk != "high"
        and boring != "high"
        and risk_level != "high"
    )
    if ok:
        return "APPROVED_FOR_X_DRYRUN", []

    reasons: list[str] = []
    if reviewer_decision != "APPROVE_FOR_DRYRUN":
        reasons.append(f"review_decision={reviewer_decision}")
    if risk_decision != "PASS":
        reasons.append(f"risk_decision={risk_decision}")
    if x_taste < 80:
        reasons.append("x_taste_score<80")
    if human < 80:
        reasons.append("human_taste_score<80")
    if ai_risk == "high":
        reasons.append("ai_taste_risk=high")
    if boring == "high":
        reasons.append("boring_risk=high")
    if risk_level == "high":
        reasons.append("risk_level=high")
    return "NEED_REWRITE_AGAIN", reasons


def _taste_gate_violations(text: str) -> list[str]:
    s = text or ""
    banned_phrases = [
        "值得关注",
        "引发市场关注",
        "总的来说",
        "综上",
        "让我们深入",
        "在 Web3 快速发展的世界里",
        "这反映出",
        "这意味着",
        "Exciting news",
        "In conclusion",
    ]
    out: list[str] = []
    for p in banned_phrases:
        if p in s:
            out.append(f"banned_phrase:{p}")
    if re.search(r"(?m)^\s*[-*]\s+\S+", s):
        out.append("markdown_list_detected")
    emojis = re.findall(r"[\U0001F300-\U0001FAFF]", s)
    if len(emojis) >= 2:
        out.append("multiple_emojis_detected")
    if re.search(r"(?i)\b(buy|sell|long|short)\b", s):
        out.append("explicit_buy_sell_en")
    if re.search(r"(?i)(喊单|抄底|梭哈|稳赚|必涨|必跌|买入|卖出|做多|做空)", s):
        out.append("explicit_buy_sell_zh")
    return out


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    v3_report_path = reports_dir / "x_v2_003_ai_content_review_report.json"
    if not v3_report_path.exists():
        raise SystemExit(2)

    if not load_openrouter_api_key():
        raise SystemExit(2)

    os.environ["MODEL_RUNTIME"] = "openrouter"
    if not (os.getenv("OPENROUTER_MODEL") or "").strip():
        os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"
    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    v3 = _read_json(v3_report_path)
    results = v3.get("results_index") if isinstance(v3.get("results_index"), list) else []

    approved_rows_v3 = [r for r in results if isinstance(r, dict) and str(r.get("final_status") or "") == "APPROVED_FOR_X_DRYRUN"]
    need_rewrite_rows_v3 = [r for r in results if isinstance(r, dict) and str(r.get("final_status") or "") == "NEED_REWRITE"]

    approved_export_rows = [_approved_row_from_v3(r) for r in approved_rows_v3]
    approved_export = {
        "task_id": "x_v2_004_dryrun_export_and_rewrite",
        "generated_at_utc": _utc_now_iso(),
        "v2_003_report": str(v3_report_path),
        "approved_count": len(approved_export_rows),
        "items": approved_export_rows,
    }
    _write_json(reports_dir / "x_v2_004_approved_dryrun_export.json", approved_export)
    (reports_dir / "x_v2_004_approved_dryrun_export.md").write_text(
        _render_approved_export_md(approved_export_rows),
        encoding="utf-8",
    )

    rewriter_prompt = _load_prompt(root, "prompts/x_rewriter_personal_reply_v004.md")
    reviewer_prompt = _load_prompt(root, "prompts/x_ai_reviewer_v003.md")
    risk_prompt = _load_prompt(root, "prompts/x_ai_risk_auditor_v003.md")

    out_root = root / "out" / "x_review_pack_v004"
    out_root.mkdir(parents=True, exist_ok=True)

    new_model_calls = 0
    rewritten: list[dict[str, Any]] = []

    for r in need_rewrite_rows_v3[:2]:
        event_id = str(r.get("event_id") or "").strip()
        v3_dir = root / "out" / "x_review_pack_v003" / event_id
        event_json = _read_json(v3_dir / "writer_request.json").get("input_event_pack") if (v3_dir / "writer_request.json").exists() else {}

        event_base = _read_json(v3_dir / "writer_request.json").get("input_event_pack") if (v3_dir / "writer_request.json").exists() else {}
        if not isinstance(event_base, dict) or not event_base:
            event_pack = _build_event_pack(_read_json(root / "out" / "x_review_pack_v002" / event_id / "event.json"))
        else:
            event_pack = event_base

        writer_v3 = r.get("writer") if isinstance(r.get("writer"), dict) else {}
        reviewer_v3 = r.get("reviewer") if isinstance(r.get("reviewer"), dict) else {}
        risk_v3 = r.get("risk") if isinstance(r.get("risk"), dict) else {}

        required_fixes = reviewer_v3.get("required_fixes") if isinstance(reviewer_v3.get("required_fixes"), list) else []
        main_weaknesses = reviewer_v3.get("main_weaknesses") if isinstance(reviewer_v3.get("main_weaknesses"), list) else []

        payload = {
            "event_pack": event_pack,
            "writer_result_v003": writer_v3,
            "reviewer_result_v003": reviewer_v3,
            "risk_result_v003": risk_v3,
            "required_fixes": required_fixes,
            "main_weaknesses": main_weaknesses,
        }

        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        rewriter_req = {
            "task_type": "x_rewriter_personal_reply_v004",
            "runtime": "openrouter",
            "model": model,
            "temperature": 0.6,
            "max_tokens": 900,
            "event_id": event_id,
        }
        _write_json(out_dir / "rewriter_request.json", rewriter_req)

        rewriter_raw: dict[str, Any] = {}
        rewriter_result: dict[str, Any] = {"event_id": event_id}

        if new_model_calls + 1 > 6:
            rewriter_result = {"event_id": event_id, "error": "model_call_budget_exceeded"}
        else:
            rr = call_llm_task(
                task_type="x_rewriter_personal_reply_v004",
                system_prompt=rewriter_prompt,
                user_prompt=_rewriter_user_prompt(payload),
                expect_json=True,
                temperature=0.6,
                max_tokens=900,
            )
            new_model_calls += 1
            rewriter_raw = rr
            if rr.get("ok") is True and isinstance(rr.get("json"), dict):
                rewriter_result = rr["json"]
            else:
                rewriter_result = {"event_id": event_id, "error": rr.get("error") or "rewriter_failed"}
            if "event_id" not in rewriter_result:
                rewriter_result["event_id"] = event_id

        _write_json(out_dir / "rewriter_response_raw.json", rewriter_raw)
        _write_json(out_dir / "rewriter_result.json", rewriter_result)

        writer_ok = all(
            isinstance(rewriter_result.get(k), str) and str(rewriter_result.get(k) or "").strip()
            for k in ["event_id", "personal_post"]
        ) and isinstance(rewriter_result.get("reply_angle"), dict)

        reviewer_raw: dict[str, Any] = {}
        reviewer_result: dict[str, Any] = {"event_id": event_id, "review_decision": "NEED_REWRITE"}
        if new_model_calls + 1 <= 6:
            rv = call_llm_task(
                task_type="x_ai_reviewer_v003",
                system_prompt=reviewer_prompt,
                user_prompt=_review_user_prompt(event_pack, rewriter_result),
                expect_json=True,
                temperature=0.2,
                max_tokens=900,
            )
            new_model_calls += 1
            reviewer_raw = rv
            if rv.get("ok") is True and isinstance(rv.get("json"), dict):
                reviewer_result = rv["json"]
            else:
                reviewer_result = {"event_id": event_id, "review_decision": "NEED_REWRITE", "error": rv.get("error") or "reviewer_failed"}
        else:
            reviewer_result = {"event_id": event_id, "review_decision": "NEED_REWRITE", "error": "model_call_budget_exceeded"}
        if "event_id" not in reviewer_result:
            reviewer_result["event_id"] = event_id
        _write_json(out_dir / "ai_reviewer_result.json", reviewer_result)
        _write_json(out_dir / "ai_reviewer_response_raw.json", reviewer_raw)

        risk_raw: dict[str, Any] = {}
        risk_result: dict[str, Any] = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium"}
        if new_model_calls + 1 <= 6:
            rk = call_llm_task(
                task_type="x_ai_risk_auditor_v003",
                system_prompt=risk_prompt,
                user_prompt=_review_user_prompt(event_pack, rewriter_result),
                expect_json=True,
                temperature=0.2,
                max_tokens=900,
            )
            new_model_calls += 1
            risk_raw = rk
            if rk.get("ok") is True and isinstance(rk.get("json"), dict):
                risk_result = rk["json"]
            else:
                risk_result = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium", "error": rk.get("error") or "risk_failed"}
        else:
            risk_result = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium", "error": "model_call_budget_exceeded"}
        if "event_id" not in risk_result:
            risk_result["event_id"] = event_id
        _write_json(out_dir / "ai_risk_result.json", risk_result)
        _write_json(out_dir / "ai_risk_response_raw.json", risk_raw)

        hard_gate_passed = True
        v2_hg = root / "out" / "x_review_pack_v002" / event_id / "hard_gate_report.json"
        if v2_hg.exists():
            hard_gate_passed = bool(_read_json(v2_hg).get("passed") is True)

        status, reasons = _final_status_for_event(
            v2_002_hard_gate_passed=hard_gate_passed,
            writer_ok=writer_ok,
            reviewer=reviewer_result,
            risk=risk_result,
        )
        final = {
            "event_id": event_id,
            "title": str(event_pack.get("title") or ""),
            "status": status,
            "reasons": reasons,
            "hard_gate_passed": hard_gate_passed,
            "review_decision": str(reviewer_result.get("review_decision") or ""),
            "risk_decision": str(risk_result.get("risk_decision") or ""),
            "x_taste_score": _safe_int(reviewer_result.get("x_taste_score"), 0),
            "human_taste_score": _safe_int(reviewer_result.get("human_taste_score"), 0),
            "risk_level": str(risk_result.get("risk_level") or ""),
        }
        _write_json(out_dir / "x_final_decision.json", final)

        rewritten.append(
            {
                "event_id": event_id,
                "title": str(event_pack.get("title") or ""),
                "rewriter_result": rewriter_result,
                "reviewer_result": reviewer_result,
                "risk_result": risk_result,
                "final": final,
            }
        )

    rewrite_report = {
        "task_id": "x_v2_004_dryrun_export_and_rewrite",
        "generated_at_utc": _utc_now_iso(),
        "model": model,
        "new_model_calls_made": new_model_calls,
        "rewritten_events": len(rewritten),
        "results": rewritten,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "key_committed": False,
        },
    }
    _write_json(reports_dir / "x_v2_004_rewrite_review_report.json", rewrite_report)
    (reports_dir / "x_v2_004_rewrite_review_report.md").write_text(
        "# X v2-004 Rewrite Review Report\n\n"
        f"- generated_at_utc: {rewrite_report.get('generated_at_utc')}\n"
        f"- model: {rewrite_report.get('model')}\n"
        f"- new_model_calls_made: {rewrite_report.get('new_model_calls_made')}\n"
        f"- rewritten_events: {rewrite_report.get('rewritten_events')}\n",
        encoding="utf-8",
    )

    final_candidates: list[dict[str, Any]] = []
    for r in approved_export_rows:
        content = {
            "personal_post": r.get("personal_post"),
            "reply_angle": r.get("reply_angle"),
        }
        ra = content.get("reply_angle") if isinstance(content.get("reply_angle"), dict) else {}
        merged = "\n".join(
            [
                str(content.get("personal_post") or ""),
                str(ra.get("aggressive") or ""),
                str(ra.get("sarcastic") or ""),
                str(ra.get("og_explainer") or ""),
            ]
        )
        violations = _taste_gate_violations(merged)
        status = "APPROVED_FOR_X_DRYRUN" if not violations else "NEED_REWRITE_AGAIN"
        reasons = list(r.get("why_approved") or [])
        if violations:
            reasons.append("taste_gate_failed:" + ",".join(violations))

        final_candidates.append(
            {
                "event_id": r.get("event_id"),
                "title": r.get("title"),
                "status": status,
                "source": "v2_003_approved",
                "content": content,
                "ai": {
                    "reviewer_decision": r.get("reviewer_decision"),
                    "risk_decision": r.get("risk_decision"),
                    "x_taste_score": r.get("x_taste_score"),
                    "human_taste_score": r.get("human_taste_score"),
                    "risk_level": r.get("risk_level"),
                },
                "reasons": reasons,
            }
        )

    for r in rewritten:
        fin = r.get("final") if isinstance(r.get("final"), dict) else {}
        st = str(fin.get("status") or "NEED_REWRITE_AGAIN")
        final_candidates.append(
            {
                "event_id": r.get("event_id"),
                "title": r.get("title"),
                "status": st if st in {"APPROVED_FOR_X_DRYRUN", "NEED_REWRITE_AGAIN", "BLOCKED_BY_RISK", "REJECTED_BY_REVIEWER"} else "NEED_REWRITE_AGAIN",
                "source": "v2_004_rewrite",
                "content": {
                    "personal_post": ((r.get("rewriter_result") or {}) if isinstance(r.get("rewriter_result"), dict) else {}).get("personal_post", ""),
                    "reply_angle": ((r.get("rewriter_result") or {}) if isinstance(r.get("rewriter_result"), dict) else {}).get("reply_angle", {}),
                },
                "ai": {
                    "reviewer_decision": str(((r.get("reviewer_result") or {}) if isinstance(r.get("reviewer_result"), dict) else {}).get("review_decision") or ""),
                    "risk_decision": str(((r.get("risk_result") or {}) if isinstance(r.get("risk_result"), dict) else {}).get("risk_decision") or ""),
                    "x_taste_score": _safe_int(((r.get("reviewer_result") or {}) if isinstance(r.get("reviewer_result"), dict) else {}).get("x_taste_score"), 0),
                    "human_taste_score": _safe_int(((r.get("reviewer_result") or {}) if isinstance(r.get("reviewer_result"), dict) else {}).get("human_taste_score"), 0),
                    "risk_level": str(((r.get("risk_result") or {}) if isinstance(r.get("risk_result"), dict) else {}).get("risk_level") or ""),
                },
                "reasons": fin.get("reasons") if isinstance(fin.get("reasons"), list) else [],
            }
        )

    final_counts = {
        "final_approved_count": len([x for x in final_candidates if x.get("status") == "APPROVED_FOR_X_DRYRUN"]),
        "still_need_rewrite": len([x for x in final_candidates if x.get("status") == "NEED_REWRITE_AGAIN"]),
        "blocked_by_risk": len([x for x in final_candidates if x.get("status") == "BLOCKED_BY_RISK"]),
        "rejected_by_reviewer": len([x for x in final_candidates if x.get("status") == "REJECTED_BY_REVIEWER"]),
    }

    final_report = {
        "task_id": "x_v2_004_dryrun_export_and_rewrite",
        "generated_at_utc": _utc_now_iso(),
        "v2_003_approved_count": len(approved_export_rows),
        "rewritten_count": len(rewritten),
        "rewrite_approved_count": len([x for x in final_candidates if x.get("source") == "v2_004_rewrite" and x.get("status") == "APPROVED_FOR_X_DRYRUN"]),
        "counts": final_counts,
        "items": final_candidates,
        "safety": {"x_published": False, "x_api_connected": False, "key_committed": False},
    }
    _write_json(reports_dir / "x_v2_004_final_dryrun_candidates.json", final_report)

    md: list[str] = []
    md.append("# X v2-004 Final Dry-run Candidates\n\n")
    md.append(f"- generated_at_utc: {final_report.get('generated_at_utc')}\n")
    md.append(f"- v2_003_approved_count: {final_report.get('v2_003_approved_count')}\n")
    md.append(f"- rewritten_count: {final_report.get('rewritten_count')}\n")
    md.append(f"- final_approved_count: {final_counts.get('final_approved_count')}\n")
    md.append(f"- still_need_rewrite: {final_counts.get('still_need_rewrite')}\n")
    md.append(f"- blocked_by_risk: {final_counts.get('blocked_by_risk')}\n")
    md.append(f"- rejected_by_reviewer: {final_counts.get('rejected_by_reviewer')}\n\n")
    for x in final_candidates:
        md.append("---\n\n")
        md.append(f"## {x.get('event_id')} | {x.get('status')}\n\n")
        md.append(f"标题：{x.get('title')}\n\n")
        c = x.get("content") if isinstance(x.get("content"), dict) else {}
        md.append("Personal Post：\n")
        md.append(str(c.get("personal_post") or "").strip() + "\n\n")
        ra = c.get("reply_angle") if isinstance(c.get("reply_angle"), dict) else {}
        md.append("Reply Angles：\n")
        md.append(f"- Aggressive：{str(ra.get('aggressive') or '').strip()}\n")
        md.append(f"- Sarcastic：{str(ra.get('sarcastic') or '').strip()}\n")
        md.append(f"- OG Explainer：{str(ra.get('og_explainer') or '').strip()}\n\n")
        ai = x.get("ai") if isinstance(x.get("ai"), dict) else {}
        md.append(f"AI Review：{ai.get('reviewer_decision')} | score {ai.get('x_taste_score')}/{ai.get('human_taste_score')}\n")
        md.append(f"AI Risk：{ai.get('risk_decision')} | risk_level {ai.get('risk_level')}\n\n")
        rs = x.get("reasons") if isinstance(x.get("reasons"), list) else []
        if rs:
            md.append("Reasons:\n")
            for r0 in rs[:12]:
                md.append(f"- {str(r0)}\n")
            md.append("\n")

    (reports_dir / "x_v2_004_final_dryrun_candidates.md").write_text("".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()
