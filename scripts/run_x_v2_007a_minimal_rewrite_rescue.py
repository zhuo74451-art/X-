#!/usr/bin/env python3
"""X v2-007a Minimal Rewrite Rescue — 从 v2-006 NEED_REWRITE 救回最多 2 条。

规则：
- 不接 X API、不真实发推、不拉 RSS、不启动 daemon
- 最多 2 条 rewrite、每条 1 writer + 1 reviewer + 1 risk
- model_calls <= 6、每次 timeout 60 秒
- 保留 v2-006 已 approved 内容
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _extract_source_url(event_pack: dict[str, Any]) -> tuple[str, bool]:
    """返回 (url, source_url_missing)"""
    u = str(event_pack.get("source_url") or "").strip()
    if u:
        return u, False
    sp = event_pack.get("source_pack")
    if isinstance(sp, list) and sp:
        u2 = str((sp[0] or {}).get("url") or "").strip() if isinstance(sp[0], dict) else ""
        if u2:
            return u2, False
    return "", True


# ── prompt builders ──────────────────────────────────────────────────────

def _rewrite_user_prompt(payload: dict[str, Any]) -> str:
    return "input:\n" + json.dumps(payload, ensure_ascii=False) + "\n\n只能基于 input，不得编造。只输出 JSON。\n"


def _review_user_prompt(event_pack: dict[str, Any], writer_for_review: dict[str, Any]) -> str:
    return (
        "input_event_pack:\n"
        + json.dumps(event_pack, ensure_ascii=False)
        + "\n\nwriter_result:\n"
        + json.dumps(writer_for_review, ensure_ascii=False)
        + "\n\n只输出 JSON。\n"
    )


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


# ── final status ─────────────────────────────────────────────────────────

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


# ── model call wrapper (with 60s timeout) ────────────────────────────────

def _call_with_timeout(task_type: str, system_prompt: str, user_prompt: str,
                       temperature: float, max_tokens: int) -> dict[str, Any]:
    """调用 llm_client.call_llm_task，强制 60 秒 timeout。"""
    from llm_client import call_llm_task

    # 强制 60s timeout
    os.environ["MODEL_TIMEOUT_SECONDS"] = "60"

    result = call_llm_task(
        task_type=task_type,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        expect_json=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if not result.get("ok") and "timeout" in str(result.get("error") or "").lower():
        result["_timeout"] = True
        result["_timeout_reason"] = "NEED_REWRITE_TIMEOUT"
    return result


# ── main ─────────────────────────────────────────────────────────────────

def main() -> int:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── check inputs ─────────────────────────────────────────────────
    v6_report_path = reports_dir / "x_v2_006_real_event_persona_dryrun_report.json"
    v6_queue_path = reports_dir / "x_v2_006_test_account_queue.json"
    event_pack_path = root / "data" / "real_event_pack_v006.jsonl"

    if not v6_report_path.exists():
        print(f"[ERROR] v2-006 report not found: {v6_report_path}", file=sys.stderr)
        return 2
    if not v6_queue_path.exists():
        print(f"[ERROR] v2-006 queue not found: {v6_queue_path}", file=sys.stderr)
        return 2

    # ── load prompts ─────────────────────────────────────────────────
    rewriter_prompt = _read_text(root / "prompts" / "x_persona_rewriter_v007.md")
    reviewer_prompt = _read_text(root / "prompts" / "x_ai_reviewer_v003.md")
    risk_prompt = _read_text(root / "prompts" / "x_ai_risk_auditor_v003.md")

    # ── load v2-006 data ─────────────────────────────────────────────
    v6_report = _read_json(v6_report_path)
    v6_queue = _read_json(v6_queue_path)

    v6_items = v6_report.get("items") if isinstance(v6_report.get("items"), list) else []

    # ── find NEED_REWRITE targets ────────────────────────────────────
    # 从 v2-006 items 中取 NEED_REWRITE、score < 80、非 high risk 的
    targets: list[dict[str, Any]] = []
    for item in v6_items:
        if not isinstance(item, dict):
            continue
        fin = item.get("final") if isinstance(item.get("final"), dict) else {}
        status = str(fin.get("status") or "").strip()
        score = _safe_int(fin.get("score"), 0)
        risk_level = str(fin.get("risk_level") or "").strip().lower()

        if status == "NEED_REWRITE" and score < 80 and risk_level != "high":
            targets.append({
                "event_id": str(item.get("event_id") or "").strip(),
                "title": str(fin.get("title") or item.get("title") or "").strip(),
                "source_mode": str(fin.get("source_mode") or item.get("source_mode") or "").strip(),
                "observed_at": str(fin.get("observed_at") or item.get("observed_at") or "").strip(),
                "source_url": str(fin.get("source_url") or item.get("source_url") or "").strip(),
                "score": score,
                "threshold": _safe_int(fin.get("threshold"), 80),
                "risk_level": str(fin.get("risk_level") or "").strip(),
            })

    # 最多 2 条
    targets = targets[:2]

    if not targets:
        print("[WARN] no NEED_REWRITE targets found, skipping rewrite", file=sys.stderr)
        targets = []

    print(f"[INFO] targets for rewrite: {len(targets)}")
    for t in targets:
        print(f"  - {t['event_id']}: {t['title'][:60]}... (score={t['score']})")

    # ── load event pack index ────────────────────────────────────────
    event_index: dict[str, dict[str, Any]] = {}
    if event_pack_path.exists():
        with event_pack_path.open("r", encoding="utf-8") as f:
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
                    event_index[eid] = obj

    # ── check model runtime ──────────────────────────────────────────
    from llm_client import load_openrouter_api_key
    api_key = load_openrouter_api_key()
    use_mock = not bool(api_key)

    if use_mock:
        print("[WARN] OPENROUTER_API_KEY not found — running in MOCK mode (no real model calls)")
        os.environ["MODEL_RUNTIME"] = "mock"
    else:
        print("[INFO] OPENROUTER_API_KEY found — running with OpenRouter")
        os.environ["MODEL_RUNTIME"] = "openrouter"
        if not (os.getenv("OPENROUTER_MODEL") or "").strip():
            os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"

    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    # ── output dir ───────────────────────────────────────────────────
    out_root = root / "out" / "x_review_pack_v007a"
    out_root.mkdir(parents=True, exist_ok=True)

    # ── run rewrites ─────────────────────────────────────────────────
    model_calls = 0
    max_model_calls = 6
    rewritten: list[dict[str, Any]] = []
    timeout_events: list[str] = []

    for t in targets:
        if model_calls >= max_model_calls:
            print(f"[WARN] model_calls reached max ({max_model_calls}), stopping rewrites")
            break

        event_id = t["event_id"]
        event_pack = event_index.get(event_id) or {}
        reason = f"x_taste_score<80;score={t['score']}"

        # 补充 event_pack 缺失的字段
        if not event_pack.get("title"):
            event_pack["title"] = t["title"]
        if not event_pack.get("source_url"):
            event_pack["source_url"] = t["source_url"]
        if not event_pack.get("observed_at"):
            event_pack["observed_at"] = t["observed_at"]
        if not event_pack.get("source_mode"):
            event_pack["source_mode"] = t["source_mode"]

        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[REWRITE] {event_id} — {t['title'][:80]}")

        # ── 1. writer ────────────────────────────────────────────
        v6_out_dir = root / "out" / "x_review_pack_v006" / event_id

        # 尝试读取 v2-006 的 persona 输出作为上下文
        persona_v6_path = v6_out_dir / "persona_writer_result.json"
        reviewer_v6_path = v6_out_dir / "ai_reviewer_result.json"
        risk_v6_path = v6_out_dir / "ai_risk_result.json"

        persona_v6: dict[str, Any] = {}
        reviewer_v6: dict[str, Any] = {}
        risk_v6: dict[str, Any] = {}
        if persona_v6_path.exists():
            try:
                persona_v6 = json.loads(persona_v6_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if reviewer_v6_path.exists():
            try:
                reviewer_v6 = json.loads(reviewer_v6_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if risk_v6_path.exists():
            try:
                risk_v6 = json.loads(risk_v6_path.read_text(encoding="utf-8"))
            except Exception:
                pass

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

        _write_json(out_dir / "rewriter_request.json", {
            "task_type": "x_persona_rewriter_v007",
            "runtime": "openrouter" if not use_mock else "mock",
            "model": model,
            "event_id": event_id,
        })

        if model_calls >= max_model_calls:
            rewrite = {"event_id": event_id, "error": "model_call_limit_reached"}
        else:
            rr = _call_with_timeout(
                task_type="x_persona_rewriter_v007",
                system_prompt=rewriter_prompt,
                user_prompt=_rewrite_user_prompt(payload),
                temperature=0.6,
                max_tokens=1000,
            )
            model_calls += 1
            _write_json(out_dir / "rewriter_response_raw.json", rr)

            if rr.get("_timeout"):
                timeout_events.append(event_id)
                rewrite = {"event_id": event_id, "error": "NEED_REWRITE_TIMEOUT", "timeout": True}
            elif rr.get("ok") is True and isinstance(rr.get("json"), dict):
                rewrite = rr["json"]
                if "event_id" not in rewrite:
                    rewrite["event_id"] = event_id
            else:
                rewrite = {"event_id": event_id, "error": rr.get("error") or "rewriter_failed"}

            _write_json(out_dir / "rewriter_result.json", rewrite)

        # ── 2. reviewer ──────────────────────────────────────────
        writer_for_review = _persona_writer_for_review(rewrite, event_id)
        writer_ok = bool(str(writer_for_review.get("personal_post") or "").strip())

        if model_calls >= max_model_calls:
            reviewer = {"event_id": event_id, "review_decision": "NEED_REWRITE"}
        else:
            rv_raw = _call_with_timeout(
                task_type="x_ai_reviewer_v003",
                system_prompt=reviewer_prompt,
                user_prompt=_review_user_prompt(event_pack, writer_for_review),
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            _write_json(out_dir / "ai_reviewer_response_raw.json", rv_raw)

            if rv_raw.get("_timeout"):
                timeout_events.append(event_id)
                reviewer = {"event_id": event_id, "review_decision": "NEED_REWRITE_TIMEOUT"}
            elif rv_raw.get("ok") is True and isinstance(rv_raw.get("json"), dict):
                reviewer = rv_raw["json"]
                if "event_id" not in reviewer:
                    reviewer["event_id"] = event_id
            else:
                reviewer = {"event_id": event_id, "review_decision": "NEED_REWRITE"}

            _write_json(out_dir / "ai_reviewer_result.json", reviewer)

        # ── 3. risk ──────────────────────────────────────────────
        if model_calls >= max_model_calls:
            risk = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium"}
        else:
            rk_raw = _call_with_timeout(
                task_type="x_ai_risk_auditor_v003",
                system_prompt=risk_prompt,
                user_prompt=_review_user_prompt(event_pack, writer_for_review),
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            _write_json(out_dir / "ai_risk_response_raw.json", rk_raw)

            if rk_raw.get("_timeout"):
                timeout_events.append(event_id)
                risk = {"event_id": event_id, "risk_decision": "NEED_REWRITE_TIMEOUT", "risk_level": "medium"}
            elif rk_raw.get("ok") is True and isinstance(rk_raw.get("json"), dict):
                risk = rk_raw["json"]
                if "event_id" not in risk:
                    risk["event_id"] = event_id
            else:
                risk = {"event_id": event_id, "risk_decision": "NEED_FIX", "risk_level": "medium"}

            _write_json(out_dir / "ai_risk_result.json", risk)

        # ── 4. final decision ────────────────────────────────────
        status, reasons = _final_status(reviewer, risk, writer_ok)
        source_url, source_url_missing = _extract_source_url(event_pack)

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
            "source_mode": str(event_pack.get("source_mode") or t.get("source_mode") or ""),
            "observed_at": str(event_pack.get("observed_at") or t.get("observed_at") or ""),
            "title": str(event_pack.get("title") or t.get("title") or ""),
            "source_url": source_url,
            "source_url_missing": source_url_missing,
        }
        _write_json(out_dir / "x_final_decision.json", final)

        rewritten.append({
            "event_id": event_id,
            "title": final["title"],
            "source_mode": final["source_mode"],
            "observed_at": final["observed_at"],
            "rewrite_reason": reason,
            "final": final,
            "rewriter_result": rewrite,
            "reviewer_result": reviewer,
            "risk_result": risk,
        })

        print(f"  -> status={status} score={final['score']} risk={final['risk_level']} calls_used={model_calls}")

    # ── build output reports ────────────────────────────────────────────

    rewrite_approved = [x for x in rewritten if (x.get("final") or {}).get("status") == "APPROVED_FOR_X_DRYRUN"]

    # ── rescue report (JSON) ──────────────────────────────────────────
    report = {
        "task_id": "x_v2_007a_minimal_rewrite_rescue",
        "generated_at_utc": _utc_now_iso(),
        "model": model,
        "model_runtime": "mock" if use_mock else "openrouter",
        "model_calls_made": model_calls,
        "model_calls_max": max_model_calls,
        "rewritten_count": len(rewritten),
        "rewrite_approved_count": len(rewrite_approved),
        "timeouts": timeout_events,
        "items": rewritten,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
            "daemon_started": False,
            "article_project_modified": False,
            "credential_exposed": False,
        },
    }
    _write_json(reports_dir / "x_v2_007a_minimal_rewrite_rescue_report.json", report)

    # ── rescue report (MD) ────────────────────────────────────────────
    md_lines: list[str] = []
    md_lines.append("# X v2-007a Minimal Rewrite Rescue Report\n\n")
    md_lines.append(f"- **generated_at_utc**: {report['generated_at_utc']}\n")
    md_lines.append(f"- **model**: {report['model']}\n")
    md_lines.append(f"- **model_runtime**: {report['model_runtime']}\n")
    md_lines.append(f"- **model_calls_made**: {report['model_calls_made']} / {report['model_calls_max']}\n")
    md_lines.append(f"- **rewritten_count**: {report['rewritten_count']}\n")
    md_lines.append(f"- **rewrite_approved_count**: {report['rewrite_approved_count']}\n")
    if timeout_events:
        md_lines.append(f"- **timeouts**: {', '.join(timeout_events)}\n")
    md_lines.append("\n---\n\n")

    for it in rewritten:
        fin = it.get("final") if isinstance(it.get("final"), dict) else {}
        rh = it.get("rewriter_result") if isinstance(it.get("rewriter_result"), dict) else {}
        reply = rh.get("reply_hot_take") if isinstance(rh.get("reply_hot_take"), dict) else {}
        md_lines.append(f"## {it.get('event_id')} | {fin.get('status')}\n\n")
        md_lines.append(f"- **title**: {it.get('title')}\n")
        md_lines.append(f"- **source_mode**: {it.get('source_mode')}\n")
        md_lines.append(f"- **observed_at**: {it.get('observed_at')}\n")
        md_lines.append(f"- **score**: {fin.get('score')} / {fin.get('threshold')}\n")
        md_lines.append(f"- **risk_level**: {fin.get('risk_level')}\n")
        md_lines.append(f"- **risk_decision**: {fin.get('risk_decision')}\n")
        src_url = fin.get("source_url") or ""
        src_missing = fin.get("source_url_missing", False)
        if src_url:
            md_lines.append(f"- **source_url**: {src_url}\n")
        if src_missing:
            md_lines.append(f"- **source_url_missing**: true ⚠️\n")
        md_lines.append("\n### Post\n\n")
        md_lines.append(str(rh.get("post") or "").strip() + "\n\n")
        md_lines.append("### Reply Hot Take\n\n")
        md_lines.append(f"- **sarcastic**: {str(reply.get('sarcastic') or '').strip()}\n")
        md_lines.append(f"- **sharp_but_safe**: {str(reply.get('sharp_but_safe') or '').strip()}\n")
        md_lines.append(f"- **og_explainer**: {str(reply.get('og_explainer') or '').strip()}\n")
        md_lines.append("\n---\n\n")

    (reports_dir / "x_v2_007a_minimal_rewrite_rescue_report.md").write_text(
        "".join(md_lines), encoding="utf-8"
    )

    # ── test account queue ─────────────────────────────────────────────
    # 保留 v2-006 approved
    v6_ready = v6_queue.get("ready") if isinstance(v6_queue.get("ready"), list) else []
    base_ready = [x for x in v6_ready if isinstance(x, dict)]

    # 补充 event_pack 信息
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
            url, missing = _extract_source_url(ep)
            r.setdefault("source_url", url)
            if missing and not r.get("source_url"):
                r["source_url_missing"] = True

    # ── 回传 v2-007 已批准的内容 ────────────────────────────────────
    v7_report_path = reports_dir / "x_v2_007_real_hotspot_rewrite_report.json"
    v7_approved_carryover: list[dict[str, Any]] = []
    if v7_report_path.exists():
        try:
            v7_report = _read_json(v7_report_path)
            v7_items = v7_report.get("items") if isinstance(v7_report.get("items"), list) else []
            for it in v7_items:
                fin = it.get("final") if isinstance(it.get("final"), dict) else {}
                if fin.get("status") != "APPROVED_FOR_X_DRYRUN":
                    continue
                eid = str(it.get("event_id") or "").strip()
                # 检查是否已经被 base_ready 包含
                already_in_base = any(
                    str(r.get("event_id") or "").strip() == eid for r in base_ready
                )
                if already_in_base:
                    continue
                rh = it.get("rewriter_result") if isinstance(it.get("rewriter_result"), dict) else {}
                reply = rh.get("reply_hot_take") if isinstance(rh.get("reply_hot_take"), dict) else {}
                src_url = str(fin.get("source_url") or "")
                src_missing = not bool(src_url)
                v7_approved_carryover.append({
                    "event_id": eid,
                    "title": str(it.get("title") or fin.get("title") or ""),
                    "source_mode": str(it.get("source_mode") or fin.get("source_mode") or ""),
                    "observed_at": str(it.get("observed_at") or fin.get("observed_at") or ""),
                    "source_url": src_url,
                    "source_url_missing": src_missing,
                    "persona": "rewritten_v007_carryover",
                    "post": str(rh.get("post") or "").strip(),
                    "reply_hot_take": {
                        "sarcastic": str(reply.get("sarcastic") or "").strip(),
                        "sharp_but_safe": str(reply.get("sharp_but_safe") or "").strip(),
                        "og_explainer": str(reply.get("og_explainer") or "").strip(),
                    },
                    "score": _safe_int(fin.get("score"), 0),
                    "threshold": 80,
                    "decision": str(fin.get("decision") or "APPROVE_FOR_DRYRUN"),
                    "risk_level": str(fin.get("risk_level") or "low"),
                    "recommended_publish_mode": "manual_test_account_only",
                    "publish_status": "not_published",
                    "_carryover_from": "x_v2_007_real_hotspot_rewrite",
                })
            if v7_approved_carryover:
                print(f"[INFO] carried over {len(v7_approved_carryover)} approved item(s) from v2-007")
        except Exception as e:
            print(f"[WARN] failed to read v2-007 report for carryover: {e}")

    # 从 rewrite 结果构建 queue 条目
    ready_from_rewrite: list[dict[str, Any]] = []
    need_rewrite_out: list[dict[str, Any]] = []
    blocked_by_risk_out: list[dict[str, Any]] = []

    for x in rewritten:
        fin = x.get("final") if isinstance(x.get("final"), dict) else {}
        status = str(fin.get("status") or "NEED_REWRITE")
        rh = x.get("rewriter_result") if isinstance(x.get("rewriter_result"), dict) else {}
        reply = rh.get("reply_hot_take") if isinstance(rh.get("reply_hot_take"), dict) else {}
        src_url = str(fin.get("source_url") or "")
        src_missing = fin.get("source_url_missing", False)

        row = {
            "event_id": x.get("event_id"),
            "title": x.get("title"),
            "source_mode": x.get("source_mode"),
            "observed_at": x.get("observed_at"),
            "source_url": src_url,
            "source_url_missing": src_missing,
            "persona": "rewritten_v007a",
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
        "task_id": "x_v2_007a_minimal_rewrite_rescue",
        "generated_at_utc": _utc_now_iso(),
        "ready": base_ready + v7_approved_carryover + ready_from_rewrite,
        "need_rewrite": need_rewrite_out,
        "downgrade_to_article_news": v6_queue.get("downgrade_to_article_news") if isinstance(v6_queue.get("downgrade_to_article_news"), list) else [],
        "blocked_by_risk": blocked_by_risk_out,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
            "daemon_started": False,
            "article_project_modified": False,
            "credential_exposed": False,
        },
    }
    _write_json(reports_dir / "x_v2_007a_test_account_queue.json", final_queue)

    # ── test account queue (MD) ────────────────────────────────────────
    qmd: list[str] = []
    qmd.append("# X v2-007a Test Account Queue\n\n")
    qmd.append(f"- **generated_at_utc**: {final_queue['generated_at_utc']}\n")
    qmd.append(f"- **task_id**: {final_queue['task_id']}\n\n")

    qmd.append("## Ready for test account manual draft\n\n")
    qmd.append(f"**count**: {len(final_queue['ready'])}\n\n")
    for r in final_queue["ready"]:
        qmd.append("---\n\n")
        qmd.append(f"- **event_id**: {r.get('event_id')}\n")
        qmd.append(f"- **title**: {r.get('title', '')}\n")
        qmd.append(f"- **source_mode**: {r.get('source_mode')}\n")
        qmd.append(f"- **observed_at**: {r.get('observed_at')}\n")
        if r.get("source_url"):
            qmd.append(f"- **source_url**: {r.get('source_url')}\n")
        if r.get("source_url_missing"):
            qmd.append(f"- **source_url_missing**: true ⚠️\n")
        qmd.append(f"- **persona**: {r.get('persona')}\n")
        qmd.append(f"- **score**: {r.get('score')} / {r.get('threshold')}\n")
        qmd.append(f"- **risk_level**: {r.get('risk_level')}\n")
        qmd.append(f"- **recommended_publish_mode**: {r.get('recommended_publish_mode')}\n")
        qmd.append(f"- **publish_status**: {r.get('publish_status')}\n\n")
        qmd.append("**Post**:\n\n")
        qmd.append(str(r.get("post") or "").strip() + "\n\n")
        rh = r.get("reply_hot_take") if isinstance(r.get("reply_hot_take"), dict) else {}
        qmd.append("**Reply hot take**:\n\n")
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
        qmd.append("- (none)\n\n")
    else:
        for r in final_queue["blocked_by_risk"]:
            qmd.append(f"- {r.get('event_id')}: {r.get('reason')}\n")
        qmd.append("\n")

    qmd.append("## Safety\n\n")
    for k, v in final_queue["safety"].items():
        qmd.append(f"- **{k}**: {v}\n")

    (reports_dir / "x_v2_007a_test_account_queue.md").write_text("".join(qmd), encoding="utf-8")

    # ── summary ────────────────────────────────────────────────────────
    final_approved = len(final_queue["ready"])
    need_rw = len(final_queue["need_rewrite"])
    blocked = len(final_queue["blocked_by_risk"])

    print(f"\n{'='*60}")
    print(f"[DONE] x_v2_007a minimal rewrite rescue")
    print(f"  rewritten_count: {len(rewritten)}")
    print(f"  rewrite_approved_count: {len(rewrite_approved)}")
    print(f"  final_approved_count (queue ready): {final_approved}")
    print(f"  need_rewrite_count: {need_rw}")
    print(f"  blocked_by_risk: {blocked}")
    print(f"  model_calls_made: {model_calls}")
    print(f"  timeouts: {len(timeout_events)}")
    print(f"  mock_mode: {use_mock}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
