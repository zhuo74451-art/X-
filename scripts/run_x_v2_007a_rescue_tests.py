#!/usr/bin/env python3
"""X v2-007a Rescue Tests — 验证 v2-007a 输出完整性和安全约束。

检查项：
1. v2-006 输入存在
2. v2-007a 输出存在
3. model_calls <= 6
4. 不含 mock/static（除非 runtime=mock）
5. approved item 有 observed_at
6. source_url 不伪造
7. x_published=false
8. x_api_connected=false
9. production_write=false
10. daemon_started=false
11. article_project_modified=false
12. credential_exposed=false
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}


def _file_exists(path: Path, label: str) -> tuple[bool, str]:
    ok = path.exists()
    return ok, f"{'PASS' if ok else 'FAIL'}: {label} exists={ok} | {path.name}"


def main() -> int:
    root = _project_root()
    reports_dir = root / "reports"
    results: list[tuple[bool, str]] = []

    # ── 1. v2-006 inputs exist ──────────────────────────────────────
    v6_report = reports_dir / "x_v2_006_real_event_persona_dryrun_report.json"
    v6_queue = reports_dir / "x_v2_006_test_account_queue.json"
    ok, msg = _file_exists(v6_report, "v2-006 report")
    results.append((ok, msg))
    ok, msg = _file_exists(v6_queue, "v2-006 queue")
    results.append((ok, msg))

    # ── 2. v2-007a outputs exist ────────────────────────────────────
    rescue_report = reports_dir / "x_v2_007a_minimal_rewrite_rescue_report.json"
    rescue_md = reports_dir / "x_v2_007a_minimal_rewrite_rescue_report.md"
    queue_json = reports_dir / "x_v2_007a_test_account_queue.json"
    queue_md = reports_dir / "x_v2_007a_test_account_queue.md"
    diag_json = reports_dir / "x_v2_007_stuck_diagnosis_report.json"
    diag_md = reports_dir / "x_v2_007_stuck_diagnosis_report.md"
    rescue_script = root / "scripts" / "run_x_v2_007a_minimal_rewrite_rescue.py"
    test_script = root / "scripts" / "run_x_v2_007a_rescue_tests.py"

    for p, lbl in [
        (rescue_report, "v2-007a rescue report (json)"),
        (rescue_md, "v2-007a rescue report (md)"),
        (queue_json, "v2-007a test account queue (json)"),
        (queue_md, "v2-007a test account queue (md)"),
        (diag_json, "v2-007 stuck diagnosis (json)"),
        (diag_md, "v2-007 stuck diagnosis (md)"),
        (rescue_script, "v2-007a rescue script"),
        (test_script, "v2-007a test script"),
    ]:
        ok, msg = _file_exists(p, lbl)
        results.append((ok, msg))

    # ── 3. model_calls <= 6 ────────────────────────────────────────
    if rescue_report.exists():
        rr = _read_json(rescue_report)
        calls = rr.get("model_calls_made", -1)
        max_calls = rr.get("model_calls_max", 6)
        ok = calls <= max_calls
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: model_calls_made={calls} <= max={max_calls}"))

        # 4. no mock/static (unless runtime=mock)
        runtime = str(rr.get("model_runtime") or "").strip()
        items = rr.get("items") if isinstance(rr.get("items"), list) else []
        for it in items:
            rew = it.get("rewriter_result") if isinstance(it.get("rewriter_result"), dict) else {}
            post = str(rew.get("post") or "").strip()
            # Check for mock/static markers
            has_mock_marker = any(m in post.lower() for m in ["[mock]", "[static]", "[sample]", "mock data"])
            if runtime != "mock":
                ok = not has_mock_marker
                results.append((ok, f"{'PASS' if ok else 'FAIL'}: no mock/static in post for {it.get('event_id')}"))

        # 5. approved items have observed_at
        for it in items:
            fin = it.get("final") if isinstance(it.get("final"), dict) else {}
            if fin.get("status") == "APPROVED_FOR_X_DRYRUN":
                obs = str(fin.get("observed_at") or "").strip()
                ok = bool(obs)
                results.append((ok, f"{'PASS' if ok else 'FAIL'}: approved item {it.get('event_id')} has observed_at={obs}"))

        # 6. source_url not forged
        for it in items:
            fin = it.get("final") if isinstance(it.get("final"), dict) else {}
            src_url = str(fin.get("source_url") or "").strip()
            src_missing = fin.get("source_url_missing", False)
            if src_missing and not src_url:
                results.append((True, f"PASS: source_url_missing=true for {it.get('event_id')} (not forged)"))
            elif src_url:
                # basic URL validation
                ok = src_url.startswith("http://") or src_url.startswith("https://")
                results.append((ok, f"{'PASS' if ok else 'FAIL'}: source_url format valid for {it.get('event_id')}: {src_url[:80]}"))

    # ── 7-12. safety flags ─────────────────────────────────────────
    safety_sources = []
    if rescue_report.exists():
        safety_sources.append(("rescue_report", _read_json(rescue_report).get("safety", {})))
    if queue_json.exists():
        safety_sources.append(("queue", _read_json(queue_json).get("safety", {})))
    if diag_json.exists():
        safety_sources.append(("diagnosis", _read_json(diag_json).get("safety", {})))

    safety_checks = [
        ("x_published", False),
        ("x_api_connected", False),
        ("production_write", False),
        ("daemon_started", False),
        ("article_project_modified", False),
        ("credential_exposed", False),
    ]

    for key, expected in safety_checks:
        all_ok = True
        details = []
        for src_name, safety in safety_sources:
            if not isinstance(safety, dict):
                continue
            val = safety.get(key)
            if val != expected:
                all_ok = False
                details.append(f"{src_name}:{key}={val}")
        if not safety_sources:
            all_ok = False
            details.append("no safety data found")
        results.append((all_ok, f"{'PASS' if all_ok else 'FAIL'}: {key}={expected} | {'; '.join(details) if details else 'ok'}"))

    # ── EXTRA: check v2-007a queue integrity ───────────────────────
    if queue_json.exists():
        q = _read_json(queue_json)
        ready = q.get("ready") if isinstance(q.get("ready"), list) else []
        need_rw = q.get("need_rewrite") if isinstance(q.get("need_rewrite"), list) else []
        blocked = q.get("blocked_by_risk") if isinstance(q.get("blocked_by_risk"), list) else []

        results.append((True, f"INFO: queue ready={len(ready)} need_rewrite={len(need_rw)} blocked_by_risk={len(blocked)}"))

        # Verify each ready item has required fields
        for r in ready:
            eid = r.get("event_id", "?")
            for field in ["event_id", "post", "observed_at", "source_mode"]:
                val = r.get(field)
                ok = bool(val) if not isinstance(val, bool) else True
                if not ok:
                    results.append((False, f"FAIL: ready item {eid} missing field '{field}'"))

        # Check that ready items have observed_at (must not be empty)
        for r in ready:
            obs = str(r.get("observed_at") or "").strip()
            if not obs:
                results.append((False, f"FAIL: ready item {r.get('event_id')} has empty observed_at"))

    # ── summary ────────────────────────────────────────────────────
    passed = sum(1 for ok, _ in results if ok)
    failed = sum(1 for ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"X v2-007a Rescue Tests: {passed}/{total} PASSED, {failed} FAILED")
    print(f"{'='*60}\n")
    for ok, msg in results:
        print(f"  [{('PASS' if ok else 'FAIL')}] {msg}")

    print(f"\n{'='*60}")
    if failed == 0:
        print("ALL TESTS PASSED")
        return 0
    else:
        print(f"{failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
