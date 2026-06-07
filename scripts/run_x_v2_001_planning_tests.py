from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict:
    obj = json.loads(_read_text(path))
    return obj if isinstance(obj, dict) else {}


def _git_modified_files(root: Path) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception:
        return []
    files: list[str] = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        p = s[3:].strip()
        if p:
            files.append(p.replace("\\", "/"))
    return files


def _contains_any(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE | re.MULTILINE):
            return True
    return False


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"

    required_files = {
        "architecture_audit_md": reports_dir / "x_v2_001_architecture_audit.md",
        "architecture_audit_json": reports_dir / "x_v2_001_architecture_audit.json",
        "baseline_md": reports_dir / "x_v2_001_hot_engine_baseline.md",
        "baseline_json": reports_dir / "x_v2_001_hot_engine_baseline.json",
        "bridge_plan_md": reports_dir / "x_v2_001_shared_hotspot_core_bridge_plan.md",
        "bridge_plan_json": reports_dir / "x_v2_001_shared_hotspot_core_bridge_plan.json",
        "autonomous_goal_md": reports_dir / "x_v2_001_autonomous_goal.md",
        "autonomous_goal_json": reports_dir / "x_v2_001_autonomous_goal.json",
    }

    checks: list[dict] = []

    def add_check(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "ok": bool(ok), "detail": detail})

    for k, p in required_files.items():
        add_check(f"exists:{k}", p.exists(), str(p))

    bridge_md = _read_text(required_files["bridge_plan_md"]) if required_files["bridge_plan_md"].exists() else ""
    goal_md = _read_text(required_files["autonomous_goal_md"]) if required_files["autonomous_goal_md"].exists() else ""

    add_check(
        "doc:no_repo_merge",
        _contains_any(bridge_md, [r"不合并仓库", r"no\s*repo\s*merge", r"still\s+separate"]),
        "bridge plan must clearly say no repo merge now",
    )
    add_check(
        "doc:no_auto_publish_now",
        _contains_any(goal_md, [r"不自动发布", r"不真实发布", r"blocked_until_ai_review"]),
        "autonomous goal must clearly say no auto publish now",
    )
    add_check(
        "doc:final_goal_auto_publish",
        _contains_any(goal_md, [r"最终目标是全自动发布", r"最终目标.*自动发布", r"全自动发布"]),
        "autonomous goal must clearly say final goal is auto publish",
    )
    add_check(
        "doc:trae_not_quality_judge",
        _contains_any(goal_md, [r"Trae\s*不负责内容质量判断", r"不做内容质量判断"]),
        "autonomous goal must clearly say Trae is not content-quality judge",
    )
    add_check(
        "doc:ai_reviewer_risk_auditor_hard_gate",
        _contains_any(goal_md, [r"AI Reviewer", r"AI Risk Auditor", r"Hard Gate"]),
        "autonomous goal must contain AI Reviewer / AI Risk Auditor / Hard Gate",
    )
    add_check(
        "doc:event_pack_schema",
        _contains_any(bridge_md, [r"event_pack", r"event_id", r"fact_pack", r"recommended_outputs"]),
        "bridge plan must contain event_pack schema",
    )

    baseline_j = _read_json(required_files["baseline_json"]) if required_files["baseline_json"].exists() else {}
    safety = baseline_j.get("safety") if isinstance(baseline_j.get("safety"), dict) else {}
    add_check("safety:paid_model_called_false", safety.get("paid_model_called") is False, "baseline.safety.paid_model_called == false")
    add_check("safety:x_published_false", safety.get("x_published") is False, "baseline.safety.x_published == false")
    add_check("safety:daemon_started_false", safety.get("daemon_started") is False, "baseline.safety.daemon_started == false")
    add_check("safety:credential_exposed_false", safety.get("credential_exposed") is False, "baseline.safety.credential_exposed == false")

    bridge_j = _read_json(required_files["bridge_plan_json"]) if required_files["bridge_plan_json"].exists() else {}
    principles = bridge_j.get("principles") if isinstance(bridge_j.get("principles"), dict) else {}
    add_check("bridge:no_repo_merge_now_true", principles.get("no_repo_merge_now") is True, "bridge_plan.principles.no_repo_merge_now == true")
    add_check(
        "bridge:no_article_project_modification_true",
        principles.get("no_article_project_modification") is True,
        "bridge_plan.principles.no_article_project_modification == true",
    )

    goal_j = _read_json(required_files["autonomous_goal_json"]) if required_files["autonomous_goal_json"].exists() else {}
    add_check("goal:trae_quality_judgment_allowed_false", goal_j.get("trae_quality_judgment_allowed") is False, "autonomous_goal.trae_quality_judgment_allowed == false")
    add_check("goal:final_goal_auto_publish_true", goal_j.get("final_goal_auto_publish") is True, "autonomous_goal.final_goal_auto_publish == true")

    modified = _git_modified_files(root)
    allowed_prefixes = ("reports/", "scripts/run_x_v2_001_planning_tests.py")
    disallowed = [p for p in modified if not any(p == ap or p.startswith(ap.rstrip("/")) for ap in allowed_prefixes)]
    add_check("repo:business_code_modified_false", len(disallowed) == 0, f"disallowed_modified_files={disallowed}")

    passed = [c for c in checks if c.get("ok") is True]
    failed = [c for c in checks if c.get("ok") is not True]

    report = {
        "task_id": "x_v2_001_audit_baseline_shared_hotspot_plan",
        "generated_at_utc": _utc_now_iso(),
        "passed": len(failed) == 0,
        "counts": {"passed": len(passed), "failed": len(failed), "total": len(checks)},
        "checks": checks,
    }

    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "x_v2_001_planning_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# X v2-001 Planning Tests Report\n\n")
    lines.append(f"- generated_at_utc: {report['generated_at_utc']}\n")
    lines.append(f"- passed: {str(report['passed']).lower()}\n")
    lines.append(f"- checks_total: {report['counts']['total']}\n")
    lines.append(f"- checks_passed: {report['counts']['passed']}\n")
    lines.append(f"- checks_failed: {report['counts']['failed']}\n")

    lines.append("\n## Failed\n")
    if not failed:
        lines.append("- (none)\n")
    else:
        for x in failed:
            lines.append(f"- {x.get('id')}: {x.get('detail')}\n")

    lines.append("\n## Passed (summary)\n")
    for x in passed[:30]:
        lines.append(f"- {x.get('id')}\n")
    if len(passed) > 30:
        lines.append(f"- ... and {len(passed) - 30} more\n")

    (reports_dir / "x_v2_001_planning_test_report.md").write_text("".join(lines), encoding="utf-8")

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

