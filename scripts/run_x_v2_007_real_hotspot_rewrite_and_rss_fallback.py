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


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except Exception:
        return {}


def _read_jsonl_index_by_event_id(path: Path) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return idx
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = (line or "").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            eid = str(obj.get("event_id") or "").strip()
            if eid:
                idx[eid] = obj
    return idx


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _extract_source_url(event_pack: dict[str, Any]) -> str:
    u = str(event_pack.get("source_url") or "").strip()
    if u:
        return u
    sp = event_pack.get("source_pack")
    if isinstance(sp, list) and sp:
        u2 = str((sp[0] or {}).get("url") or "").strip() if isinstance(sp[0], dict) else ""
        if u2:
            return u2
    return ""


def _persona_writer_for_review(rewrite: dict[str, Any], event_id: str) -> dict[str, Any]:
    rh = rewrite.get("reply_hot_take") if isinstance(rewrite.get("reply_hot_take"), dict) else {}
    return {
        "event_id": event_id,
        "personal_post": str(rewrite.get("post") or "").strip(),
        "reply_angle": {
            "aggressive": str(rh.get("sharp_but_safe") or "").strip(),
            "sarcastic": str(rh.get("sarcastic") or "").strip(),
            "og_explainer": str(rh.get("og_explainer") or "").strip(),
        },
    }


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


def _rewrite_user_prompt(payload: dict[str, Any]) -> str:
    return "input:\n" + json.dumps(payload, ensure_ascii=False) + "\n\n只能基于 input，不得编造。只输出 JSON。\n"


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
        raise SystemExit(2)

    os.environ["MODEL_RUNTIME"] = "openrouter"
    if not (os.getenv("OPENROUTER_MODEL") or "").strip():
        os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"
    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    queue_path = reports_dir / "x_v2_006_test_account_queue.json"
    v6_report_path = reports_dir / "x_v2_006_real_event_persona_dryrun_report.json"
    if not queue_path.exists() or not v6_report_path.exists():
        raise SystemExit(2)

    queue = _read_json(queue_path)
    v6 = _read_json(v6_report_path)

    need_rewrite = queue.get("need_rewrite") if isinstance(queue.get("need_rewrite"), list) else []
    targets = []
    for it in need_rewrite:
        if not isinstance(it, dict):
            continue
        eid = str(it.get("event_id") or "").strip()
        if eid:
            targets.append(it)
    targets = targets[:3]

    event_index = _read_jsonl_index_by_event_id(root / "data" / "real_event_pack_v006.jsonl")

    rewriter_prompt = _read_text(root / "prompts" / "x_persona_rewriter_v007.md")
    reviewer_prompt = _read_text(root / "prompts" / "x_ai_reviewer_v003.md")
    risk_prompt = _read_text(root / "prompts" / "x_ai_risk_auditor_v003.md")

    out_root = root / "out" / "x_review_pack_v007"
    out_root.mkdir(parents=True, exist_ok=True)

    model_calls = 0
    rewritten: list[dict[str, Any]] = []

    for t in targets:
        event_id = str(t.get("event_id") or "").strip()
        reason = str(t.get("reason") or "").strip()
        event_pack = event_index.get(event_id) or {}

        v6_dir = root / "out" / "x_review_pack_v006" / event_id
        persona_v6 = _read_json_if_exists(v6_dir / "persona_writer_result.json")
        reviewer_v6 = _read_json_if_exists(v6_dir / "ai_reviewer_result.json")
        risk_v6 = _read_json_if_exists(v6_dir / "ai_risk_result.json")

        post = ""
        if isinstance(persona_v6, dict):
            post = str(persona_v6.get("personal_sharp") or persona_v6.get("personal_balanced") or "").strip()
        reply = persona_v6.get("reply_hot_take") if isinstance(persona_v6.get("reply_hot_take"), dict) else {}

        payload = {
            "event_pack": event_pack,
            "persona_output_v006": {
                "post": post,
                "reply_hot_take": {
                    "sarcastic": str(reply.get("sarcastic") or "").strip(),
                    "sharp_but_safe": str(reply.get("sharp_but_safe") or "").strip(),
                    "og_explainer": str(reply.get("og_explainer") or "").strip(),
                },
            },
            "reviewer_result_v006": reviewer_v6,
            "risk_result_v006": risk_v6,
            "rewrite_reason": reason,
        }

        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        _write_json(
            out_dir / "rewriter_request.json",
            {"task_type": "x_persona_rewriter_v007", "runtime": "openrouter", "model": model, "event_id": event_id},
        )

        rr = _read_json_if_exists(out_dir / "rewriter_response_raw.json")
        rewrite = _read_json_if_exists(out_dir / "rewriter_result.json")
        if not rewrite:
            rr = call_llm_task(
                task_type="x_persona_rewriter_v007",
                system_prompt=rewriter_prompt,
                user_prompt=_rewrite_user_prompt(payload),
                expect_json=True,
                temperature=0.6,
                max_tokens=1000,
            )
            model_calls += 1
            _write_json(out_dir / "rewriter_response_raw.json", rr)
            rewrite = (
                rr.get("json")
                if rr.get("ok") is True and isinstance(rr.get("json"), dict)
                else {"event_id": event_id, "error": rr.get("error") or "rewriter_failed"}
            )
            if "event_id" not in rewrite:
                rewrite["event_id"] = event_id
            _write_json(out_dir / "rewriter_result.json", rewrite)

        writer_for_review = _persona_writer_for_review(rewrite, event_id)
        writer_ok = bool(str(writer_for_review.get("personal_post") or "").strip())

        rv_raw = _read_json_if_exists(out_dir / "ai_reviewer_response_raw.json")
        reviewer = _read_json_if_exists(out_dir / "ai_reviewer_result.json")
        if not reviewer:
            rv_raw = call_llm_task(
                task_type="x_ai_reviewer_v003",
                system_prompt=reviewer_prompt,
                user_prompt=_review_user_prompt(event_pack, writer_for_review),
                expect_json=True,
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            _write_json(out_dir / "ai_reviewer_response_raw.json", rv_raw)
            reviewer = (
                rv_raw.get("json")
                if rv_raw.get("ok") is True and isinstance(rv_raw.get("json"), dict)
                else {"event_id": event_id, "review_decision": "NEED_REWRITE"}
            )
            if "event_id" not in reviewer:
                reviewer["event_id"] = event_id
            _write_json(out_dir / "ai_reviewer_result.json", reviewer)

        rk_raw = _read_json_if_exists(out_dir / "ai_risk_response_raw.json")
        risk = _read_json_if_exists(out_dir / "ai_risk_result.json")
        if not risk:
            rk_raw = call_llm_task(
                task_type="x_ai_risk_auditor_v003",
                system_prompt=risk_prompt,
                user_prompt=_review_user_prompt(event_pack, writer_for_review),
                expect_json=True,
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            _write_json(out_dir / "ai_risk_response_raw.json", rk_raw)
            risk = (
                rk_raw.get("json")
                if rk_raw.get("ok") is True and isinstance(rk_raw.get("json"), dict)
                else {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium"}
            )
            if "event_id" not in risk:
                risk["event_id"] = event_id
            _write_json(out_dir / "ai_risk_result.json", risk)

        status, reasons = _final_status(reviewer, risk, writer_ok)
        source_url = _extract_source_url(event_pack)
        final = {
            "event_id": event_id,
            "status": status,
            "reasons": reasons,
            "score": _safe_int(reviewer.get("x_taste_score"), 0),
            "threshold": 80,
            "decision": str(reviewer.get("review_decision") or ""),
            "human_taste_score": _safe_int(reviewer.get("human_taste_score"), 0),
            "risk_level": str(risk.get("risk_level") or ""),
            "risk_decision": str(risk.get("risk_decision") or ""),
            "source_mode": str((event_pack.get("source_mode") or "")),
            "observed_at": str((event_pack.get("observed_at") or "")),
            "title": str((event_pack.get("title") or "")),
            "source_url": source_url,
        }
        _write_json(out_dir / "x_final_decision.json", final)

        md: list[str] = []
        md.append("# X Review Packet v007\n\n")
        md.append(f"- generated_at_utc: {_utc_now_iso()}\n")
        md.append(f"- event_id: {event_id}\n")
        md.append(f"- source_mode: {final.get('source_mode')}\n")
        md.append(f"- observed_at: {final.get('observed_at')}\n")
        md.append(f"- final_status: {final.get('status')}\n\n")
        md.append("## Post\n\n")
        md.append(str(rewrite.get("post") or "").strip() + "\n\n")
        rh = rewrite.get("reply_hot_take") if isinstance(rewrite.get("reply_hot_take"), dict) else {}
        md.append("## Reply Hot Take\n\n")
        md.append("Sarcastic：\n" + str(rh.get("sarcastic") or "").strip() + "\n\n")
        md.append("Sharp But Safe：\n" + str(rh.get("sharp_but_safe") or "").strip() + "\n\n")
        md.append("OG Explainer：\n" + str(rh.get("og_explainer") or "").strip() + "\n\n")
        md.append("## AI Review\n\n")
        md.append(f"- score: {final.get('score')}\n")
        md.append(f"- threshold: {final.get('threshold')}\n")
        md.append(f"- decision: {final.get('decision')}\n")
        md.append(f"- human_taste_score: {final.get('human_taste_score')}\n\n")
        md.append("## Risk\n\n")
        md.append(f"- risk_level: {final.get('risk_level')}\n")
        md.append(f"- risk_decision: {final.get('risk_decision')}\n")
        (out_dir / "x_review_packet.md").write_text("".join(md), encoding="utf-8")

        rewritten.append(
            {
                "event_id": event_id,
                "title": final.get("title"),
                "source_mode": final.get("source_mode"),
                "observed_at": final.get("observed_at"),
                "rewrite_reason": reason,
                "final": final,
                "rewriter_result": rewrite,
                "reviewer_result": reviewer,
                "risk_result": risk,
            }
        )

    rewrite_approved = [x for x in rewritten if (x.get("final") or {}).get("status") == "APPROVED_FOR_X_DRYRUN"]

    report = {
        "task_id": "x_v2_007_real_hotspot_rewrite_and_rss_fallback",
        "generated_at_utc": _utc_now_iso(),
        "model": model,
        "model_calls_made": model_calls,
        "rewritten_count": len(rewritten),
        "rewrite_approved_count": len(rewrite_approved),
        "items": rewritten,
        "safety": {"x_published": False, "x_api_connected": False},
    }
    _write_json(reports_dir / "x_v2_007_real_hotspot_rewrite_report.json", report)

    md: list[str] = []
    md.append("# X v2-007 Real Hotspot Rewrite Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- model: {report.get('model')}\n")
    md.append(f"- model_calls_made: {report.get('model_calls_made')}\n")
    md.append(f"- rewritten_count: {report.get('rewritten_count')}\n")
    md.append(f"- rewrite_approved_count: {report.get('rewrite_approved_count')}\n\n")
    for it in rewritten:
        fin = it.get("final") if isinstance(it.get("final"), dict) else {}
        md.append("---\n\n")
        md.append(f"## {it.get('event_id')} | {fin.get('status')}\n\n")
        md.append(f"- title: {it.get('title')}\n")
        md.append(f"- source_mode: {it.get('source_mode')}\n")
        md.append(f"- observed_at: {it.get('observed_at')}\n")
        md.append(f"- rewrite_reason: {it.get('rewrite_reason')}\n")
        md.append(f"- score: {fin.get('score')}\n")
        md.append(f"- threshold: {fin.get('threshold')}\n")
        md.append(f"- decision: {fin.get('decision')}\n")
        md.append(f"- risk_level: {fin.get('risk_level')}\n")
        md.append(f"- risk_decision: {fin.get('risk_decision')}\n\n")
    (reports_dir / "x_v2_007_real_hotspot_rewrite_report.md").write_text("".join(md), encoding="utf-8")

    queue_ready = queue.get("ready") if isinstance(queue.get("ready"), list) else []
    base_ready = [x for x in queue_ready if isinstance(x, dict)]
    for r in base_ready:
        eid = str(r.get("event_id") or "").strip()
        ep = event_index.get(eid) or {}
        if ep:
            if not r.get("title"):
                r["title"] = str(ep.get("title") or "")
            if not r.get("observed_at"):
                r["observed_at"] = str(ep.get("observed_at") or "")
            if not r.get("source_mode"):
                r["source_mode"] = str(ep.get("source_mode") or "")
            r.setdefault("source_url", _extract_source_url(ep))

    ready_from_rewrite = []
    need_rewrite_out = []
    blocked_by_risk_out = []
    for x in rewritten:
        fin = x.get("final") if isinstance(x.get("final"), dict) else {}
        status = str(fin.get("status") or "NEED_REWRITE")
        rh = x.get("rewriter_result") if isinstance(x.get("rewriter_result"), dict) else {}
        reply = rh.get("reply_hot_take") if isinstance(rh.get("reply_hot_take"), dict) else {}
        row = {
            "event_id": x.get("event_id"),
            "title": x.get("title"),
            "source_mode": x.get("source_mode"),
            "observed_at": x.get("observed_at"),
            "source_url": str(fin.get("source_url") or ""),
            "persona": "rewritten_v007",
            "post": str(rh.get("post") or "").strip(),
            "reply_hot_take": {
                "sarcastic": str(reply.get("sarcastic") or "").strip(),
                "sharp_but_safe": str(reply.get("sharp_but_safe") or "").strip(),
                "og_explainer": str(reply.get("og_explainer") or "").strip(),
            },
            "score": _safe_int(fin.get("score"), 0),
            "threshold": 80,
            "decision": str(fin.get("decision") or ""),
            "risk_level": str(fin.get("risk_level") or ""),
            "recommended_publish_mode": "manual_test_account_only",
            "publish_status": "not_published",
        }
        if status == "APPROVED_FOR_X_DRYRUN":
            ready_from_rewrite.append(row)
        elif status == "BLOCKED_BY_RISK":
            blocked_by_risk_out.append({"event_id": x.get("event_id"), "reason": ";".join(fin.get("reasons") or [])})
        else:
            need_rewrite_out.append({"event_id": x.get("event_id"), "reason": ";".join(fin.get("reasons") or [])})

    final_queue = {
        "task_id": "x_v2_007_real_hotspot_rewrite_and_rss_fallback",
        "generated_at_utc": _utc_now_iso(),
        "ready": base_ready + ready_from_rewrite,
        "need_rewrite": need_rewrite_out,
        "downgrade_to_article_news": queue.get("downgrade_to_article_news") if isinstance(queue.get("downgrade_to_article_news"), list) else [],
        "blocked_by_risk": blocked_by_risk_out,
        "safety": {"x_published": False, "x_api_connected": False},
    }
    _write_json(reports_dir / "x_v2_007_today_test_account_queue.json", final_queue)

    qmd: list[str] = []
    qmd.append("# X v2-007 Today Test Account Queue\n\n")
    qmd.append(f"- generated_at_utc: {final_queue.get('generated_at_utc')}\n\n")
    qmd.append("## Ready for test account manual draft\n\n")
    for r in final_queue["ready"]:
        qmd.append("---\n\n")
        qmd.append(f"- event_id: {r.get('event_id')}\n")
        qmd.append(f"- title: {r.get('title','')}\n")
        qmd.append(f"- source_mode: {r.get('source_mode')}\n")
        qmd.append(f"- observed_at: {r.get('observed_at')}\n")
        qmd.append(f"- persona: {r.get('persona')}\n")
        qmd.append(f"- score: {r.get('score')}\n")
        qmd.append(f"- threshold: {r.get('threshold')}\n")
        qmd.append(f"- risk_level: {r.get('risk_level')}\n")
        qmd.append(f"- recommended_publish_mode: {r.get('recommended_publish_mode')}\n")
        qmd.append(f"- publish_status: {r.get('publish_status')}\n\n")
        qmd.append("Post:\n\n")
        qmd.append(str(r.get("post") or "").strip() + "\n\n")
        rh = r.get("reply_hot_take") if isinstance(r.get("reply_hot_take"), dict) else {}
        qmd.append("Reply hot take:\n")
        qmd.append(f"- sarcastic: {str(rh.get('sarcastic') or '').strip()}\n")
        qmd.append(f"- sharp_but_safe: {str(rh.get('sharp_but_safe') or '').strip()}\n")
        qmd.append(f"- og_explainer: {str(rh.get('og_explainer') or '').strip()}\n\n")

    qmd.append("## Need rewrite\n\n")
    if not final_queue["need_rewrite"]:
        qmd.append("- (none)\n\n")
    else:
        for r in final_queue["need_rewrite"]:
            qmd.append(f"- {r.get('event_id')}: {r.get('reason')}\n")
        qmd.append("\n")

    qmd.append("## Downgrade to article/news\n\n")
    dg = final_queue.get("downgrade_to_article_news") if isinstance(final_queue.get("downgrade_to_article_news"), list) else []
    if not dg:
        qmd.append("- (none)\n\n")
    else:
        for r in dg:
            if isinstance(r, dict):
                qmd.append(f"- {r.get('event_id')}: {r.get('reason')}\n")
        qmd.append("\n")

    qmd.append("## Blocked by risk\n\n")
    if not final_queue["blocked_by_risk"]:
        qmd.append("- (none)\n")
    else:
        for r in final_queue["blocked_by_risk"]:
            qmd.append(f"- {r.get('event_id')}: {r.get('reason')}\n")
    (reports_dir / "x_v2_007_today_test_account_queue.md").write_text("".join(qmd), encoding="utf-8")


if __name__ == "__main__":
    main()
