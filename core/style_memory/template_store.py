from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS style_templates (
  template_id TEXT PRIMARY KEY,
  account TEXT NOT NULL,
  topic_domain TEXT NOT NULL,
  pattern TEXT NOT NULL,
  hook_type TEXT NOT NULL,
  persona_voice TEXT NOT NULL DEFAULT '',
  sample_size INTEGER NOT NULL DEFAULT 0,
  avg_engagement_rate REAL NOT NULL DEFAULT 0,
  vs_baseline REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'testing',
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT ''
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_template(conn: sqlite3.Connection, tpl: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO style_templates (
          template_id,account,topic_domain,pattern,hook_type,persona_voice,
          sample_size,avg_engagement_rate,vs_baseline,status,notes,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(template_id) DO UPDATE SET
          account=excluded.account,
          topic_domain=excluded.topic_domain,
          pattern=excluded.pattern,
          hook_type=excluded.hook_type,
          persona_voice=excluded.persona_voice,
          sample_size=excluded.sample_size,
          avg_engagement_rate=excluded.avg_engagement_rate,
          vs_baseline=excluded.vs_baseline,
          status=excluded.status,
          notes=excluded.notes,
          updated_at=excluded.updated_at
        """,
        (
            tpl["template_id"],
            tpl.get("account", "coinmeta_official"),
            tpl.get("topic_domain", "general"),
            tpl.get("pattern", ""),
            tpl.get("hook_type", "context"),
            tpl.get("persona_voice", ""),
            int(tpl.get("sample_size") or 0),
            float(tpl.get("avg_engagement_rate") or 0),
            float(tpl.get("vs_baseline") or 0),
            tpl.get("status", "testing"),
            tpl.get("notes", ""),
            tpl.get("updated_at", ""),
        ),
    )
    conn.commit()


def list_templates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM style_templates ORDER BY status, vs_baseline DESC").fetchall()
    return [dict(r) for r in rows]


def get_template(conn: sqlite3.Connection, template_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM style_templates WHERE template_id=?", (template_id,)).fetchone()
    return dict(row) if row else None


def choose_template(conn: sqlite3.Connection, account: str, topic_domain: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM style_templates
        WHERE account=? AND topic_domain=? AND status IN ('validated','testing')
        ORDER BY status='validated' DESC, vs_baseline DESC, sample_size DESC
        LIMIT 1
        """,
        (account, topic_domain),
    ).fetchone()
    return dict(row) if row else None
