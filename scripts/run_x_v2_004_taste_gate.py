from __future__ import annotations

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


def _find_violations(text: str) -> list[str]:
    s = text or ""

    banned_phrases = [
        "值得关注",
        "引发市场关注",
        "总的来说",
        "综上",
        "让我们深入",
        "在 Web3 快速发展的世界里",
        "这反映出",
        "这意味着",
        "Exciting news",
        "In conclusion",
    ]

    v: list[str] = []
    for p in banned_phrases:
        if p in s:
            v.append(f"banned_phrase:{p}")

    if re.search(r"(?m)^\s*[-*]\s+\S+", s):
        v.append("markdown_list_detected")

    emojis = re.findall(r"[\U0001F300-\U0001FAFF]", s)
    if len(emojis) >= 2:
        v.append("multiple_emojis_detected")

    if re.search(r"(?i)\b(buy|sell|long|short)\b", s):
        v.append("explicit_buy_sell_en")
    if re.search(r"(?i)(喊单|抄底|梭哈|稳赚|必涨|必跌|买入|卖出|做多|做空)", s):
        v.append("explicit_buy_sell_zh")

    return v


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    src = reports_dir / "x_v2_004_final_dryrun_candidates.json"
    if not src.exists():
        raise SystemExit(2)

    data = _read_json(src)
    items = data.get("items") if isinstance(data.get("items"), list) else []

    results: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("status") or "") != "APPROVED_FOR_X_DRYRUN":
            continue
        eid = str(it.get("event_id") or "")
        content = it.get("content") if isinstance(it.get("content"), dict) else {}
        personal = str(content.get("personal_post") or "")
        ra = content.get("reply_angle") if isinstance(content.get("reply_angle"), dict) else {}
        aggressive = str(ra.get("aggressive") or "")
        sarcastic = str(ra.get("sarcastic") or "")
        og = str(ra.get("og_explainer") or "")

        merged = "\n".join([personal, aggressive, sarcastic, og])
        violations = _find_violations(merged)
        results.append(
            {
                "event_id": eid,
                "passed": len(violations) == 0,
                "violations": violations,
            }
        )

    failed = [x for x in results if x.get("passed") is not True]
    report = {
        "task_id": "x_v2_004_dryrun_export_and_rewrite",
        "generated_at_utc": _utc_now_iso(),
        "approved_checked": len(results),
        "passed": len(failed) == 0,
        "failed": failed,
        "results": results,
    }
    _write_json(reports_dir / "x_v2_004_taste_gate_report.json", report)

    lines: list[str] = []
    lines.append("# X v2-004 Taste Gate Report\n\n")
    lines.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    lines.append(f"- approved_checked: {report.get('approved_checked')}\n")
    lines.append(f"- passed: {str(report.get('passed')).lower()}\n\n")
    lines.append("## Failed\n")
    if not failed:
        lines.append("- (none)\n")
    else:
        for x in failed:
            lines.append(f"- {x.get('event_id')}: {json.dumps(x.get('violations') or [], ensure_ascii=False)}\n")
    (reports_dir / "x_v2_004_taste_gate_report.md").write_text("".join(lines), encoding="utf-8")

    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

