from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_simple_yaml(path: Path) -> dict:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _content_hash(item: dict) -> str:
    payload = {
        "input_type": item.get("input_type") or "",
        "source_name": item.get("source_name") or "",
        "source_url": item.get("source_url") or "",
        "raw_text": item.get("raw_text") or "",
        "related_coinmeta_news_url": item.get("related_coinmeta_news_url") or "",
        "related_coinmeta_news_text": item.get("related_coinmeta_news_text") or "",
        "news_card_image": item.get("news_card_image") or "",
        "lang": item.get("lang") or "",
    }
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> None:
    root = _project_root()
    cfg = _load_simple_yaml(root / "config.yaml")
    db_path = root / (cfg.get("db_path") or "hot_follow.db")
    data_path = root / "data" / "sample_hot_inputs.json"

    items = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("sample_hot_inputs.json must be a JSON array")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    inserted = 0
    skipped = 0
    now = _utc_now_iso()

    for item in items:
        if not isinstance(item, dict):
            continue
        ch = _content_hash(item)
        exists = conn.execute(
            "SELECT 1 FROM hot_inputs WHERE content_hash = ? LIMIT 1;", (ch,)
        ).fetchone()
        if exists:
            skipped += 1
            continue

        conn.execute(
            """
            INSERT INTO hot_inputs (
              input_type, source_tool, source_name, source_url,
              raw_text, related_coinmeta_news_url, related_coinmeta_news_text,
              news_card_image, lang, content_hash, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?);
            """,
            (
                item.get("input_type"),
                item.get("source_tool"),
                item.get("source_name"),
                item.get("source_url"),
                item.get("raw_text"),
                item.get("related_coinmeta_news_url"),
                item.get("related_coinmeta_news_text"),
                item.get("news_card_image") or "",
                item.get("lang"),
                ch,
                now,
                now,
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()

    print(f"[import_sample_hot_inputs] ok inserted={inserted} skipped={skipped} db={db_path}")


if __name__ == "__main__":
    main()
