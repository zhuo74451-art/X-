from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_client import load_openrouter_api_key

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(_read_text(path))
    return obj if isinstance(obj, dict) else {}


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _has_suspicious_secret(text: str) -> bool:
    s = text or ""
    patterns = [
        r"OPENROUTER_API_KEY",
        r"OPENAI_API_KEY",
        r"ANTHROPIC_API_KEY",
        r"sk-[A-Za-z0-9]{20,}",
        r"(?i)\b(api[_-]?key|password|cookie)\b\s*[:=]\s*[^ \n\r\t]{8,}",
        r"(?i)\bbearer\s+[A-Za-z0-9_\-]{20,}",
    ]
    return any(re.search(p, s) for p in patterns)


def _md_report(reports_dir: Path, report: dict[str, Any]) -> None:
    failed = report.get("failed") if isinstance(report.get("failed"), list) else []
    lines: list[str] = []
    lines.append("# X v2-003 AI Content Review Tests Report\n\n")
    lines.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    lines.append(f"- passed: {str(report.get('passed')).lower()}\n")
    lines.append(f"- mode: {str(report.get('mode') or '')}\n")
    lines.append(f"- total_checks: {report.get('total_checks')}\n")
    lines.append(f"- failed_checks: {len(failed)}\n")
    lines.append("\n## Failed\n")
    if not failed:
        lines.append("- (none)\n")
    else:
        for x in failed[:80]:
            lines.append(f"- {json.dumps(x, ensure_ascii=False)}\n")
    (reports_dir / "x_v2_003_ai_content_review_test_report.md").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    failed: list[dict[str, Any]] = []

    def check(ok: bool, name: str, detail: Any = "") -> None:
        if not ok:
            failed.append({"check": name, "detail": detail})

    writer_prompt = root / "prompts" / "x_writer_personal_reply_v003.md"
    reviewer_prompt = root / "prompts" / "x_ai_reviewer_v003.md"
    risk_prompt = root / "prompts" / "x_ai_risk_auditor_v003.md"
    check(writer_prompt.exists(), "prompt_exists:writer", str(writer_prompt))
    check(reviewer_prompt.exists(), "prompt_exists:reviewer", str(reviewer_prompt))
    check(risk_prompt.exists(), "prompt_exists:risk", str(risk_prompt))

    v2_root = root / "out" / "x_review_pack_v002"
    check((v2_root / "index.json").exists(), "v2_002_packets_exist", str(v2_root / "index.json"))

    report_path = reports_dir / "x_v2_003_ai_content_review_report.json"
    check(report_path.exists(), "report_exists:v2_003_ai_content_review_report", str(report_path))

    key_present = bool(load_openrouter_api_key())
    mode = "openrouter" if key_present else "blocked_missing_key_expected"

    if report_path.exists():
        rep = _read_json(report_path)
        if not key_present:
            check(
                str(rep.get("status") or "") in {"BLOCKED_MISSING_OPENROUTER_KEY", "BLOCKED_MISSING_OPENROUTER_MODEL", "BLOCKED"},
                "blocked_status_when_no_key",
                rep.get("status"),
            )
            check(int(rep.get("model_calls_made") or 0) == 0, "no_model_calls_when_blocked", rep.get("model_calls_made"))
        else:
            check(int(rep.get("model_calls_made") or 0) <= 12, "model_calls<=12", rep.get("model_calls_made"))
            check(rep.get("safety", {}).get("trae_self_scoring") is False, "trae_self_scoring_false", rep.get("safety"))

    if key_present:
        out_root = root / "out" / "x_review_pack_v003"
        check(out_root.exists(), "out_dir_exists:v003", str(out_root))

        event_dirs = [p for p in sorted(out_root.iterdir()) if p.is_dir()]
        check(len(event_dirs) == 4, "generated_events_equals_4", len(event_dirs))

        for d in event_dirs:
            req_files = [
                "writer_request.json",
                "writer_response_raw.json",
                "writer_result.json",
                "ai_reviewer_request.json",
                "ai_reviewer_response_raw.json",
                "ai_reviewer_result.json",
                "ai_risk_request.json",
                "ai_risk_response_raw.json",
                "ai_risk_result.json",
                "x_final_decision.json",
                "x_review_packet.md",
            ]
            for f in req_files:
                check((d / f).exists(), f"exists:{f}", str(d / f))

            wr = _read_json(d / "writer_result.json") if (d / "writer_result.json").exists() else {}
            personal = str(wr.get("personal_post") or "")
            check(len(personal) <= 140, "personal_post_len<=140", {"event": d.name, "len": len(personal)})

            ra = wr.get("reply_angle") if isinstance(wr.get("reply_angle"), dict) else {}
            check(all(k in ra for k in ["aggressive", "sarcastic", "og_explainer"]), "reply_angle_3_styles", {"event": d.name, "keys": list(ra.keys())})

            forbidden_fields = ["official_post", "thread_outline", "quote_angle", "image_prompt"]
            check(all(k not in wr for k in forbidden_fields), "writer_not_generate_forbidden_fields", {"event": d.name, "present": [k for k in forbidden_fields if k in wr]})

            blob = ""
            for f in req_files:
                p = d / f
                if p.exists():
                    blob += _read_text(p) + "\n"
            check(not _has_suspicious_secret(blob), "no_credential_leak", d.name)
            check("api.twitter.com" not in blob, "no_x_api_connected", d.name)

    report = {
        "task_id": "x_v2_003_ai_personal_reply_generation_review",
        "generated_at_utc": _utc_now_iso(),
        "passed": len(failed) == 0,
        "mode": mode,
        "total_checks": len(failed) + 1,
        "failed": failed,
    }
    _write_json(reports_dir / "x_v2_003_ai_content_review_test_report.json", report)
    _md_report(reports_dir, report)

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

