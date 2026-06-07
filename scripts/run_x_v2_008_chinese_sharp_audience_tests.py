#!/usr/bin/env python3
"""X v2-008 Chinese Sharp Audience Tests — 验证锐评风输出完整性。

检查 14 项约束。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BANNED = ["耐人寻味", "懂得都懂", "懂的都懂", "水很深", "你品你细品",
          "值得关注", "引发市场关注", "基础设施", "基本常识", "良性竞争"]
HARD = ["已经被架空", "明确利益输送", "最大受益者已经坐实", "官方砸盘",
        "以太坊要凉", "项目方跑路", "必然", "毫无疑问", "已坐实"]
INVESTMENT = ["买入", "卖出", "做多", "做空", "梭哈", "满仓", "抄底", "逃顶",
              "必涨", "必跌", "翻倍", "十倍", "百倍"]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_text(item: dict[str, Any]) -> str:
    """排除 original_post（旧版原文仅供引用参考，不参与禁止词检查）。"""
    rh = item.get("reply_hot_take") if isinstance(item.get("reply_hot_take"), dict) else {}
    return " ".join([
        str(item.get("personal_sharp") or ""),
        str(item.get("personal_balanced") or ""),
        str(rh.get("sarcastic") or ""),
        str(rh.get("sharp_but_safe") or ""),
        str(rh.get("og_explainer") or ""),
    ])


def main() -> int:
    root = _project_root()
    reports_dir = root / "reports"
    results: list[tuple[bool, str]] = []

    report_json = reports_dir / "x_v2_008_chinese_sharp_audience_report.json"
    queue_json = reports_dir / "x_v2_008_chinese_sharp_test_account_queue.json"

    # 1. report exists
    for p, lbl in [(report_json, "v2-008 sharp report"), (queue_json, "v2-008 sharp queue")]:
        ok = p.exists()
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {lbl} exists={ok}"))

    if not queue_json.exists():
        print("FAIL: queue missing")
        return 1

    queue = _read_json(queue_json)
    ready = queue.get("READY_FOR_TEST_ACCOUNT") if isinstance(queue.get("READY_FOR_TEST_ACCOUNT"), list) else []

    # 2. report exists check (done above)
    # 3. queue exists check (done above)

    # 4. READY 内容 audience_context_score >= 8
    for r in ready:
        score = r.get("audience_context_score", 0)
        ok = score >= 8
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {r.get('event_id')} audience={score} >= 8"))

    # 5. READY 内容 sharpness_score >= 8
    for r in ready:
        score = r.get("sharpness_score", 0)
        ok = score >= 8
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {r.get('event_id')} sharpness={score} >= 8"))

    # 6. READY 内容不含未解释的 EF/Lubin/Consensys
    jargon_terms = ["EF", "Lubin", "Consensys"]
    for r in ready:
        eid = r.get("event_id", "?")
        text = _all_text(r)
        entities_str = " ".join(str(e) for e in r.get("entities_explained", []))
        for term in jargon_terms:
            if term in text and term not in entities_str:
                results.append((False, f"FAIL: {eid} has '{term}' in text but not in entities_explained"))
                break
        else:
            results.append((True, f"PASS: {eid} jargon explained"))

    # 7. READY 内容不含禁止词
    for r in ready:
        eid = r.get("event_id", "?")
        text = _all_text(r)
        found = [w for w in BANNED if w in text]
        ok = len(found) == 0
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {eid} banned_words={found}"))

    # 8. READY 内容不含投资建议
    for r in ready:
        eid = r.get("event_id", "?")
        text = _all_text(r)
        found = [w for w in INVESTMENT if w in text]
        ok = len(found) == 0
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {eid} investment_words={found}"))

    # 9. READY 内容不含硬断言/造谣词
    for r in ready:
        eid = r.get("event_id", "?")
        text = _all_text(r)
        found = [w for w in HARD if w in text]
        ok = len(found) == 0
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {eid} hard_assertions={found}"))

    # 10-14. Safety
    report = _read_json(report_json) if report_json.exists() else {}
    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    safety.update(queue.get("safety") if isinstance(queue.get("safety"), dict) else {})

    for key, expected in [
        ("x_published", False), ("x_api_connected", False), ("production_write", False),
        ("daemon_started", False), ("article_project_modified", False), ("credential_exposed", False),
    ]:
        val = safety.get(key)
        ok = val == expected
        results.append((ok, f"{'PASS' if ok else 'FAIL'}: {key}={val} (expected {expected})"))

    # 15. model_calls <= 6
    calls = report.get("model_calls_made", -1)
    ok = calls <= 6
    results.append((ok, f"{'PASS' if ok else 'FAIL'}: model_calls_made={calls} <= 6"))

    # summary
    passed = sum(1 for ok, _ in results if ok)
    failed = sum(1 for ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"X v2-008 Chinese Sharp Tests: {passed}/{total} PASSED, {failed} FAILED")
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
