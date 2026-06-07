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


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    failed: list[dict[str, Any]] = []

    def check(ok: bool, name: str, detail: Any = "") -> None:
        if not ok:
            failed.append({"check": name, "detail": detail})

    prompt_sharp = root / "prompts" / "x_persona_personal_sharp_v005.md"
    prompt_balanced = root / "prompts" / "x_persona_personal_balanced_v005.md"
    prompt_reply = root / "prompts" / "x_persona_reply_hot_take_v005.md"
    banned_cfg = root / "configs" / "x_taste_banned_phrases_v005.json"
    check(prompt_sharp.exists(), "persona_prompt_exists:personal_sharp", str(prompt_sharp))
    check(prompt_balanced.exists(), "persona_prompt_exists:personal_balanced", str(prompt_balanced))
    check(prompt_reply.exists(), "persona_prompt_exists:reply_hot_take", str(prompt_reply))
    check(banned_cfg.exists(), "banned_phrases_config_exists", str(banned_cfg))

    persona_report = reports_dir / "x_v2_005_persona_split_report.json"
    taste_report = reports_dir / "x_v2_005_taste_gate_report.json"
    final_pkg = reports_dir / "x_v2_005_final_test_account_dryrun_package.json"
    check(persona_report.exists(), "persona_report_exists", str(persona_report))
    check(taste_report.exists(), "taste_gate_report_exists", str(taste_report))
    check(final_pkg.exists(), "final_dryrun_package_exists", str(final_pkg))

    if persona_report.exists():
        r = _read_json(persona_report)
        check(int(r.get("model_calls_made") or 0) <= 9, "model_calls<=9", r.get("model_calls_made"))
        items = r.get("items") if isinstance(r.get("items"), list) else []
        case = [x for x in items if isinstance(x, dict) and x.get("event_id") == "evt_case_001"]
        check(bool(case), "evt_case_001_present", "")
        if case:
            c0 = case[0]
            check(
                str(c0.get("route") or c0.get("status") or "") == "DOWNGRADE_TO_ARTICLE_OR_NEWS",
                "evt_case_001_downgraded",
                c0.get("route") or c0.get("status"),
            )

    if final_pkg.exists():
        p = _read_json(final_pkg)
        groups = p.get("groups") if isinstance(p.get("groups"), dict) else {}
        ready = groups.get("ready") if isinstance(groups.get("ready"), list) else []
        for it in ready:
            if not isinstance(it, dict):
                continue
            post = str(it.get("post") or "")
            check("official_safe" not in post, "no_official_safe", it.get("event_id"))
            check("thread" not in post.lower(), "no_thread", it.get("event_id"))
            check("image" not in post.lower(), "no_image", it.get("event_id"))

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
        "task_id": "x_v2_005_persona_split_test_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "passed": len(failed) == 0,
        "failed": failed,
        "git_push": {
            "attempted": True,
            "pushed": pushed,
            "reason": push_reason,
        },
    }
    _write_json(reports_dir / "x_v2_005_test_report.json", report)

    md: list[str] = []
    md.append("# X v2-005 Tests Report\n\n")
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
    (reports_dir / "x_v2_005_test_report.md").write_text("".join(md), encoding="utf-8")

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

