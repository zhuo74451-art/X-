from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _req(cond: bool, msg: str, errs: list[str]) -> None:
    if not cond:
        errs.append(msg)


def main() -> None:
    errs: list[str] = []
    routes = list("ABCDEFGHI")

    profiles_path = ROOT / "configs" / "visual_style_profiles.json"
    registry_path = ROOT / "configs" / "visual_route_registry.json"
    templates_dir = ROOT / "templates" / "visual_routes"

    _req(profiles_path.exists(), "missing:configs/visual_style_profiles.json", errs)
    _req(registry_path.exists(), "missing:configs/visual_route_registry.json", errs)
    _req(templates_dir.exists(), "missing:templates/visual_routes", errs)

    if errs:
        for e in errs:
            print(e)
        raise SystemExit(2)

    profiles = _read_json(profiles_path)
    registry = _read_json(registry_path)

    _req(isinstance(profiles, dict), "profiles_not_object", errs)
    _req(isinstance(registry, dict), "registry_not_object", errs)

    if not isinstance(profiles, dict) or not isinstance(registry, dict):
        for e in errs:
            print(e)
        raise SystemExit(2)

    for r in routes:
        p = profiles.get(r)
        _req(isinstance(p, dict), f"profile_missing_or_invalid:{r}", errs)
        if isinstance(p, dict):
            _req(isinstance(p.get("visual_methods"), list) and len(p.get("visual_methods")) >= 2, f"profile.{r}.missing:visual_methods", errs)
            _req(isinstance(p.get("open_fields"), list) and len(p.get("open_fields")) >= 2, f"profile.{r}.missing:open_fields", errs)
            _req(isinstance(p.get("do_not_hardcode"), list) and len(p.get("do_not_hardcode")) >= 2, f"profile.{r}.missing:do_not_hardcode", errs)
            _req(isinstance(p.get("x_adaptation"), dict) and bool(p.get("x_adaptation")), f"profile.{r}.missing:x_adaptation", errs)

    for r in routes:
        reg = registry.get(r)
        _req(isinstance(reg, dict), f"registry_missing_or_invalid:{r}", errs)
        if not isinstance(reg, dict):
            continue
        sp = reg.get("style_profile")
        _req(isinstance(sp, str) and sp in profiles, f"registry.{r}.invalid:style_profile", errs)
        tmpl = reg.get("prompt_template")
        _req(isinstance(tmpl, str) and tmpl.strip() != "", f"registry.{r}.missing:prompt_template", errs)
        if isinstance(tmpl, str) and tmpl.strip():
            _req((templates_dir / tmpl).exists(), f"registry.{r}.missing_template_file:{tmpl}", errs)

    if errs:
        for e in errs:
            print(e)
        raise SystemExit(2)

    print("VISUAL_STYLE_PROFILES_CHECK_PASS")


if __name__ == "__main__":
    main()

