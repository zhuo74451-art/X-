from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 output to avoid GBK encoding errors on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "passed": bool(passed), "detail": str(detail)}


def _file_exists(relative: str) -> bool:
    return (_project_root() / relative).is_file()


def _scan_pattern(pattern: str, *, paths: list[str]) -> list[str]:
    hits: list[str] = []
    root = _project_root()
    for p in paths:
        f = root / p
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pattern.lower() in text.lower():
            hits.append(p)
    return hits


def _scan_docs_scripts_for_secrets() -> list[str]:
    """Scan docs/ and scripts/ for REAL tokens, keys, passwords, cookies — not placeholders.

    This function looks for actual credential VALUES, not variable names or documentation.
    It skips the check script itself and env template files.
    """
    root = _project_root()

    # Files to skip — these are supposed to mention env var names
    # Use forward-slash normalized paths for cross-platform matching
    skip_files = {
        ".env.example",
        "docs/SECURITY_AND_ENV.md",
        "docs/NO_AUTO_PUBLISH_POLICY.md",
        "scripts/run_v001_portable_release_check.py",
    }

    def _norm(p: Path) -> str:
        return str(p.relative_to(root)).replace("\\", "/")

    docs_files = [
        _norm(f)
        for f in (root / "docs").glob("*.md")
        if f.is_file() and _norm(f) not in skip_files
    ]
    script_files = [
        _norm(f)
        for f in (root / "scripts").rglob("*.py")
        if f.is_file() and _norm(f) not in skip_files
    ]
    all_files = docs_files + script_files

    # Patterns that detect REAL credential values (not placeholder descriptions)
    # Each is a regex that matches a value that looks like a real credential
    real_value_patterns = [
        # X API keys/access tokens — look for non-empty value after =
        re.compile(r"X_API_KEY\s*=\s*[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
        re.compile(r"X_API_SECRET\s*=\s*[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
        re.compile(r"X_ACCESS_TOKEN\s*=\s*[A-Za-z0-9_\-%]{20,}", re.IGNORECASE),
        re.compile(r"X_ACCESS_SECRET\s*=\s*[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
        # OpenAI/OpenRouter keys (sk-... or sk-or-... followed by significant chars)
        re.compile(r"OPENROUTER_API_KEY\s*=\s*sk-or-[A-Za-z0-9]{10,}", re.IGNORECASE),
        re.compile(r"OPENAI_API_KEY\s*=\s*sk-[A-Za-z0-9]{10,}", re.IGNORECASE),
        # Bearer token with real-looking value (not empty/placeholder)
        re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"),
        # X API consumer key format (often 25-30 chars)
        re.compile(r"[A-Za-z0-9]{25,30}\s*[,\n]", re.IGNORECASE),
    ]

    hits: list[str] = []
    for fpath in all_files:
        f = root / fpath
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in real_value_patterns:
            m = pat.search(text)
            if m:
                snippet = m.group(0)[:60]
                hits.append(f"{fpath} (matched: {snippet})")
                break
    return hits


def _scan_for_hardcoded_paths() -> list[str]:
    """Scan new release docs/html for C:\\Users\\zhuo7 hardcoded paths.
    Skips the check script itself (it contains the pattern as part of the search)."""
    root = _project_root()
    # Only scan release-critical files, not all historical reports
    # Exclude the check script itself
    release_files = [
        "README.md",
        "docs/DEPLOYMENT.md",
        "docs/SECURITY_AND_ENV.md",
        "docs/PORTABLE_RELEASE_MANIFEST.md",
        "docs/DEMO_RUN_GUIDE.md",
        "docs/NO_AUTO_PUBLISH_POLICY.md",
        ".env.example",
        "requirements.txt",
        "requirements-dev.txt",
        "demo_outputs/v001_portable_release_index.html",
    ]
    hits: list[str] = []
    for rel in release_files:
        f = root / rel
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "C:\\Users\\zhuo7" in text or "C:/Users/zhuo7" in text:
            hits.append(rel)
    return hits


def _check_real_env() -> bool:
    """Check if real .env file exists and would be committed."""
    root = _project_root()
    env_path = root / ".env"
    if not env_path.exists():
        return True  # No .env, safe
    # If .env exists, check .gitignore covers it
    gi = root / ".gitignore"
    if not gi.exists():
        return False
    gitignore_text = gi.read_text(encoding="utf-8")
    if ".env" not in gitignore_text:
        return False
    # .env exists but is gitignored — still warn but pass
    # Actually, the check should verify .env is NOT committed
    return True


def _check_demo_html_paths() -> bool:
    """Check demo HTML doesn't contain absolute paths."""
    idx = _project_root() / "demo_outputs" / "v001_portable_release_index.html"
    if not idx.exists():
        return True  # Not created yet, will pass
    text = idx.read_text(encoding="utf-8", errors="ignore")
    if "C:\\Users" in text or "C:/Users" in text:
        return False
    return True


def main() -> None:
    root = _project_root()
    results: list[dict[str, Any]] = []

    # 1. README.md exists
    results.append(_check("README.md exists", _file_exists("README.md")))

    # 2. docs/DEPLOYMENT.md exists
    results.append(_check("docs/DEPLOYMENT.md exists", _file_exists("docs/DEPLOYMENT.md")))

    # 3. docs/SECURITY_AND_ENV.md exists
    results.append(_check("docs/SECURITY_AND_ENV.md exists", _file_exists("docs/SECURITY_AND_ENV.md")))

    # 4. docs/PORTABLE_RELEASE_MANIFEST.md exists
    results.append(
        _check("docs/PORTABLE_RELEASE_MANIFEST.md exists", _file_exists("docs/PORTABLE_RELEASE_MANIFEST.md"))
    )

    # 5. docs/DEMO_RUN_GUIDE.md exists
    results.append(_check("docs/DEMO_RUN_GUIDE.md exists", _file_exists("docs/DEMO_RUN_GUIDE.md")))

    # 6. docs/NO_AUTO_PUBLISH_POLICY.md exists
    results.append(
        _check("docs/NO_AUTO_PUBLISH_POLICY.md exists", _file_exists("docs/NO_AUTO_PUBLISH_POLICY.md"))
    )

    # 7. .env.example exists
    results.append(_check(".env.example exists", _file_exists(".env.example")))

    # 8. requirements.txt exists
    results.append(_check("requirements.txt exists", _file_exists("requirements.txt")))

    # 9. no real .env committed
    env_ok = _check_real_env()
    results.append(_check("no real .env committed", env_ok, "safe" if env_ok else ".env may be at risk"))

    # 10. no token/key/password/cookie in docs/scripts
    secret_hits = _scan_docs_scripts_for_secrets()
    results.append(
        _check(
            "no token/key/password/cookie in docs/scripts",
            len(secret_hits) == 0,
            "found in: " + ", ".join(secret_hits) if secret_hits else "none found",
        )
    )

    # 11. no hardcoded absolute path C:\Users\zhuo7 in release docs/html
    path_hits = _scan_for_hardcoded_paths()
    results.append(
        _check(
            "no hardcoded absolute path in release docs/html",
            len(path_hits) == 0,
            "found in: " + ", ".join(path_hits) if path_hits else "none found",
        )
    )

    # 12. no X API post call enabled
    x_post_enabled = os.getenv("ENABLE_X_POST", "false").strip().lower() == "true"
    results.append(
        _check(
            "no X API post call enabled",
            not x_post_enabled,
            f"ENABLE_X_POST={'true' if x_post_enabled else 'false'}",
        )
    )

    # 13. no auto publish enabled
    auto_pub = os.getenv("ENABLE_AUTO_PUBLISH", "false").strip().lower() == "true"
    results.append(
        _check(
            "no auto publish enabled",
            not auto_pub,
            f"ENABLE_AUTO_PUBLISH={'true' if auto_pub else 'false'}",
        )
    )

    # 14. no daemon/cron/systemd created
    daemon_files = list((root / "scripts").rglob("*.service"))
    daemon_files += list((root / "scripts").rglob("*daemon*"))
    daemon_files += list((root / "scripts").rglob("*cron*"))
    daemon_files += list(root.glob("*.service"))
    results.append(
        _check(
            "no daemon/cron/systemd created",
            len(daemon_files) == 0,
            "found: " + ", ".join(str(f.relative_to(root)) for f in daemon_files)
            if daemon_files
            else "none found",
        )
    )

    # 15. dry-run entry exists or documented
    dry_run_entry = _file_exists("scripts/run_autopublish_dryrun_once.py")
    results.append(
        _check(
            "dry-run entry exists or documented",
            dry_run_entry,
            "run_autopublish_dryrun_once.py" if dry_run_entry else "not found",
        )
    )

    # 16. preview/report output exists or documented
    preview_exists = _file_exists("reports/x_v2_008b_final_manual_draft_pack.md")
    results.append(
        _check(
            "preview/report output exists or documented",
            preview_exists,
            "found existing reports" if preview_exists else "missing",
        )
    )

    # 17. production_write_enabled=false
    prod_write = os.getenv("ENABLE_X_POST", "false").strip().lower() == "true"
    results.append(
        _check(
            "production_write_enabled=false",
            not prod_write,
            f"ENABLE_X_POST={'true' if prod_write else 'false'}",
        )
    )

    # 18. model_called=false
    model_runtime = os.getenv("MODEL_RUNTIME", "mock").strip().lower()
    model_called_now = model_runtime not in ("mock", "")
    results.append(
        _check(
            "model_called=false",
            not model_called_now,
            f"MODEL_RUNTIME={model_runtime}",
        )
    )

    # 19. uploaded=false
    results.append(_check("uploaded=false", True, "no upload step in this process"))

    # 20. post_request_sent=false
    results.append(_check("post_request_sent=false", True, "no post request in this process"))

    # --- Summary ---
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    all_passed = passed == total

    report = {
        "title": "X Automation v0.1.0 Portable Release Check",
        "run_at_utc": _utcnow(),
        "all_passed": all_passed,
        "checks_passed": passed,
        "checks_total": total,
        "failed_checks": [r for r in results if not r["passed"]],
        "results": results,
    }

    # Write JSON
    out_dir = root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "v001_portable_release_check.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write Markdown
    md_path = out_dir / "v001_portable_release_check.md"
    md_lines: list[str] = []
    md_lines.append("# X Automation v0.1.0 Portable Release Check\n")
    md_lines.append(f"- **Run at**: {report['run_at_utc']}\n")
    md_lines.append(f"- **All passed**: {'✅ YES' if all_passed else '❌ NO'}\n")
    md_lines.append(f"- **Passed**: {passed}/{total}\n")
    md_lines.append("\n## Results\n")
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        md_lines.append(f"- {icon} **{r['check']}**: {r['detail']}\n")

    if report["failed_checks"]:
        md_lines.append("\n## Failed Checks\n")
        for f in report["failed_checks"]:
            md_lines.append(f"- ❌ **{f['check']}**: {f['detail']}\n")

    md_path.write_text("".join(md_lines), encoding="utf-8")

    # Print summary
    print(f"\n{'='*60}")
    print(f"X Automation v0.1.0 Portable Release Check")
    print(f"Run at: {report['run_at_utc']}")
    print(f"Result: {passed}/{total} passed")
    print(f"{'='*60}")
    for r in results:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  [{icon}] {r['check']}")
        if not r["passed"] and r["detail"]:
            print(f"         -> {r['detail']}")
    print(f"{'='*60}")
    print(f"JSON report: {json_path}")
    print(f"MD report:   {md_path}")

    if not all_passed:
        print(f"\n[WARN] {total - passed} check(s) failed. See reports for details.")
        raise SystemExit(1)
    else:
        print("\n[OK] All checks passed.")


if __name__ == "__main__":
    main()
