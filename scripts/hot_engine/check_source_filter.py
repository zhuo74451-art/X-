from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_trump_source_cfg() -> dict[str, Any]:
    path = _project_root() / "configs" / "hot_sources" / "trump_chinese_macro_sources.json"
    obj = _read_json(path)
    if not isinstance(obj, dict):
        return {}
    items = obj.get("sources")
    if not isinstance(items, list):
        return {}
    for x in items:
        if isinstance(x, dict) and str(x.get("source_id") or "") == "x_trumpchinese1":
            return x
    return {}


def _load_sensitive_filter() -> dict[str, Any]:
    path = _project_root() / "configs" / "source_filters" / "source_sensitive_filter.json"
    obj = _read_json(path)
    return obj if isinstance(obj, dict) else {}


def _match_any(text: str, needles: list[str]) -> str:
    t = text or ""
    for n in needles:
        if not n:
            continue
        if n in t:
            return n
        if n.lower() in t.lower():
            return n
    return ""


def apply_source_sensitive_filter(*, source_id: str, handle: str, text: str) -> dict[str, Any]:
    cfg = _load_trump_source_cfg() if source_id == "x_trumpchinese1" else {}

    out: dict[str, Any] = {
        "source_id": source_id,
        "handle": handle,
        "pipeline_stage": "traffic_signal",
        "source_role": str(cfg.get("source_role") or "traffic_signal"),
        "source_category": str(cfg.get("source_category") or "trump_chinese_macro"),
        "trust_level": str(cfg.get("trust_level") or "medium_low"),
        "needs_verification": bool(cfg.get("needs_verification", True)),
        "publish_as_source": bool(cfg.get("publish_as_source", False)),
        "source_filter_status": "allowed",
        "block_reason": "",
        "allowed_use": ["hot_discovery", "scoring_only", "queued_verification"],
        "blocked_use": ["fact_source", "direct_quote", "content_generation", "visual_generation", "auto_publish"],
    }

    if source_id != "x_trumpchinese1":
        return out

    f = _load_sensitive_filter()
    srcs = f.get("sources") if isinstance(f.get("sources"), dict) else {}
    s = srcs.get(source_id) if isinstance(srcs.get(source_id), dict) else {}
    cats = s.get("categories") if isinstance(s.get("categories"), dict) else {}

    for cat, words in cats.items():
        if not isinstance(words, list):
            continue
        hit = _match_any(text, [str(x) for x in words])
        if hit:
            out["source_filter_status"] = "blocked"
            out["block_reason"] = f"source_sensitive_filter:{cat}"
            out["matched_keyword"] = hit
            out["allowed_use"] = ["log_only"]
            out["blocked_use"] = ["hot_engine", "content_generation", "visual_generation", "auto_publish", "fact_source", "direct_quote"]
            return out

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--handle", required=True)
    ap.add_argument("--text", default="")
    ap.add_argument("--text-file", default="")
    args = ap.parse_args()

    text = args.text
    if str(args.text_file or "").strip():
        p = Path(str(args.text_file)).expanduser()
        if not p.is_absolute():
            p = _project_root() / p
        try:
            text = p.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            text = ""

    r = apply_source_sensitive_filter(source_id=args.source_id, handle=args.handle, text=text)
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
