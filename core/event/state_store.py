from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_update TEXT NOT NULL,
  signal_count INTEGER NOT NULL DEFAULT 1,
  source_diversity INTEGER NOT NULL DEFAULT 1,
  fact_anchor TEXT NOT NULL,
  entities_json TEXT NOT NULL DEFAULT '[]',
  heat_score INTEGER NOT NULL DEFAULT 0,
  heat_velocity REAL NOT NULL DEFAULT 0,
  risk_level TEXT NOT NULL DEFAULT 'medium',
  risk_flags_json TEXT NOT NULL DEFAULT '[]',
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_actions (
  action_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  account TEXT NOT NULL DEFAULT '',
  content_package_id TEXT NOT NULL DEFAULT '',
  publish_status TEXT NOT NULL DEFAULT 'draft',
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_actions_event_id ON event_actions(event_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def to_json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def from_json(value: str) -> Any:
    try:
        return json.loads(value or "[]")
    except json.JSONDecodeError:
        return []


def row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    obj = dict(row)
    obj["entities"] = from_json(obj.pop("entities_json", "[]"))
    obj["risk_flags"] = from_json(obj.pop("risk_flags_json", "[]"))
    return obj


def upsert_event(conn: sqlite3.Connection, event: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO events (
          event_id,title,status,first_seen,last_update,signal_count,source_diversity,
          fact_anchor,entities_json,heat_score,heat_velocity,risk_level,risk_flags_json,
          summary,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(event_id) DO UPDATE SET
          title=excluded.title,
          status=excluded.status,
          last_update=excluded.last_update,
          signal_count=excluded.signal_count,
          source_diversity=excluded.source_diversity,
          fact_anchor=excluded.fact_anchor,
          entities_json=excluded.entities_json,
          heat_score=excluded.heat_score,
          heat_velocity=excluded.heat_velocity,
          risk_level=excluded.risk_level,
          risk_flags_json=excluded.risk_flags_json,
          summary=excluded.summary,
          updated_at=excluded.updated_at
        """,
        (
            event["event_id"],
            event.get("title", ""),
            event.get("status", "emerging"),
            event.get("first_seen"),
            event.get("last_update"),
            int(event.get("signal_count") or 1),
            int(event.get("source_diversity") or 1),
            event.get("fact_anchor", "single_source"),
            to_json(event.get("entities") or []),
            int(event.get("heat_score") or 0),
            float(event.get("heat_velocity") or 0),
            event.get("risk_level", "medium"),
            to_json(event.get("risk_flags") or []),
            event.get("summary", ""),
            event.get("created_at"),
            event.get("updated_at"),
        ),
    )
    conn.commit()


def list_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM events ORDER BY heat_score DESC, updated_at DESC").fetchall()
    return [row_to_event(r) for r in rows]


def get_event(conn: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
    return row_to_event(row) if row else None


def add_action(conn: sqlite3.Connection, action: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO event_actions (
          action_id,event_id,action_type,account,content_package_id,publish_status,reason,created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            action["action_id"],
            action["event_id"],
            action["action_type"],
            action.get("account", ""),
            action.get("content_package_id", ""),
            action.get("publish_status", "draft"),
            action.get("reason", ""),
            action["created_at"],
        ),
    )
    conn.commit()


def list_actions(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM event_actions WHERE event_id=? ORDER BY created_at DESC", (event_id,)
    ).fetchall()
    return [dict(r) for r in rows]
