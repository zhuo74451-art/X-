#!/usr/bin/env python3
"""X v2-007b Manual Draft Review Pack Tests — 验证导出包完整性。

检查：
- pack exists (json + md)
- approved_count == 2
- 每条都有 source_url / observed_at
- x_published=false
- x_api_connected=false
- production_write=false
- model_calls_made=0
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


def main() -> int:
    root = _project_root()
    reports_dir = root / "reports"
    results: list[tuple[bool, str]] = []

    pack_json = reports_dir / "x_v2_007b_manual_draft_review_pack.json"
    pack_md = reports_dir / "x_v2_007b_manual_draft_review_pack.md"

    # 1. pack exists
    for p, lbl in [(pack_json, "review pack (json)"), (pack_md, "review pack (md)")]:
        ok = p.exists()
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {lbl} exists={ok}"))

    if not pack_json.exists():
        print("FAIL: pack json missing, cannot continue")
        return 1

    pack = _read_json(pack_json)

    # 2. approved_count == 2
    count = pack.get("approved_count", 0)
    ok = count == 2
    results.append((ok, f"{'PASS' if ok else 'FAIL'}: approved_count={count} (expected 2)"))

    # 3. model_calls_made == 0
    calls = pack.get("model_calls_made", -1)
    ok = calls == 0
    results.append((ok, f"{'PASS' if ok else 'FAIL'}: model_calls_made={calls} (expected 0)"))

    # 4. each item has source_url / observed_at
    items = pack.get("items") if isinstance(pack.get("items"), list) else []
    for it in items:
        eid = it.get("event_id", "?")
        for field in ["source_url", "observed_at", "post"]:
            val = it.get(field)
            has = bool(val) if not isinstance(val, bool) else True
            results.append((has, f"{'PASS' if has else 'FAIL'}: item {eid} has {field}"))

        # Check reply_hot_take fields exist
        for rk in ["reply_hot_take_sarcastic", "reply_hot_take_sharp_but_safe", "reply_hot_take_og_explainer"]:
            val = it.get(rk)
            has = bool(val is not None)
            results.append((has, f"{'PASS' if has else 'FAIL'}: item {eid} has {rk}"))

    # 5. safety flags
    safety = pack.get("safety") if isinstance(pack.get("safety"), dict) else {}
    safety_checks = [
        ("x_published", False),
        ("x_api_connected", False),
        ("production_write", False),
        ("daemon_started", False),
        ("article_project_modified", False),
        ("credential_exposed", False),
    ]
    for key, expected in safety_checks:
        val = safety.get(key)
        ok = val == expected
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {key}={val} (expected {expected})"))

    # summary
    passed = sum(1 for ok, _ in results if ok)
    failed = sum(1 for ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"X v2-007b Review Pack Tests: {passed}/{total} PASSED, {failed} FAILED")
    print(f"{'='*60}\n")
    for ok, msg in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")

    print(f"\n{'='*60}")
    if failed == 0:
        print("ALL TESTS PASSED")
        return 0
    else:
        print(f"{failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
