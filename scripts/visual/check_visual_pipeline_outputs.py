from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _require(cond: bool, msg: str, errors: list[str]) -> None:
    if not cond:
        errors.append(msg)


def _is_nonempty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def main() -> None:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--run-dir", required=True)
    ns = ap.parse_args()

    run_dir = Path(ns.run_dir)
    errors: list[str] = []

    required_files = [
        "input_raw.txt",
        "input_normalized.json",
        "extracted_facts.json",
        "route_decision.json",
        "image_text_pack.json",
        "prompt_pack.json",
        "validation_checklist.json",
        "audit_report.md",
        "ready_to_generate_prompt.md",
    ]

    for fn in required_files:
        _require((run_dir / fn).exists(), f"missing_file:{fn}", errors)

    if errors:
        for e in errors:
            print(e)
        raise SystemExit(2)

    try:
        route_decision = _read_json(run_dir / "route_decision.json")
    except Exception as e:
        print(f"route_decision.json_parse_error:{e}")
        raise SystemExit(2)

    _require(isinstance(route_decision, dict), "route_decision_not_object", errors)
    if isinstance(route_decision, dict):
        _require(_is_nonempty_str(route_decision.get("selected_route")), "route_decision.missing:selected_route", errors)
        _require(isinstance(route_decision.get("scores"), dict), "route_decision.missing:scores", errors)
        _require(isinstance(route_decision.get("reason_by_rule"), list), "route_decision.missing:reason_by_rule", errors)

    try:
        image_text_pack = _read_json(run_dir / "image_text_pack.json")
    except Exception as e:
        print(f"image_text_pack.json_parse_error:{e}")
        raise SystemExit(2)

    _require(isinstance(image_text_pack, dict), "image_text_pack_not_object", errors)
    if isinstance(image_text_pack, dict):
        _require(_is_nonempty_str(image_text_pack.get("title")), "image_text_pack.missing:title", errors)
        _require(_is_nonempty_str(image_text_pack.get("subtitle")), "image_text_pack.missing:subtitle", errors)
        _require(isinstance(image_text_pack.get("blocks"), list), "image_text_pack.missing:blocks", errors)
        _require(_is_nonempty_str(image_text_pack.get("footer")), "image_text_pack.missing:footer", errors)
        _require(isinstance(image_text_pack.get("source_trace"), list), "image_text_pack.missing:source_trace", errors)

    try:
        prompt_pack = _read_json(run_dir / "prompt_pack.json")
    except Exception as e:
        print(f"prompt_pack.json_parse_error:{e}")
        raise SystemExit(2)

    _require(isinstance(prompt_pack, dict), "prompt_pack_not_object", errors)
    if isinstance(prompt_pack, dict):
        _require(_is_nonempty_str(prompt_pack.get("route")), "prompt_pack.missing:route", errors)
        _require(_is_nonempty_str(prompt_pack.get("size")), "prompt_pack.missing:size", errors)
        _require(_is_nonempty_str(prompt_pack.get("style_profile_used")), "prompt_pack.missing:style_profile_used", errors)
        _require(isinstance(prompt_pack.get("visual_methods"), list), "prompt_pack.missing:visual_methods", errors)
        _require(isinstance(prompt_pack.get("x_adaptation"), dict), "prompt_pack.missing:x_adaptation", errors)
        pvs = prompt_pack.get("prompt_variants")
        _require(isinstance(pvs, dict), "prompt_pack.missing:prompt_variants", errors)
        if isinstance(pvs, dict):
            _require(_is_nonempty_str(pvs.get("render_safe_prompt_cn")), "prompt_pack.prompt_variants.missing:render_safe_prompt_cn", errors)
            _require(_is_nonempty_str(pvs.get("standard_prompt_cn")), "prompt_pack.prompt_variants.missing:standard_prompt_cn", errors)
        _require(_is_nonempty_str(prompt_pack.get("negative_prompt")), "prompt_pack.missing:negative_prompt", errors)
        _require(isinstance(prompt_pack.get("guardrails"), list), "prompt_pack.missing:guardrails", errors)
        _require(isinstance(prompt_pack.get("preferred_generation_order"), list), "prompt_pack.missing:preferred_generation_order", errors)

    try:
        vchk = _read_json(run_dir / "validation_checklist.json")
    except Exception as e:
        print(f"validation_checklist.json_parse_error:{e}")
        raise SystemExit(2)

    _require(isinstance(vchk, dict), "validation_checklist_not_object", errors)
    if isinstance(vchk, dict):
        _require(isinstance(vchk.get("text_check"), list), "validation_checklist.missing:text_check", errors)
        _require(isinstance(vchk.get("risk_check"), list), "validation_checklist.missing:risk_check", errors)
        _require(isinstance(vchk.get("visual_check"), list), "validation_checklist.missing:visual_check", errors)

    if errors:
        for e in errors:
            print(e)
        raise SystemExit(2)

    print("VISUAL_PIPELINE_CHECK_PASS")


if __name__ == "__main__":
    main()

