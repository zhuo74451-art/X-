from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            j = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(j, dict):
            out.append(j)
    return out


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    root = _project_root()
    log_dir = root / "out" / "publish_logs"
    published_path = log_dir / "published_posts.jsonl"
    dryrun_path = log_dir / "dryrun_posts.jsonl"
    blocked_legacy_path = log_dir / "blocked_legacy.jsonl"

    rows = _read_jsonl(published_path)
    kept_published: list[dict[str, Any]] = []
    moved_would: list[dict[str, Any]] = []
    moved_blocked: list[dict[str, Any]] = []

    for r in rows:
        st = str(r.get("status") or "").strip()
        if st == "published":
            kept_published.append(r)
        elif st == "would_publish":
            moved_would.append(r)
        elif st == "blocked":
            moved_blocked.append(r)
        else:
            moved_blocked.append({**r, "_note": "unknown_status_moved_to_blocked_legacy"})

    backup_dir = log_dir / "backups"
    backup_path = backup_dir / f"published_posts_{_utc_stamp()}.jsonl"
    if published_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(published_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        backup_path = backup_dir / f"published_posts_{_utc_stamp()}_missing.jsonl"

    _append_jsonl(dryrun_path, moved_would)
    _append_jsonl(blocked_legacy_path, moved_blocked)
    _write_jsonl(published_path, kept_published)

    print("[cleanup_publish_logs] ok")
    print(f"- kept_published: {len(kept_published)}")
    print(f"- moved_would_publish: {len(moved_would)}")
    print(f"- moved_blocked: {len(moved_blocked)}")
    print(f"- backup_path: {backup_path}")


if __name__ == "__main__":
    main()

