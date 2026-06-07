from __future__ import annotations

import argparse
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


def _as_text(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


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


def _has_auto_publish_true(text: str) -> bool:
    s = text or ""
    return bool(re.search(r"(?i)auto[_-]?publish\s*[:=]\s*true", s))


def _placeholder_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return False
    return ("example.com" in u) or ("placeholder" in u)


def _gate_one(event_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    event_path = event_dir / "event.json"
    pack_path = event_dir / "x_content_pack.json"

    if not event_path.exists():
        errors.append("missing_file:event.json")
        return {"passed": False, "errors": errors, "warnings": warnings}
    if not pack_path.exists():
        errors.append("missing_file:x_content_pack.json")
        return {"passed": False, "errors": errors, "warnings": warnings}

    event = _read_json(event_path)
    pack = _read_json(pack_path)

    event_id = str(pack.get("event_id") or "").strip() or str(event.get("input_id") or "").strip()
    title = str(pack.get("title") or "").strip() or str(event.get("title") or "").strip()
    summary = str(event.get("summary") or "").strip()

    if not event_id:
        errors.append("missing:event_id")
    if not title:
        errors.append("missing:title")
    if not summary:
        errors.append("missing:summary")

    sp = event.get("source_pack") if isinstance(event.get("source_pack"), list) else None
    if sp is None:
        errors.append("missing:source_pack")
    elif not sp:
        errors.append("invalid:source_pack:empty")
    else:
        first = sp[0] if isinstance(sp[0], dict) else {}
        url = str(first.get("url") or "").strip()
        if not url:
            errors.append("invalid:source_pack[0].url:empty")
        elif _placeholder_url(url):
            warnings.append("warning:source_pack[0].url_is_placeholder")

    if "risk_flags" not in event:
        errors.append("missing:event.risk_flags")
    elif not isinstance(event.get("risk_flags"), list):
        errors.append("invalid:event.risk_flags:not_list")

    if "risk_flags" not in pack:
        errors.append("missing:x_content_pack.risk_flags")
    elif not isinstance(pack.get("risk_flags"), list):
        errors.append("invalid:x_content_pack.risk_flags:not_list")

    required_top = ["official_post", "personal_post", "reply_angle", "quote_angle", "thread_outline"]
    for k in required_top:
        if k not in pack:
            errors.append(f"missing:x_content_pack.{k}")

    op = pack.get("official_post") if isinstance(pack.get("official_post"), dict) else {}
    pp = pack.get("personal_post") if isinstance(pack.get("personal_post"), dict) else {}
    ra = pack.get("reply_angle") if isinstance(pack.get("reply_angle"), dict) else {}
    qa = pack.get("quote_angle") if isinstance(pack.get("quote_angle"), dict) else {}

    for k in ["draft", "style", "max_chars"]:
        if k not in op:
            errors.append(f"missing:official_post.{k}")
        if k not in pp:
            errors.append(f"missing:personal_post.{k}")
    for k in ["draft", "target_type"]:
        if k not in ra:
            errors.append(f"missing:reply_angle.{k}")
    for k in ["draft", "angle"]:
        if k not in qa:
            errors.append(f"missing:quote_angle.{k}")

    if not isinstance(pack.get("thread_outline"), list):
        errors.append("invalid:thread_outline:not_list")

    if str(pack.get("publish_status") or "").strip() != "blocked_until_ai_review":
        errors.append("invalid:publish_status:not_blocked_until_ai_review")

    blob = _as_text(event) + "\n" + _as_text(pack)
    if _has_suspicious_secret(blob):
        errors.append("credential_leak_detected")
    if _has_auto_publish_true(blob):
        errors.append("auto_publish_true_detected")
    if "https://api.twitter.com" in blob or "api.twitter.com" in blob:
        errors.append("x_publish_endpoint_detected")

    mode = str(pack.get("content_generation_mode") or "").strip()
    if mode != "template_skeleton_no_ai":
        errors.append("invalid:content_generation_mode:not_template_skeleton_no_ai")

    return {
        "event_id": event_id,
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checked_at_utc": _utc_now_iso(),
        "publish_status": "blocked_until_ai_review",
        "content_generation_mode": mode,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default="out/x_review_pack_v002")
    args = ap.parse_args()

    root = _project_root()
    in_dir = Path(args.input_dir)
    if not in_dir.is_absolute():
        in_dir = root / in_dir

    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    per_event: list[dict[str, Any]] = []
    if in_dir.exists():
        for p in sorted(in_dir.iterdir()):
            if not p.is_dir():
                continue
            r = _gate_one(p)
            _write_json(p / "hard_gate_report.json", r)
            per_event.append(r)

    passed = [x for x in per_event if x.get("passed") is True]
    failed = [x for x in per_event if x.get("passed") is not True]

    report = {
        "task_id": "x_v2_002_shared_event_pack_adapter",
        "generated_at_utc": _utc_now_iso(),
        "input_dir": str(in_dir),
        "counts": {"total": len(per_event), "passed": len(passed), "failed": len(failed)},
        "passed": len(failed) == 0,
        "results": per_event,
        "safety": {
            "paid_model_called": False,
            "x_published": False,
            "daemon_started": False,
            "credential_exposed": False
        }
    }

    _write_json(reports_dir / "x_v2_002_hard_gate_report.json", report)

    lines: list[str] = []
    lines.append("# X v2-002 Hard Gate Report\n\n")
    lines.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    lines.append(f"- input_dir: {report.get('input_dir')}\n")
    lines.append(f"- passed: {str(report.get('passed')).lower()}\n")
    lines.append(f"- total: {report['counts']['total']}\n")
    lines.append(f"- passed_count: {report['counts']['passed']}\n")
    lines.append(f"- failed_count: {report['counts']['failed']}\n")

    lines.append("\n## Failed\n")
    if not failed:
        lines.append("- (none)\n")
    else:
        for r in failed:
            eid = str(r.get("event_id") or "")
            lines.append(f"- {eid}: {json.dumps(r.get('errors') or [], ensure_ascii=False)}\n")

    (reports_dir / "x_v2_002_hard_gate_report.md").write_text("".join(lines), encoding="utf-8")

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

