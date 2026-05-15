from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapters.import_integration_api import fetch_pool, normalize_to_hot_input


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=["ready", "published"], required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--since", type=str, default="")
    ap.add_argument("--source", type=str, default="")
    ap.add_argument("--content_type", type=str, default="")
    ap.add_argument("--q", type=str, default="")
    args = ap.parse_args()

    try:
        items = fetch_pool(
            pool=args.pool,
            limit=args.limit,
            offset=args.offset,
            since=args.since or None,
            source=args.source or None,
            content_type=args.content_type or None,
            q=args.q or None,
        )
    except RuntimeError as e:
        print(f"[test_import_integration_api] fetch_failed pool={args.pool} error={e}")
        print("[test_import_integration_api] 请确认 Integration Read API 已启动：http://127.0.0.1:8001")
        raise SystemExit(2)
    hot_inputs = [normalize_to_hot_input(x) for x in items]

    print(f"[test_import_integration_api] pool={args.pool} fetched={len(items)} normalized={len(hot_inputs)}")
    for i, hi in enumerate(hot_inputs[:3], start=1):
        print(f"\n--- hot_input {i} ---")
        print(json.dumps(hi, ensure_ascii=False, indent=2))

    root = _project_root()
    out_dir = root / "out" / "integration_samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.pool}_hot_inputs.json"
    out_path.write_text(json.dumps(hot_inputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[test_import_integration_api] saved={out_path}")


if __name__ == "__main__":
    main()

