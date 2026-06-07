from __future__ import annotations

import json
import os
import subprocess
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


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    p = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout or "", p.stderr or ""


def _truncate(s: str, n: int = 800) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n] + "…"


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    failed: list[dict[str, Any]] = []

    def check(ok: bool, name: str, detail: Any = "") -> None:
        if not ok:
            failed.append({"check": name, "detail": detail})

    v3 = reports_dir / "x_v2_003_ai_content_review_report.json"
    v4_export = reports_dir / "x_v2_004_approved_dryrun_export.json"
    v4_rewrite = reports_dir / "x_v2_004_rewrite_review_report.json"
    v4_final = reports_dir / "x_v2_004_final_dryrun_candidates.json"
    taste = reports_dir / "x_v2_004_taste_gate_report.json"

    check(v3.exists(), "v2_003_report_exists", str(v3))
    check(v4_export.exists(), "v2_004_approved_export_exists", str(v4_export))
    check(v4_rewrite.exists(), "v2_004_rewrite_report_exists", str(v4_rewrite))
    check(v4_final.exists(), "v2_004_final_candidates_exists", str(v4_final))
    check(taste.exists(), "v2_004_taste_gate_report_exists", str(taste))

    need_rewrite_count = None
    if v3.exists():
        d = _read_json(v3)
        counts = d.get("counts") if isinstance(d.get("counts"), dict) else {}
        need_rewrite_count = int(counts.get("need_rewrite") or 0)
        check(need_rewrite_count == 2, "need_rewrite_events_identified", need_rewrite_count)

    if v4_rewrite.exists():
        r = _read_json(v4_rewrite)
        check(int(r.get("new_model_calls_made") or 0) <= 6, "model_calls<=6", r.get("new_model_calls_made"))
        check(int(r.get("rewritten_events") or 0) <= 2, "rewrite_at_most_once_per_event", r.get("rewritten_events"))

    if taste.exists():
        t = _read_json(taste)
        check(t.get("passed") is True, "approved_pass_taste_gate", t.get("failed"))

    if v4_final.exists():
        f = _read_json(v4_final)
        safety = f.get("safety") if isinstance(f.get("safety"), dict) else {}
        check(safety.get("x_published") is False, "x_not_published", safety)
        check(safety.get("x_api_connected") is False, "x_api_not_connected", safety)

    code, out, err = _run_git(["ls-files", "local_only"], root)
    check(code == 0, "git_ls_files_ok", _truncate(err))
    if code == 0:
        check((out or "").strip() == "", "local_only_not_committed", out.strip())

    code, out, err = _run_git(["grep", "-n", "OPENROUTER_API_KEY", "reports"], root)
    if code == 0:
        check(False, "key_not_in_reports", _truncate(out))

    pushed = False
    push_reason = ""
    push_code, push_out, push_err = _run_git(["push"], root)
    if push_code == 0:
        pushed = True
    else:
        pushed = False
        push_reason = _truncate(push_err or push_out)
        if not push_reason:
            push_reason = f"git_push_failed_exit_code={push_code}"

    report = {
        "task_id": "x_v2_004_dryrun_export_and_rewrite",
        "generated_at_utc": _utc_now_iso(),
        "passed": len(failed) == 0,
        "failed": failed,
        "git_push": {
            "attempted": True,
            "pushed": pushed,
            "reason": push_reason,
        },
    }
    _write_json(reports_dir / "x_v2_004_test_report.json", report)

    md: list[str] = []
    md.append("# X v2-004 Tests Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- passed: {str(report.get('passed')).lower()}\n")
    md.append(f"- git_push_attempted: true\n")
    md.append(f"- pushed: {str(pushed).lower()}\n")
    if not pushed:
        md.append(f"- push_reason: {push_reason}\n")
    md.append("\n## Failed\n")
    if not failed:
        md.append("- (none)\n")
    else:
        for x in failed[:80]:
            md.append(f"- {json.dumps(x, ensure_ascii=False)}\n")
    (reports_dir / "x_v2_004_test_report.md").write_text("".join(md), encoding="utf-8")

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
