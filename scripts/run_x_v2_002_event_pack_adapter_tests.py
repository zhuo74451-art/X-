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


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if (line or "").strip():
            n += 1
    return n


def _run_py(root: Path, args: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env["MODEL_RUNTIME"] = "mock"
    for k in ["OPENROUTER_API_KEY", "OPENROUTER_MODEL"]:
        env.pop(k, None)
    p = subprocess.run(
        ["python", *args],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    return int(p.returncode), out


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


def _write_report(reports_dir: Path, report: dict[str, Any]) -> None:
    (reports_dir / "x_v2_002_event_pack_adapter_test_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines: list[str] = []
    lines.append("# X v2-002 Event Pack Adapter Tests Report\n\n")
    lines.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    lines.append(f"- passed: {str(report.get('passed')).lower()}\n")
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    lines.append(f"- total: {counts.get('total')}\n")
    lines.append(f"- passed_count: {counts.get('passed')}\n")
    lines.append(f"- failed_count: {counts.get('failed')}\n")

    failed = report.get("failed") if isinstance(report.get("failed"), list) else []
    lines.append("\n## Failed\n")
    if not failed:
        lines.append("- (none)\n")
    else:
        for x in failed[:80]:
            lines.append(f"- {json.dumps(x, ensure_ascii=False)}\n")

    (reports_dir / "x_v2_002_event_pack_adapter_test_report.md").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    required_paths = {
        "schema": root / "schemas" / "shared_event_schema_v001.json",
        "sample": root / "data" / "sample_shared_event_pack.jsonl",
        "adapter": root / "scripts" / "adapters" / "import_shared_event_pack.py",
        "builder": root / "scripts" / "build_x_review_packet_from_event_pack_v002.py",
        "hard_gates": root / "scripts" / "run_x_v2_002_hard_gates.py",
    }

    failed: list[dict[str, Any]] = []

    def req_exists(name: str) -> None:
        if not required_paths[name].exists():
            failed.append({"check": f"exists:{name}", "detail": str(required_paths[name])})

    for k in list(required_paths.keys()):
        req_exists(k)

    out_import = root / "out" / "shared_event_import"
    out_events = out_import / "events.jsonl"
    out_x_review = root / "out" / "x_review_pack_v002"

    rc1, log1 = _run_py(
        root,
        [
            "scripts/adapters/import_shared_event_pack.py",
            "--input",
            "data/sample_shared_event_pack.jsonl",
            "--out",
            "out/shared_event_import/events.jsonl",
        ],
    )
    if rc1 != 0:
        failed.append({"check": "run:import_adapter", "returncode": rc1, "log_tail": log1[-1200:]})

    rc2, log2 = _run_py(root, ["scripts/build_x_review_packet_from_event_pack_v002.py"])
    if rc2 != 0:
        failed.append({"check": "run:review_packet_builder", "returncode": rc2, "log_tail": log2[-1200:]})

    rc3, log3 = _run_py(root, ["scripts/run_x_v2_002_hard_gates.py"])
    if rc3 != 0:
        failed.append({"check": "run:hard_gates", "returncode": rc3, "log_tail": log3[-1200:]})

    if not out_events.exists():
        failed.append({"check": "exists:import_output_events_jsonl", "detail": str(out_events)})
    if not (out_import / "import_report.json").exists():
        failed.append({"check": "exists:import_report_json", "detail": str(out_import / "import_report.json")})
    if not (out_import / "import_report.md").exists():
        failed.append({"check": "exists:import_report_md", "detail": str(out_import / "import_report.md")})

    sample_event_count = _read_jsonl_count(required_paths["sample"])
    imported_event_count = _read_jsonl_count(out_events)

    if imported_event_count != 4:
        failed.append({"check": "imported_event_count_equals_4", "detail": imported_event_count})

    generated_dirs: list[Path] = []
    if out_x_review.exists():
        for p in sorted(out_x_review.iterdir()):
            if p.is_dir():
                generated_dirs.append(p)

    if len(generated_dirs) != 4:
        failed.append({"check": "generated_review_dirs_equals_4", "detail": len(generated_dirs)})

    for d in generated_dirs:
        x_pack_path = d / "x_content_pack.json"
        if not x_pack_path.exists():
            failed.append({"check": "exists:x_content_pack.json", "event_dir": str(d)})
            continue
        x_pack = _read_json(x_pack_path)
        if str(x_pack.get("publish_status") or "") != "blocked_until_ai_review":
            failed.append({"check": "publish_status_blocked", "event_dir": str(d), "value": x_pack.get("publish_status")})
        if str(x_pack.get("content_generation_mode") or "") != "template_skeleton_no_ai":
            failed.append({"check": "content_generation_mode_template", "event_dir": str(d), "value": x_pack.get("content_generation_mode")})

        gate_path = d / "hard_gate_report.json"
        if not gate_path.exists():
            failed.append({"check": "exists:hard_gate_report.json", "event_dir": str(d)})
        else:
            gate = _read_json(gate_path)
            if gate.get("passed") is not True:
                failed.append({"check": "hard_gate_passed", "event_dir": str(d), "errors": gate.get("errors")})

        blob = ""
        for fp in ["event.json", "x_content_pack.json", "x_review_packet.md", "status.json"]:
            p = d / fp
            if p.exists():
                blob += p.read_text(encoding="utf-8", errors="ignore") + "\n"
        if _has_suspicious_secret(blob):
            failed.append({"check": "no_credential_leak", "event_dir": str(d)})
        if re.search(r"(?i)auto[_-]?publish\\s*[:=]\\s*true", blob):
            failed.append({"check": "no_auto_publish_true", "event_dir": str(d)})
        if "api.twitter.com" in blob:
            failed.append({"check": "no_x_publish_endpoint", "event_dir": str(d)})

    report = {
        "task_id": "x_v2_002_shared_event_pack_adapter",
        "generated_at_utc": _utc_now_iso(),
        "passed": len(failed) == 0,
        "counts": {"total": 1, "passed": 1 if len(failed) == 0 else 0, "failed": 0 if len(failed) == 0 else 1},
        "facts": {
            "schema": str(required_paths["schema"]),
            "sample_event_count": sample_event_count,
            "imported_event_count": imported_event_count,
            "review_generated_count": len(generated_dirs),
            "import_report": str(out_import / "import_report.json"),
            "x_review_dir": str(out_x_review),
        },
        "failed": failed,
        "safety": {
            "paid_model_called": False,
            "x_published": False,
            "article_project_modified": False,
            "production_write": False,
            "daemon_started": False,
            "credential_exposed": False,
        },
    }

    _write_report(reports_dir, report)

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

