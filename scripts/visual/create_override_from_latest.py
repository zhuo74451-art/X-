from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    latest_path = ROOT / "out" / "visual_pipeline" / "latest_run.json"
    if not latest_path.exists():
        raise SystemExit("latest_run.json not found")

    latest = _read_json(latest_path)
    if not isinstance(latest, dict):
        raise SystemExit("latest_run.json invalid")

    run_dir = latest.get("run_dir")
    if not isinstance(run_dir, str) or not run_dir.strip():
        raise SystemExit("latest_run.json missing run_dir")

    image_pack_path = ROOT / run_dir / "image_text_pack.json"
    if not image_pack_path.exists():
        raise SystemExit(f"image_text_pack.json not found: {image_pack_path}")

    img = _read_json(image_pack_path)
    if not isinstance(img, dict):
        raise SystemExit("image_text_pack.json invalid")

    override = {
        "_usage": "复制本文件后改名使用。只填写想覆盖的字段；未填写的字段会保留自动结果。",
        "route": str(img.get("route") or ""),
        "title": str(img.get("title") or ""),
        "subtitle": str(img.get("subtitle") or ""),
        "blocks": img.get("blocks") if isinstance(img.get("blocks"), list) else [],
        "footer": str(img.get("footer") or "CoinMeta / 币界网"),
        "notes": "override_from_latest",
    }

    out_dir = ROOT / "data" / "visual_inbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_utc_ts()}_override_from_latest.json"
    out_path.write_text(json.dumps(override, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OVERRIDE_DRAFT_CREATED: {out_path.as_posix()}")


if __name__ == "__main__":
    main()

