from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS post_metrics (
  post_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  template_id TEXT NOT NULL DEFAULT '',
  account TEXT NOT NULL DEFAULT '',
  posted_at TEXT NOT NULL DEFAULT '',
  impressions INTEGER NOT NULL DEFAULT 0,
  likes INTEGER NOT NULL DEFAULT 0,
  replies INTEGER NOT NULL DEFAULT 0,
  reposts INTEGER NOT NULL DEFAULT 0,
  bookmarks INTEGER NOT NULL DEFAULT 0,
  engagement_rate REAL NOT NULL DEFAULT 0,
  expected_metric TEXT NOT NULL DEFAULT '',
  self_score INTEGER NOT NULL DEFAULT 0,
  real_score INTEGER NOT NULL DEFAULT 0,
  self_score_vs_real TEXT NOT NULL DEFAULT '',
  lesson TEXT NOT NULL DEFAULT ''
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def engagement_rate(row: dict[str, Any]) -> float:
    impressions = int(row.get("impressions") or 0)
    if impressions <= 0:
        return 0.0
    total = sum(int(row.get(k) or 0) for k in ["likes", "replies", "reposts", "bookmarks"])
    return round(total / impressions, 6)


def real_score(row: dict[str, Any]) -> int:
    er = engagement_rate(row)
    replies = int(row.get("replies") or 0)
    bookmarks = int(row.get("bookmarks") or 0)
    return max(0, min(100, int(er * 1200 + min(20, replies) + min(20, bookmarks))))


def compare_scores(self_score: int, actual_score: int) -> str:
    if self_score >= 75 and actual_score < 45:
        return "overrated"
    if self_score < 60 and actual_score >= 70:
        return "underrated"
    if abs(self_score - actual_score) <= 15:
        return "matched"
    return "drifted"


def upsert_metric(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["engagement_rate"] = engagement_rate(item)
    item["real_score"] = real_score(item)
    item["self_score_vs_real"] = compare_scores(int(item.get("self_score") or 0), item["real_score"])
    conn.execute(
        """
        INSERT INTO post_metrics (
          post_id,event_id,template_id,account,posted_at,impressions,likes,replies,reposts,
          bookmarks,engagement_rate,expected_metric,self_score,real_score,self_score_vs_real,lesson
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(post_id) DO UPDATE SET
          event_id=excluded.event_id,
          template_id=excluded.template_id,
          account=excluded.account,
          posted_at=excluded.posted_at,
          impressions=excluded.impressions,
          likes=excluded.likes,
          replies=excluded.replies,
          reposts=excluded.reposts,
          bookmarks=excluded.bookmarks,
          engagement_rate=excluded.engagement_rate,
          expected_metric=excluded.expected_metric,
          self_score=excluded.self_score,
          real_score=excluded.real_score,
          self_score_vs_real=excluded.self_score_vs_real,
          lesson=excluded.lesson
        """,
        (
            item["post_id"], item["event_id"], item.get("template_id", ""), item.get("account", ""),
            item.get("posted_at", ""), int(item.get("impressions") or 0), int(item.get("likes") or 0),
            int(item.get("replies") or 0), int(item.get("reposts") or 0), int(item.get("bookmarks") or 0),
            float(item.get("engagement_rate") or 0), item.get("expected_metric", ""), int(item.get("self_score") or 0),
            int(item.get("real_score") or 0), item.get("self_score_vs_real", ""), item.get("lesson", ""),
        ),
    )
    conn.commit()
    return item


def list_metrics(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM post_metrics ORDER BY posted_at DESC, post_id DESC").fetchall()
    return [dict(r) for r in rows]


def metrics_by_template(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT template_id, account, COUNT(*) sample_size, AVG(engagement_rate) avg_engagement_rate, AVG(real_score) avg_real_score FROM post_metrics WHERE template_id != '' GROUP BY template_id, account ORDER BY avg_engagement_rate DESC"
    ).fetchall()
    return [dict(r) for r in rows]
