from __future__ import annotations

import json
import os
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


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _load_prompt(root: Path, rel_path: str) -> str:
    p = root / rel_path
    return _read_text(p)


def _detect_key_missing() -> tuple[bool, str]:
    if not load_openrouter_api_key():
        return True, "BLOCKED_MISSING_OPENROUTER_KEY"
    return False, ""


def _build_event_pack_for_writer(event: dict[str, Any]) -> dict[str, Any]:
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


def _writer_user_prompt(event_pack: dict[str, Any]) -> str:
    return (
        "input_event_pack:\n"
        + json.dumps(event_pack, ensure_ascii=False)
        + "\n\n"
        + "只能基于 input_event_pack，不得编造。只输出 JSON。\n"
    )


def _reviewer_user_prompt(event_pack: dict[str, Any], writer_result: dict[str, Any]) -> str:
    return (
        "input_event_pack:\n"
        + json.dumps(event_pack, ensure_ascii=False)
        + "\n\n"
        + "writer_result:\n"
        + json.dumps(writer_result, ensure_ascii=False)
        + "\n\n"
        + "只输出 JSON。\n"
    )


def _risk_user_prompt(event_pack: dict[str, Any], writer_result: dict[str, Any]) -> str:
    return (
        "input_event_pack:\n"
        + json.dumps(event_pack, ensure_ascii=False)
        + "\n\n"
        + "writer_result:\n"
        + json.dumps(writer_result, ensure_ascii=False)
        + "\n\n"
        + "只输出 JSON。\n"
    )


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _final_decision(
    *,
    hard_gate_passed: bool,
    writer_ok: bool,
    reviewer: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, Any]:
    reviewer_decision = str(reviewer.get("review_decision") or "").strip()
    risk_decision = str(risk.get("risk_decision") or "").strip()
    x_taste_score = _safe_int(reviewer.get("x_taste_score"), 0)
    human_taste_score = _safe_int(reviewer.get("human_taste_score"), 0)
    ai_taste_risk = str(reviewer.get("ai_taste_risk") or "").strip()
    boring_risk = str(reviewer.get("boring_risk") or "").strip()
    risk_level = str(risk.get("risk_level") or "").strip()

    status = "NEED_REWRITE"
    reasons: list[str] = []

    if not hard_gate_passed:
        return {
            "status": "BLOCKED_HARD_GATE",
            "reasons": ["v2_002_hard_gate_failed"],
            "approved_for_x_dryrun": False,
        }
    if not writer_ok:
        return {
            "status": "NEED_REWRITE",
            "reasons": ["writer_failed_or_invalid_json"],
            "approved_for_x_dryrun": False,
        }
    if risk_decision == "BLOCK":
        return {
            "status": "BLOCKED_BY_RISK",
            "reasons": ["risk_decision=BLOCK"],
            "approved_for_x_dryrun": False,
        }
    if reviewer_decision == "REJECT":
        return {
            "status": "REJECTED_BY_REVIEWER",
            "reasons": ["review_decision=REJECT"],
            "approved_for_x_dryrun": False,
        }

    approved = (
        reviewer_decision == "APPROVE_FOR_DRYRUN"
        and risk_decision == "PASS"
        and x_taste_score >= 80
        and human_taste_score >= 80
        and ai_taste_risk != "high"
        and boring_risk != "high"
        and risk_level != "high"
    )
    if approved:
        status = "APPROVED_FOR_X_DRYRUN"
    else:
        status = "NEED_REWRITE" if risk_decision != "BLOCK" else "BLOCKED_BY_RISK"
        if reviewer_decision != "APPROVE_FOR_DRYRUN":
            reasons.append(f"review_decision={reviewer_decision}")
        if risk_decision != "PASS":
            reasons.append(f"risk_decision={risk_decision}")
        if x_taste_score < 80:
            reasons.append("x_taste_score<80")
        if human_taste_score < 80:
            reasons.append("human_taste_score<80")
        if ai_taste_risk == "high":
            reasons.append("ai_taste_risk=high")
        if boring_risk == "high":
            reasons.append("boring_risk=high")
        if risk_level == "high":
            reasons.append("risk_level=high")

    return {
        "status": status,
        "reasons": reasons,
        "approved_for_x_dryrun": status == "APPROVED_FOR_X_DRYRUN",
    }


def _render_packet_md(
    *,
    event_pack: dict[str, Any],
    writer: dict[str, Any],
    reviewer: dict[str, Any],
    risk: dict[str, Any],
    final: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# X Review Packet v003\n\n")
    lines.append(f"- generated_at_utc: {_utc_now_iso()}\n")
    lines.append(f"- event_id: {str(event_pack.get('event_id') or '')}\n")
    lines.append(f"- title: {str(event_pack.get('title') or '')}\n")
    lines.append(f"- final_status: {str(final.get('status') or '')}\n")

    lines.append("\n## Personal Post\n\n")
    lines.append(str(writer.get("personal_post") or "").strip() + "\n")

    ra = writer.get("reply_angle") if isinstance(writer.get("reply_angle"), dict) else {}
    lines.append("\n## Reply Angles\n\n")
    lines.append("Aggressive：\n" + str(ra.get("aggressive") or "").strip() + "\n\n")
    lines.append("Sarcastic：\n" + str(ra.get("sarcastic") or "").strip() + "\n\n")
    lines.append("OG Explainer：\n" + str(ra.get("og_explainer") or "").strip() + "\n")

    lines.append("\n## AI Review\n\n")
    lines.append(f"- decision: {str(reviewer.get('review_decision') or '')}\n")
    lines.append(f"- x_taste_score: {str(reviewer.get('x_taste_score') or '')}\n")
    lines.append(f"- human_taste_score: {str(reviewer.get('human_taste_score') or '')}\n")
    lines.append(f"- ai_taste_risk: {str(reviewer.get('ai_taste_risk') or '')}\n")
    lines.append(f"- boring_risk: {str(reviewer.get('boring_risk') or '')}\n")

    lines.append("\n## Risk Audit\n\n")
    lines.append(f"- decision: {str(risk.get('risk_decision') or '')}\n")
    lines.append(f"- risk_level: {str(risk.get('risk_level') or '')}\n")

    lines.append("\n## Notes\n\n")
    lines.append("- 本轮只生成 personal_post + reply_angle。\n")
    lines.append("- 未连接 X API；未发布；未自动发布。\n")
    return "".join(lines)


def _write_summary_md(out_root: Path, groups: dict[str, list[dict[str, Any]]]) -> None:
    approved = groups.get("APPROVED_FOR_X_DRYRUN") or []
    rewrite = groups.get("NEED_REWRITE") or []
    blocked = groups.get("BLOCKED_BY_RISK") or []
    rejected = groups.get("REJECTED_BY_REVIEWER") or []

    def _render_list(path: Path, title: str, rows: list[dict[str, Any]]) -> None:
        lines: list[str] = []
        lines.append(f"# {title}\n\n")
        for r in rows:
            eid = str(r.get("event_id") or "")
            t = str(r.get("title") or "")
            w = r.get("writer") if isinstance(r.get("writer"), dict) else {}
            ra = w.get("reply_angle") if isinstance(w.get("reply_angle"), dict) else {}
            reviewer = r.get("reviewer") if isinstance(r.get("reviewer"), dict) else {}
            risk = r.get("risk") if isinstance(r.get("risk"), dict) else {}
            lines.append("## Event\n")
            lines.append(f"标题：{t}\n\n")
            lines.append("## Personal Post\n")
            lines.append(f"正文：{str(w.get('personal_post') or '').strip()}\n\n")
            lines.append("## Reply Angles\n")
            lines.append(f"Aggressive：{str(ra.get('aggressive') or '').strip()}\n")
            lines.append(f"Sarcastic：{str(ra.get('sarcastic') or '').strip()}\n")
            lines.append(f"OG Explainer：{str(ra.get('og_explainer') or '').strip()}\n\n")
            lines.append("## AI Review\n")
            lines.append(
                f"score：{str(reviewer.get('x_taste_score') or '')}/{str(reviewer.get('human_taste_score') or '')}\n"
            )
            lines.append(f"risk：{str(reviewer.get('ai_taste_risk') or '')}/{str(reviewer.get('boring_risk') or '')}\n")
            lines.append(f"decision：{str(reviewer.get('review_decision') or '')}\n\n")
            lines.append("---\n\n")
        path.write_text("".join(lines), encoding="utf-8")

    _render_list(out_root / "approved_dryrun_posts.md", "Approved For X Dryrun Posts", approved)
    _render_list(out_root / "rewrite_needed.md", "Rewrite Needed", rewrite)
    _render_list(out_root / "blocked_by_risk.md", "Blocked By Risk", blocked)
    _render_list(out_root / "rejected_by_reviewer.md", "Rejected By Reviewer", rejected)


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    v2_index = root / "out" / "x_review_pack_v002" / "index.json"
    if not v2_index.exists():
        report = {
            "task_id": "x_v2_003_ai_personal_reply_generation_review",
            "generated_at_utc": _utc_now_iso(),
            "status": "BLOCKED",
            "blocked_reason": "missing_v2_002_review_packets",
            "model_calls_made": 0,
            "generated_events": 0,
            "counts": {},
            "safety": {"x_published": False, "x_api_connected": False, "paid_model_called": False},
        }
        _write_json(reports_dir / "x_v2_003_ai_content_review_report.json", report)
        (reports_dir / "x_v2_003_ai_content_review_report.md").write_text(
            "# X v2-003 AI Content Review Report\n\n- status: blocked\n- blocked_reason: missing_v2_002_review_packets\n",
            encoding="utf-8",
        )
        raise SystemExit(2)

    blocked, blocked_status = _detect_key_missing()
    if blocked:
        report = {
            "task_id": "x_v2_003_ai_personal_reply_generation_review",
            "generated_at_utc": _utc_now_iso(),
            "status": blocked_status,
            "blocked_reason": blocked_status,
            "key_loading": {
                "env_key_detected": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
                "local_secret_detected": bool(load_openrouter_api_key()) and not bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
            },
            "model_calls_made": 0,
            "generated_events": 0,
            "counts": {},
            "safety": {"x_published": False, "x_api_connected": False, "paid_model_called": False},
        }
        _write_json(reports_dir / "x_v2_003_ai_content_review_report.json", report)
        (reports_dir / "x_v2_003_ai_content_review_report.md").write_text(
            "# X v2-003 AI Content Review Report\n\n"
            f"- status: blocked\n- blocked_reason: {blocked_status}\n",
            encoding="utf-8",
        )
        raise SystemExit(2)

    os.environ["MODEL_RUNTIME"] = "openrouter"
    if not (os.getenv("OPENROUTER_MODEL") or "").strip():
        os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"

    writer_prompt = _load_prompt(root, "prompts/x_writer_personal_reply_v003.md")
    reviewer_prompt = _load_prompt(root, "prompts/x_ai_reviewer_v003.md")
    risk_prompt = _load_prompt(root, "prompts/x_ai_risk_auditor_v003.md")

    v2_root = v2_index.parent
    out_root = root / "out" / "x_review_pack_v003"
    out_root.mkdir(parents=True, exist_ok=True)

    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    event_dirs = [p for p in sorted(v2_root.iterdir()) if p.is_dir()]
    event_dirs = event_dirs[:4]

    model_calls = 0
    rows_for_summary: list[dict[str, Any]] = []

    for d in event_dirs:
        event = _read_json(d / "event.json") if (d / "event.json").exists() else {}
        hard_gate = _read_json(d / "hard_gate_report.json") if (d / "hard_gate_report.json").exists() else {}
        hard_gate_passed = bool(hard_gate.get("passed") is True)

        event_pack = _build_event_pack_for_writer(event)
        event_id = str(event_pack.get("event_id") or "").strip() or d.name

        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        writer_request = {
            "task_type": "x_writer_personal_reply_v003",
            "runtime": "openrouter",
            "model": model,
            "temperature": 0.6,
            "max_tokens": 900,
            "event_id": event_id,
            "input_event_pack": event_pack,
        }
        _write_json(out_dir / "writer_request.json", writer_request)

        writer_ok = False
        writer_result: dict[str, Any] = {"event_id": event_id, "error": ""}
        writer_raw: dict[str, Any] = {}

        if model_calls + 1 > 12:
            writer_result = {"event_id": event_id, "error": "model_call_budget_exceeded"}
        else:
            wr = call_llm_task(
                task_type="x_writer_personal_reply_v003",
                system_prompt=writer_prompt,
                user_prompt=_writer_user_prompt(event_pack),
                expect_json=True,
                temperature=0.6,
                max_tokens=900,
            )
            model_calls += 1
            writer_raw = wr
            writer_ok = bool(wr.get("ok") is True and isinstance(wr.get("json"), dict))
            writer_result = wr.get("json") if isinstance(wr.get("json"), dict) else {"event_id": event_id, "error": wr.get("error") or ""}
            if "event_id" not in writer_result:
                writer_result["event_id"] = event_id

        _write_json(out_dir / "writer_response_raw.json", writer_raw)
        _write_json(out_dir / "writer_result.json", writer_result)

        reviewer_request = {
            "task_type": "x_ai_reviewer_v003",
            "runtime": "openrouter",
            "model": model,
            "temperature": 0.2,
            "max_tokens": 900,
            "event_id": event_id,
            "input_event_pack": event_pack,
            "writer_result": writer_result,
        }
        _write_json(out_dir / "ai_reviewer_request.json", reviewer_request)

        reviewer_raw: dict[str, Any] = {}
        reviewer_result: dict[str, Any] = {"event_id": event_id, "review_decision": "NEED_REWRITE"}
        if model_calls + 1 <= 12:
            rr = call_llm_task(
                task_type="x_ai_reviewer_v003",
                system_prompt=reviewer_prompt,
                user_prompt=_reviewer_user_prompt(event_pack, writer_result),
                expect_json=True,
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            reviewer_raw = rr
            if rr.get("ok") is True and isinstance(rr.get("json"), dict):
                reviewer_result = rr["json"]
            else:
                reviewer_result = {"event_id": event_id, "review_decision": "NEED_REWRITE", "error": rr.get("error") or "reviewer_failed"}
        else:
            reviewer_result = {"event_id": event_id, "review_decision": "NEED_REWRITE", "error": "model_call_budget_exceeded"}

        if "event_id" not in reviewer_result:
            reviewer_result["event_id"] = event_id

        _write_json(out_dir / "ai_reviewer_response_raw.json", reviewer_raw)
        _write_json(out_dir / "ai_reviewer_result.json", reviewer_result)

        risk_request = {
            "task_type": "x_ai_risk_auditor_v003",
            "runtime": "openrouter",
            "model": model,
            "temperature": 0.2,
            "max_tokens": 900,
            "event_id": event_id,
            "input_event_pack": event_pack,
            "writer_result": writer_result,
        }
        _write_json(out_dir / "ai_risk_request.json", risk_request)

        risk_raw: dict[str, Any] = {}
        risk_result: dict[str, Any] = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium"}
        if model_calls + 1 <= 12:
            rk = call_llm_task(
                task_type="x_ai_risk_auditor_v003",
                system_prompt=risk_prompt,
                user_prompt=_risk_user_prompt(event_pack, writer_result),
                expect_json=True,
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            risk_raw = rk
            if rk.get("ok") is True and isinstance(rk.get("json"), dict):
                risk_result = rk["json"]
            else:
                risk_result = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium", "error": rk.get("error") or "risk_failed"}
        else:
            risk_result = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium", "error": "model_call_budget_exceeded"}

        if "event_id" not in risk_result:
            risk_result["event_id"] = event_id

        _write_json(out_dir / "ai_risk_response_raw.json", risk_raw)
        _write_json(out_dir / "ai_risk_result.json", risk_result)

        final = _final_decision(
            hard_gate_passed=hard_gate_passed,
            writer_ok=writer_ok,
            reviewer=reviewer_result,
            risk=risk_result,
        )
        final_out = {
            "event_id": event_id,
            "title": str(event_pack.get("title") or ""),
            "hard_gate_passed": hard_gate_passed,
            "writer_ok": writer_ok,
            "review_decision": str(reviewer_result.get("review_decision") or ""),
            "risk_decision": str(risk_result.get("risk_decision") or ""),
            "x_taste_score": _safe_int(reviewer_result.get("x_taste_score"), 0),
            "human_taste_score": _safe_int(reviewer_result.get("human_taste_score"), 0),
            "ai_taste_risk": str(reviewer_result.get("ai_taste_risk") or ""),
            "boring_risk": str(reviewer_result.get("boring_risk") or ""),
            "risk_level": str(risk_result.get("risk_level") or ""),
            "final": final,
        }
        _write_json(out_dir / "x_final_decision.json", final_out)
        (out_dir / "x_review_packet.md").write_text(
            _render_packet_md(
                event_pack=event_pack,
                writer=writer_result,
                reviewer=reviewer_result,
                risk=risk_result,
                final=final_out,
            ),
            encoding="utf-8",
        )

        rows_for_summary.append(
            {
                "event_id": event_id,
                "title": str(event_pack.get("title") or ""),
                "final_status": str(final.get("status") or ""),
                "writer": writer_result,
                "reviewer": reviewer_result,
                "risk": risk_result,
                "final": final_out,
            }
        )

    counts: dict[str, int] = {
        "approved_for_x_dryrun": len([x for x in rows_for_summary if x.get("final_status") == "APPROVED_FOR_X_DRYRUN"]),
        "need_rewrite": len([x for x in rows_for_summary if x.get("final_status") == "NEED_REWRITE"]),
        "blocked_by_risk": len([x for x in rows_for_summary if x.get("final_status") == "BLOCKED_BY_RISK"]),
        "rejected_by_reviewer": len([x for x in rows_for_summary if x.get("final_status") == "REJECTED_BY_REVIEWER"]),
        "blocked_hard_gate": len([x for x in rows_for_summary if x.get("final_status") == "BLOCKED_HARD_GATE"]),
    }

    best = None
    approved_rows = [x for x in rows_for_summary if x.get("final_status") == "APPROVED_FOR_X_DRYRUN"]
    if approved_rows:
        best = max(approved_rows, key=lambda r: _safe_int((r.get("reviewer") or {}).get("x_taste_score"), 0))

    report = {
        "task_id": "x_v2_003_ai_personal_reply_generation_review",
        "generated_at_utc": _utc_now_iso(),
        "status": "DONE",
        "key_loading": {
            "env_key_detected": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
            "local_secret_detected": bool(load_openrouter_api_key()) and not bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
        },
        "model": model,
        "model_calls_made": model_calls,
        "generated_events": len(rows_for_summary),
        "counts": counts,
        "best_output": {
            "best_event": (best or {}).get("event_id") if best else "",
            "personal_post": ((best or {}).get("writer") or {}).get("personal_post") if best else "",
            "reply_angle_aggressive": (((best or {}).get("writer") or {}).get("reply_angle") or {}).get("aggressive") if best else "",
            "reply_angle_sarcastic": (((best or {}).get("writer") or {}).get("reply_angle") or {}).get("sarcastic") if best else "",
            "reply_angle_og_explainer": (((best or {}).get("writer") or {}).get("reply_angle") or {}).get("og_explainer") if best else "",
            "x_taste_score": _safe_int(((best or {}).get("reviewer") or {}).get("x_taste_score"), 0) if best else 0,
            "risk_level": ((best or {}).get("risk") or {}).get("risk_level") if best else "",
        },
        "out_dir": str(out_root),
        "results_index": rows_for_summary,
        "safety": {
            "trae_self_scoring": False,
            "ai_reviewer_used": True,
            "ai_risk_auditor_used": True,
            "x_published": False,
            "x_api_connected": False,
            "article_project_modified": False,
            "production_write": False,
            "daemon_started": False,
            "credential_exposed": False,
        },
    }
    _write_json(reports_dir / "x_v2_003_ai_content_review_report.json", report)

    md_lines: list[str] = []
    md_lines.append("# X v2-003 AI Content Review Report\n\n")
    md_lines.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md_lines.append(f"- status: {report.get('status')}\n")
    md_lines.append(f"- model_calls_made: {report.get('model_calls_made')}\n")
    md_lines.append(f"- generated_events: {report.get('generated_events')}\n")
    md_lines.append(
        f"- approved_for_x_dryrun: {counts.get('approved_for_x_dryrun')}\n"
        f"- need_rewrite: {counts.get('need_rewrite')}\n"
        f"- blocked_by_risk: {counts.get('blocked_by_risk')}\n"
        f"- rejected_by_reviewer: {counts.get('rejected_by_reviewer')}\n"
    )
    if best:
        md_lines.append("\n## Best Output\n\n")
        md_lines.append(f"- best_event: {report['best_output']['best_event']}\n")
        md_lines.append(f"- x_taste_score: {report['best_output']['x_taste_score']}\n")
        md_lines.append(f"- risk_level: {report['best_output']['risk_level']}\n")
        md_lines.append("\nPersonal Post:\n\n")
        md_lines.append(str(report["best_output"]["personal_post"]).strip() + "\n")

    (reports_dir / "x_v2_003_ai_content_review_report.md").write_text("".join(md_lines), encoding="utf-8")

    groups: dict[str, list[dict[str, Any]]] = {
        "APPROVED_FOR_X_DRYRUN": [],
        "NEED_REWRITE": [],
        "BLOCKED_BY_RISK": [],
        "REJECTED_BY_REVIEWER": [],
    }
    for r in rows_for_summary:
        st = str(r.get("final_status") or "")
        if st in groups:
            groups[st].append(r)
        elif st == "APPROVED_FOR_X_DRYRUN":
            groups["APPROVED_FOR_X_DRYRUN"].append(r)
        else:
            groups["NEED_REWRITE"].append(r)

    _write_summary_md(out_root, groups)


if __name__ == "__main__":
    main()

