from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _safe_read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parsed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, line in enumerate(_read_text(path).splitlines(), start=1):
        s = (line or "").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            errors.append({"line": idx, "error": f"json_decode_error: {str(e)}"})
            continue
        if not isinstance(obj, dict):
            errors.append({"line": idx, "error": "not_an_object"})
            continue
        parsed.append(obj)
    return parsed, errors


def _is_str_list(x: Any) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)


def _validate_source_pack_item(x: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(x, dict):
        return ["source_pack_item_not_object"]
    for k in ["title", "url", "source_type", "facts_supported"]:
        if k not in x:
            errs.append(f"source_pack_item_missing:{k}")
    if "title" in x and not isinstance(x.get("title"), str):
        errs.append("source_pack_item_title_not_string")
    if "url" in x and not isinstance(x.get("url"), str):
        errs.append("source_pack_item_url_not_string")
    if "facts_supported" in x and not _is_str_list(x.get("facts_supported")):
        errs.append("source_pack_item_facts_supported_not_string_list")
    st = x.get("source_type")
    if "source_type" in x and not isinstance(st, str):
        errs.append("source_pack_item_source_type_not_string")
    elif isinstance(st, str):
        if st not in {"official", "data_platform", "tier1_media", "community", "unknown"}:
            errs.append("source_pack_item_source_type_invalid_enum")
    return errs


def _validate_image_candidate(x: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(x, dict):
        return ["image_candidate_not_object"]
    for k in ["url", "kind", "usable_for_x"]:
        if k not in x:
            errs.append(f"image_candidate_missing:{k}")
    if "url" in x and not isinstance(x.get("url"), str):
        errs.append("image_candidate_url_not_string")
    kind = x.get("kind")
    if "kind" in x and not isinstance(kind, str):
        errs.append("image_candidate_kind_not_string")
    elif isinstance(kind, str):
        if kind not in {"cover", "chart", "screenshot", "logo", "unknown"}:
            errs.append("image_candidate_kind_invalid_enum")
    if "usable_for_x" in x and not isinstance(x.get("usable_for_x"), bool):
        errs.append("image_candidate_usable_for_x_not_boolean")
    return errs


def validate_shared_event(event: dict[str, Any]) -> list[str]:
    errs: list[str] = []

    def req_str(key: str) -> None:
        if key not in event:
            errs.append(f"missing:{key}")
            return
        if not isinstance(event.get(key), str) or not str(event.get(key) or "").strip():
            errs.append(f"invalid:{key}:not_nonempty_string")

    req_str("event_id")
    req_str("title")
    req_str("summary")

    et = event.get("event_type")
    if not isinstance(et, str):
        errs.append("invalid:event_type:not_string")
    else:
        if et not in {"hot", "industry_structure", "case_data_regulation", "whale", "macro", "project"}:
            errs.append("invalid:event_type:enum")

    if "assets" not in event:
        errs.append("missing:assets")
    elif not _is_str_list(event.get("assets")):
        errs.append("invalid:assets:not_string_list")

    sp = event.get("source_pack")
    if "source_pack" not in event:
        errs.append("missing:source_pack")
    elif not isinstance(sp, list):
        errs.append("invalid:source_pack:not_list")
    else:
        for i, item in enumerate(sp[:20], start=1):
            for e in _validate_source_pack_item(item):
                errs.append(f"source_pack[{i}]:{e}")

    fp = event.get("fact_pack")
    if "fact_pack" not in event:
        errs.append("missing:fact_pack")
    elif not isinstance(fp, dict):
        errs.append("invalid:fact_pack:not_object")
    else:
        for k in ["confirmed", "uncertain", "should_not_claim"]:
            if k not in fp:
                errs.append(f"fact_pack_missing:{k}")
            elif not _is_str_list(fp.get(k)):
                errs.append(f"fact_pack_invalid:{k}:not_string_list")

    rf = event.get("risk_flags")
    if "risk_flags" not in event:
        errs.append("missing:risk_flags")
    elif not _is_str_list(rf):
        errs.append("invalid:risk_flags:not_string_list")

    ic = event.get("image_candidates")
    if "image_candidates" not in event:
        errs.append("missing:image_candidates")
    elif not isinstance(ic, list):
        errs.append("invalid:image_candidates:not_list")
    else:
        for i, item in enumerate(ic[:20], start=1):
            for e in _validate_image_candidate(item):
                errs.append(f"image_candidates[{i}]:{e}")

    ro = event.get("recommended_outputs")
    if "recommended_outputs" not in event:
        errs.append("missing:recommended_outputs")
    elif not isinstance(ro, list) or not all(isinstance(x, str) for x in ro):
        errs.append("invalid:recommended_outputs:not_string_list")
    else:
        allowed = {"article", "x_post", "thread", "reply", "quote"}
        for x in ro:
            if x not in allowed:
                errs.append("invalid:recommended_outputs:enum")
                break

    rr = event.get("review_required")
    if "review_required" not in event:
        errs.append("missing:review_required")
    elif not isinstance(rr, bool):
        errs.append("invalid:review_required:not_boolean")

    return errs


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def shared_event_to_hot_input(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "").strip()
    title = str(event.get("title") or "").strip()
    summary = str(event.get("summary") or "").strip()
    fp = event.get("fact_pack") if isinstance(event.get("fact_pack"), dict) else {}
    confirmed = fp.get("confirmed") if isinstance(fp.get("confirmed"), list) else []
    confirmed = [str(x) for x in confirmed if isinstance(x, str) and x.strip()]
    raw_text = summary
    if confirmed:
        raw_text = summary + "\n" + "\n".join(confirmed)

    sp = event.get("source_pack") if isinstance(event.get("source_pack"), list) else []
    source_url = ""
    if sp and isinstance(sp[0], dict):
        source_url = str(sp[0].get("url") or "").strip()

    return {
        "input_id": event_id,
        "source_name": "shared_hotspot_core",
        "title": title,
        "summary": summary,
        "raw_text": raw_text,
        "source_url": source_url,
        "created_at": "",
        "asset_symbols": event.get("assets") if isinstance(event.get("assets"), list) else [],
        "risk_flags": event.get("risk_flags") if isinstance(event.get("risk_flags"), list) else [],
        "recommended_outputs": event.get("recommended_outputs") if isinstance(event.get("recommended_outputs"), list) else [],
        "event_type": str(event.get("event_type") or "").strip(),
        "source_pack": event.get("source_pack") if isinstance(event.get("source_pack"), list) else [],
        "fact_pack": fp,
        "image_candidates": event.get("image_candidates") if isinstance(event.get("image_candidates"), list) else [],
        "review_required": bool(event.get("review_required")) if isinstance(event.get("review_required"), bool) else True,
    }


def _detect_placeholder_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return False
    if "example.com" in u:
        return True
    if "placeholder" in u:
        return True
    return False


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_report(out_dir: Path, report: dict[str, Any]) -> None:
    (out_dir / "import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Shared Event Pack Import Report\n\n")
    lines.append(f"- generated_at_utc: {report.get('generated_at_utc')}\n")
    lines.append(f"- input_path: {report.get('input_path')}\n")
    lines.append(f"- out_events_jsonl: {report.get('out_events_jsonl')}\n")
    lines.append(f"- input_lines: {report.get('input_lines')}\n")
    lines.append(f"- parsed_events: {report.get('parsed_events')}\n")
    lines.append(f"- valid_events: {report.get('valid_events')}\n")
    lines.append(f"- invalid_events: {report.get('invalid_events')}\n")
    lines.append(f"- written_hot_inputs: {report.get('written_hot_inputs')}\n")

    warns = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    lines.append("\n## Warnings\n")
    if not warns:
        lines.append("- (none)\n")
    else:
        for w in warns[:50]:
            lines.append(f"- {str(w)}\n")

    errs = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines.append("\n## Errors\n")
    if not errs:
        lines.append("- (none)\n")
    else:
        for e in errs[:50]:
            lines.append(f"- {json.dumps(e, ensure_ascii=False)}\n")
        if len(errs) > 50:
            lines.append(f"- ... and {len(errs) - 50} more\n")

    (out_dir / "import_report.md").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="event_pack.jsonl path (relative to project root or absolute)")
    ap.add_argument("--out", required=True, help="output events.jsonl path (relative to project root or absolute)")
    args = ap.parse_args()

    root = _project_root()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = root / input_path
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path

    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed, read_errors = _safe_read_jsonl(input_path)

    valid_events: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, ev in enumerate(parsed, start=1):
        errs = validate_shared_event(ev)
        if errs:
            invalid.append({"index": idx, "event_id": str(ev.get("event_id") or ""), "errors": errs})
            continue
        sp0_url = ""
        sp = ev.get("source_pack") if isinstance(ev.get("source_pack"), list) else []
        if sp and isinstance(sp[0], dict):
            sp0_url = str(sp[0].get("url") or "").strip()
        if _detect_placeholder_url(sp0_url):
            warnings.append(f"placeholder_url_detected event_id={str(ev.get('event_id') or '').strip()} url={_clip(sp0_url, 120)}")
        valid_events.append(ev)

    hot_inputs = [shared_event_to_hot_input(e) for e in valid_events]
    _write_jsonl(out_path, hot_inputs)

    report = {
        "task_id": "x_v2_002_shared_event_pack_adapter",
        "generated_at_utc": _utc_now_iso(),
        "input_path": str(input_path),
        "out_events_jsonl": str(out_path),
        "input_lines": len([x for x in _read_text(input_path).splitlines() if (x or '').strip()]),
        "parsed_events": len(parsed),
        "valid_events": len(valid_events),
        "invalid_events": len(invalid),
        "written_hot_inputs": len(hot_inputs),
        "warnings": warnings,
        "errors": read_errors + invalid,
        "safety": {
            "network_used": False,
            "paid_model_called": False,
            "x_published": False,
            "source_file_modified": False
        }
    }
    _write_report(out_dir, report)

    if invalid or read_errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

