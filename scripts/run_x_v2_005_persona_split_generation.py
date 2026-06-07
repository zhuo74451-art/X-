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


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _load_prompt(root: Path, rel: str) -> str:
    return _read_text(root / rel)


def _load_event_pack(root: Path, event_id: str) -> dict[str, Any]:
    v3_req = root / "out" / "x_review_pack_v003" / event_id / "writer_request.json"
    if v3_req.exists():
        d = _read_json(v3_req)
        ep = d.get("input_event_pack")
        if isinstance(ep, dict) and ep:
            return ep

    v2_event = root / "out" / "x_review_pack_v002" / event_id / "event.json"
    if v2_event.exists():
        ev = _read_json(v2_event)
        return {
            "event_id": str(ev.get("input_id") or event_id),
            "title": str(ev.get("title") or ""),
            "summary": str(ev.get("summary") or ""),
            "event_type": str(ev.get("event_type") or ""),
            "assets": ev.get("asset_symbols") if isinstance(ev.get("asset_symbols"), list) else [],
            "source_pack": ev.get("source_pack") if isinstance(ev.get("source_pack"), list) else [],
            "fact_pack": ev.get("fact_pack") if isinstance(ev.get("fact_pack"), dict) else {},
            "risk_flags": ev.get("risk_flags") if isinstance(ev.get("risk_flags"), list) else [],
            "image_candidates": ev.get("image_candidates") if isinstance(ev.get("image_candidates"), list) else [],
            "recommended_outputs": ev.get("recommended_outputs") if isinstance(ev.get("recommended_outputs"), list) else [],
            "review_required": True,
        }
    return {"event_id": event_id}


def _load_v4_context(root: Path, event_id: str) -> dict[str, Any]:
    v4_dir = root / "out" / "x_review_pack_v004" / event_id
    v3_dir = root / "out" / "x_review_pack_v003" / event_id
    ctx: dict[str, Any] = {}
    if (v4_dir / "rewriter_result.json").exists():
        ctx["v4_rewriter_result"] = _read_json(v4_dir / "rewriter_result.json")
    if (v4_dir / "ai_reviewer_result.json").exists():
        ctx["v4_reviewer_result"] = _read_json(v4_dir / "ai_reviewer_result.json")
    if (v4_dir / "ai_risk_result.json").exists():
        ctx["v4_risk_result"] = _read_json(v4_dir / "ai_risk_result.json")
    if (v3_dir / "writer_result.json").exists():
        ctx["v3_writer_result"] = _read_json(v3_dir / "writer_result.json")
    if (v3_dir / "ai_reviewer_result.json").exists():
        ctx["v3_reviewer_result"] = _read_json(v3_dir / "ai_reviewer_result.json")
    if (v3_dir / "ai_risk_result.json").exists():
        ctx["v3_risk_result"] = _read_json(v3_dir / "ai_risk_result.json")
    return ctx


def _route_for_event(event_id: str) -> dict[str, Any]:
    if event_id == "evt_case_001":
        return {
            "route": "DOWNGRADE_TO_ARTICLE_OR_NEWS",
            "reason": "regulatory/compliance content is better suited to article/news format",
            "personas": [],
        }
    if event_id == "evt_whale_001":
        return {"route": "X_PERSONA_GENERATION", "personas": ["personal_sharp", "reply_hot_take"]}
    if event_id == "evt_hot_001":
        return {"route": "X_PERSONA_GENERATION", "personas": ["personal_balanced", "reply_hot_take"]}
    if event_id == "evt_industry_001":
        return {"route": "X_PERSONA_GENERATION", "personas": ["personal_sharp", "personal_balanced", "reply_hot_take"]}
    return {"route": "X_PERSONA_GENERATION", "personas": ["personal_balanced", "reply_hot_take"]}


def _build_persona_system_prompt(
    *,
    sharp: str,
    balanced: str,
    reply: str,
    personas: list[str],
) -> str:
    parts: list[str] = []
    parts.append("你只输出 JSON，不要解释文字，不要 markdown，不要代码块。\n")
    if "personal_sharp" in personas:
        parts.append("\n" + sharp.strip() + "\n")
    if "personal_balanced" in personas:
        parts.append("\n" + balanced.strip() + "\n")
    if "reply_hot_take" in personas:
        parts.append("\n" + reply.strip() + "\n")
    parts.append(
        "\n统一输出 schema（缺失的 persona 字段输出空字符串或空对象）：\n"
        "{\n"
        '  "event_id": "",\n'
        '  "route": "X_PERSONA_GENERATION",\n'
        '  "personal_sharp": "",\n'
        '  "personal_balanced": "",\n'
        '  "reply_hot_take": {\n'
        '    "sarcastic": "",\n'
        '    "sharp_but_safe": "",\n'
        '    "og_explainer": ""\n'
        "  },\n"
        '  "used_facts": [],\n'
        '  "should_not_claim": [],\n'
        '  "persona_notes": ""\n'
        "}\n"
    )
    return "\n".join(parts).strip() + "\n"


def _persona_user_prompt(payload: dict[str, Any]) -> str:
    return (
        "input:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\n"
        + "只能基于 input，不得编造。只输出 JSON。\n"
    )


def _review_user_prompt(event_pack: dict[str, Any], writer_for_review: dict[str, Any]) -> str:
    return (
        "input_event_pack:\n"
        + json.dumps(event_pack, ensure_ascii=False)
        + "\n\n"
        + "writer_result:\n"
        + json.dumps(writer_for_review, ensure_ascii=False)
        + "\n\n"
        + "只输出 JSON。\n"
    )


def _writer_for_review(persona: dict[str, Any], primary: str) -> dict[str, Any]:
    reply = persona.get("reply_hot_take") if isinstance(persona.get("reply_hot_take"), dict) else {}
    return {
        "event_id": str(persona.get("event_id") or ""),
        "personal_post": primary,
        "reply_angle": {
            "aggressive": str(reply.get("sharp_but_safe") or ""),
            "sarcastic": str(reply.get("sarcastic") or ""),
            "og_explainer": str(reply.get("og_explainer") or ""),
        },
    }


def _pick_primary_post(persona: dict[str, Any], personas: list[str]) -> str:
    if "personal_sharp" in personas:
        v = str(persona.get("personal_sharp") or "").strip()
        if v:
            return v
    v = str(persona.get("personal_balanced") or "").strip()
    return v


def _final_status(reviewer: dict[str, Any], risk: dict[str, Any], writer_ok: bool) -> tuple[str, list[str]]:
    if not writer_ok:
        return "NEED_REWRITE", ["writer_invalid_or_empty"]

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
    return "NEED_REWRITE", reasons


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if not load_openrouter_api_key():
        report = {
            "task_id": "x_v2_005_persona_split_test_dryrun",
            "generated_at_utc": _utc_now_iso(),
            "status": "BLOCKED_MISSING_OPENROUTER_KEY",
            "blocked_reason": "BLOCKED_MISSING_OPENROUTER_KEY",
            "model_calls_made": 0,
        }
        _write_json(reports_dir / "x_v2_005_persona_split_report.json", report)
        (reports_dir / "x_v2_005_persona_split_report.md").write_text(
            "# X v2-005 Persona Split Report\n\n- status: blocked\n- blocked_reason: BLOCKED_MISSING_OPENROUTER_KEY\n",
            encoding="utf-8",
        )
        raise SystemExit(2)

    os.environ["MODEL_RUNTIME"] = "openrouter"
    if not (os.getenv("OPENROUTER_MODEL") or "").strip():
        os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"
    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    v4_final_path = reports_dir / "x_v2_004_final_dryrun_candidates.json"
    if not v4_final_path.exists():
        raise SystemExit(2)
    v4_final = _read_json(v4_final_path)

    sharp_prompt = _load_prompt(root, "prompts/x_persona_personal_sharp_v005.md")
    balanced_prompt = _load_prompt(root, "prompts/x_persona_personal_balanced_v005.md")
    reply_prompt = _load_prompt(root, "prompts/x_persona_reply_hot_take_v005.md")
    reviewer_prompt = _load_prompt(root, "prompts/x_ai_reviewer_v003.md")
    risk_prompt = _load_prompt(root, "prompts/x_ai_risk_auditor_v003.md")

    out_root = root / "out" / "x_review_pack_v005"
    out_root.mkdir(parents=True, exist_ok=True)

    event_ids = ["evt_whale_001", "evt_hot_001", "evt_industry_001", "evt_case_001"]
    model_calls = 0

    items: list[dict[str, Any]] = []

    for event_id in event_ids:
        route = _route_for_event(event_id)
        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        if route.get("route") == "DOWNGRADE_TO_ARTICLE_OR_NEWS":
            persona = {
                "event_id": event_id,
                "route": "DOWNGRADE_TO_ARTICLE_OR_NEWS",
                "reason": str(route.get("reason") or ""),
            }
            _write_json(out_dir / "persona_writer_result.json", persona)
            items.append(
                {
                    "event_id": event_id,
                    "route": persona["route"],
                    "status": "DOWNGRADE_TO_ARTICLE_OR_NEWS",
                    "reason": persona["reason"],
                }
            )
            continue

        personas = route.get("personas") if isinstance(route.get("personas"), list) else []
        system_prompt = _build_persona_system_prompt(
            sharp=sharp_prompt,
            balanced=balanced_prompt,
            reply=reply_prompt,
            personas=personas,
        )

        event_pack = _load_event_pack(root, event_id)
        ctx = _load_v4_context(root, event_id)
        payload = {"event_pack": event_pack, "route": route, "context": ctx}

        writer_req = {
            "task_type": "x_persona_split_writer_v005",
            "runtime": "openrouter",
            "model": model,
            "temperature": 0.6,
            "max_tokens": 1000,
            "event_id": event_id,
            "route": route,
        }
        _write_json(out_dir / "persona_writer_request.json", writer_req)

        writer_raw: dict[str, Any] = {}
        persona_result: dict[str, Any] = {"event_id": event_id, "route": "X_PERSONA_GENERATION"}

        if model_calls + 1 > 9:
            persona_result = {"event_id": event_id, "route": "X_PERSONA_GENERATION", "error": "model_call_budget_exceeded"}
        else:
            wr = call_llm_task(
                task_type="x_persona_split_writer_v005",
                system_prompt=system_prompt,
                user_prompt=_persona_user_prompt(payload),
                expect_json=True,
                temperature=0.6,
                max_tokens=1000,
            )
            model_calls += 1
            writer_raw = wr
            if wr.get("ok") is True and isinstance(wr.get("json"), dict):
                persona_result = wr["json"]
            else:
                persona_result = {"event_id": event_id, "route": "X_PERSONA_GENERATION", "error": wr.get("error") or "writer_failed"}

        if "event_id" not in persona_result:
            persona_result["event_id"] = event_id
        if "route" not in persona_result:
            persona_result["route"] = "X_PERSONA_GENERATION"

        _write_json(out_dir / "persona_writer_response_raw.json", writer_raw)
        _write_json(out_dir / "persona_writer_result.json", persona_result)

        primary_post = _pick_primary_post(persona_result, personas)
        writer_ok = bool(primary_post.strip()) and isinstance(persona_result.get("reply_hot_take"), dict)
        writer_for_review = _writer_for_review(persona_result, primary_post)

        reviewer_raw: dict[str, Any] = {}
        reviewer_result: dict[str, Any] = {"event_id": event_id, "review_decision": "NEED_REWRITE"}
        if model_calls + 1 <= 9:
            rr = call_llm_task(
                task_type="x_ai_reviewer_v003",
                system_prompt=reviewer_prompt,
                user_prompt=_review_user_prompt(event_pack, writer_for_review),
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

        risk_raw: dict[str, Any] = {}
        risk_result: dict[str, Any] = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium"}
        if model_calls + 1 <= 9:
            rk = call_llm_task(
                task_type="x_ai_risk_auditor_v003",
                system_prompt=risk_prompt,
                user_prompt=_review_user_prompt(event_pack, writer_for_review),
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

        status, reasons = _final_status(reviewer_result, risk_result, writer_ok)
        final = {
            "event_id": event_id,
            "route": "X_PERSONA_GENERATION",
            "personas": personas,
            "primary_persona": "personal_sharp" if "personal_sharp" in personas else "personal_balanced",
            "status": status,
            "reasons": reasons,
            "x_taste_score": _safe_int(reviewer_result.get("x_taste_score"), 0),
            "human_taste_score": _safe_int(reviewer_result.get("human_taste_score"), 0),
            "risk_level": str(risk_result.get("risk_level") or ""),
            "reviewer_decision": str(reviewer_result.get("review_decision") or ""),
            "risk_decision": str(risk_result.get("risk_decision") or ""),
        }
        _write_json(out_dir / "x_final_decision.json", final)

        md: list[str] = []
        md.append("# X Review Packet v005\n\n")
        md.append(f"- generated_at_utc: {_utc_now_iso()}\n")
        md.append(f"- event_id: {event_id}\n")
        md.append(f"- route: X_PERSONA_GENERATION\n")
        md.append(f"- final_status: {status}\n\n")
        md.append("## Primary Post\n\n")
        md.append(primary_post.strip() + "\n\n")
        rh = persona_result.get("reply_hot_take") if isinstance(persona_result.get("reply_hot_take"), dict) else {}
        md.append("## Reply Hot Take\n\n")
        md.append("Sarcastic：\n" + str(rh.get("sarcastic") or "").strip() + "\n\n")
        md.append("Sharp But Safe：\n" + str(rh.get("sharp_but_safe") or "").strip() + "\n\n")
        md.append("OG Explainer：\n" + str(rh.get("og_explainer") or "").strip() + "\n\n")
        md.append("## AI Review\n\n")
        md.append(f"- decision: {final.get('reviewer_decision')}\n")
        md.append(f"- x_taste_score: {final.get('x_taste_score')}\n")
        md.append(f"- human_taste_score: {final.get('human_taste_score')}\n\n")
        md.append("## Risk\n\n")
        md.append(f"- decision: {final.get('risk_decision')}\n")
        md.append(f"- risk_level: {final.get('risk_level')}\n")
        (out_dir / "x_review_packet.md").write_text("".join(md), encoding="utf-8")

        items.append(
            {
                "event_id": event_id,
                "route": "X_PERSONA_GENERATION",
                "personas": personas,
                "persona_writer_result": persona_result,
                "reviewer_result": reviewer_result,
                "risk_result": risk_result,
                "final": final,
            }
        )

    active = [x for x in items if x.get("route") == "X_PERSONA_GENERATION"]
    downgraded = [x for x in items if x.get("route") == "DOWNGRADE_TO_ARTICLE_OR_NEWS"]
    approved = [x for x in active if (x.get("final") or {}).get("status") == "APPROVED_FOR_X_DRYRUN"]
    need_rw = [x for x in active if (x.get("final") or {}).get("status") == "NEED_REWRITE"]
    blocked = [x for x in active if (x.get("final") or {}).get("status") == "BLOCKED_BY_RISK"]

    report = {
        "task_id": "x_v2_005_persona_split_test_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "status": "DONE",
        "model": model,
        "model_calls_made": model_calls,
        "active_events": len(active),
        "downgraded_events": len(downgraded),
        "counts": {
            "final_approved_count": len(approved),
            "need_rewrite_count": len(need_rw),
            "blocked_by_risk": len(blocked),
        },
        "items": items,
        "safety": {"x_published": False, "x_api_connected": False, "production_write": False, "daemon_started": False},
    }
    _write_json(reports_dir / "x_v2_005_persona_split_report.json", report)

    md: list[str] = []
    md.append("# X v2-005 Persona Split Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- model: {report.get('model')}\n")
    md.append(f"- model_calls_made: {report.get('model_calls_made')}\n")
    md.append(f"- active_events: {report.get('active_events')}\n")
    md.append(f"- downgraded_events: {report.get('downgraded_events')}\n")
    md.append(f"- final_approved_count: {report['counts']['final_approved_count']}\n")
    md.append(f"- need_rewrite_count: {report['counts']['need_rewrite_count']}\n")
    md.append(f"- blocked_by_risk: {report['counts']['blocked_by_risk']}\n")
    (reports_dir / "x_v2_005_persona_split_report.md").write_text("".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()

