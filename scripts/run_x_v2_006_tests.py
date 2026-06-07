from __future__ import annotations

import json
import os
import re
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


def _truncate(s: str, n: int = 1200) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n] + "…"


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    p = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return p.returncode, p.stdout or "", p.stderr or ""


def _read_jsonl_count(path: Path) -> int:
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if (line or "").strip():
                n += 1
    return n


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    failed: list[dict[str, Any]] = []

    def check(ok: bool, name: str, detail: Any = "") -> None:
        if not ok:
            failed.append({"check": name, "detail": detail})

    real_jsonl = root / "data" / "real_event_pack_v006.jsonl"
    real_report = reports_dir / "x_v2_006_real_event_pack_report.json"
    persona_report = reports_dir / "x_v2_006_real_event_persona_dryrun_report.json"
    queue_json = reports_dir / "x_v2_006_test_account_queue.json"
    queue_md = reports_dir / "x_v2_006_test_account_queue.md"
    taste_report = reports_dir / "x_v2_006_taste_gate_report.json"

    check(real_report.exists(), "real_event_pack_report_exists", str(real_report))

    status = ""
    real_event_count = 0
    source_mode = ""
    blocked_reason = ""

    if real_report.exists():
        rr = _read_json(real_report)
        status = str(rr.get("status") or "")
        source_mode = str(rr.get("source_mode") or "")
        real_event_count = int(rr.get("real_event_count") or 0)
        blocked_reason = str(rr.get("blocked_reason") or "")

    if status == "DONE":
        check(real_jsonl.exists(), "real_event_pack_jsonl_exists", str(real_jsonl))
        if real_jsonl.exists():
            count = _read_jsonl_count(real_jsonl)
            check(count >= 3, "real_event_count>=3", count)

        check(source_mode not in {"mock_sample", "fake_demo", "hand_written_only"}, "source_mode_not_mock", source_mode)
    else:
        check(status == "BLOCKED_NO_REAL_EVENT_SOURCE", "blocked_when_no_real_source", {"status": status, "reason": blocked_reason})

    if status == "DONE":
        check(persona_report.exists(), "persona_dryrun_report_exists", str(persona_report))
        check(queue_json.exists(), "test_account_queue_json_exists", str(queue_json))
        check(queue_md.exists(), "test_account_queue_md_exists", str(queue_md))
        check(taste_report.exists(), "taste_gate_report_exists", str(taste_report))

    if persona_report.exists():
        pr = _read_json(persona_report)
        check(int(pr.get("model_calls_made") or 0) <= 12, "model_calls<=12", pr.get("model_calls_made"))

    if queue_md.exists():
        text = queue_md.read_text(encoding="utf-8", errors="ignore")
        check(re.search(r"score\\s*:\\s*\\d+\\s*/\\s*\\d+", text) is None, "score_format_no_slash", "found score: a/b")

    code, out, err = _run_git(["ls-files", "local_only"], root)
    check(code == 0, "git_ls_files_ok", _truncate(err))
    if code == 0:
        check((out or "").strip() == "", "local_only_not_committed", out.strip())

    code, out, err = _run_git(["grep", "-n", "OPENROUTER_API_KEY", "reports"], root)
    if code == 0:
        check(False, "key_not_in_reports", _truncate(out))

    code, out, err = _run_git(["grep", "-n", "api.twitter.com", "reports"], root)
    if code == 0:
        check(False, "no_x_api_connected", _truncate(out))

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
        "task_id": "x_v2_006_real_event_persona_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "passed": len(failed) == 0,
        "failed": failed,
        "real_event_pack": {
            "status": status,
            "source_mode": source_mode,
            "real_event_count": real_event_count,
            "blocked_reason": blocked_reason,
        },
        "git_push": {"attempted": True, "pushed": pushed, "reason": push_reason},
    }
    _write_json(reports_dir / "x_v2_006_test_report.json", report)

    md: list[str] = []
    md.append("# X v2-006 Tests Report\n\n")
    md.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    md.append(f"- passed: {str(report.get('passed')).lower()}\n")
    md.append(f"- pushed: {str(pushed).lower()}\n")
    if not pushed:
        md.append(f"- push_reason: {push_reason}\n")
    md.append("\n## Failed\n")
    if not failed:
        md.append("- (none)\n")
    else:
        for x in failed[:80]:
            md.append(f"- {json.dumps(x, ensure_ascii=False)}\n")
    (reports_dir / "x_v2_006_test_report.md").write_text("".join(md), encoding="utf-8")

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

