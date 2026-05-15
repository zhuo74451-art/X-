from __future__ import annotations

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


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {r[1] for r in rows}


def _ensure_hot_inputs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hot_inputs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          input_type TEXT NOT NULL,
          source_tool TEXT,
          source_name TEXT,
          source_url TEXT,
          raw_text TEXT NOT NULL,
          related_coinmeta_news_url TEXT,
          related_coinmeta_news_text TEXT,
          news_card_image TEXT,
          lang TEXT NOT NULL,
          content_hash TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'new',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )

    cols = _get_columns(conn, "hot_inputs")
    if "news_card_image" not in cols:
        conn.execute("ALTER TABLE hot_inputs ADD COLUMN news_card_image TEXT;")


def _recreate_hot_evaluations_if_needed(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hot_evaluations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          input_id INTEGER NOT NULL UNIQUE,
          is_hot_topic INTEGER,
          hotness_score INTEGER,
          algorithm_fit_score INTEGER,
          reply_potential_score INTEGER,
          retweet_potential_score INTEGER,
          dwell_time_score INTEGER,
          visual_potential_score INTEGER,
          coinmeta_angle_score INTEGER,
          fact_anchor_status TEXT,
          template_type TEXT,
          publish_mode TEXT,
          risk_level TEXT,
          safe_angle TEXT,
          do_not_write TEXT,
          interaction_trigger TEXT,
          recommended_post_type TEXT,
          evaluation_json TEXT,
          prompt_version TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY (input_id) REFERENCES hot_inputs(id)
        );
        """
    )

    cols = _get_columns(conn, "hot_evaluations")
    required = {
        "is_hot_topic",
        "algorithm_fit_score",
        "reply_potential_score",
        "retweet_potential_score",
        "dwell_time_score",
        "visual_potential_score",
        "coinmeta_angle_score",
        "fact_anchor_status",
        "interaction_trigger",
        "recommended_post_type",
    }
    if required.issubset(cols):
        return

    conn.execute("ALTER TABLE hot_evaluations RENAME TO hot_evaluations_old;")
    conn.execute(
        """
        CREATE TABLE hot_evaluations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          input_id INTEGER NOT NULL UNIQUE,
          is_hot_topic INTEGER,
          hotness_score INTEGER,
          algorithm_fit_score INTEGER,
          reply_potential_score INTEGER,
          retweet_potential_score INTEGER,
          dwell_time_score INTEGER,
          visual_potential_score INTEGER,
          coinmeta_angle_score INTEGER,
          fact_anchor_status TEXT,
          template_type TEXT,
          publish_mode TEXT,
          risk_level TEXT,
          safe_angle TEXT,
          do_not_write TEXT,
          interaction_trigger TEXT,
          recommended_post_type TEXT,
          evaluation_json TEXT,
          prompt_version TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY (input_id) REFERENCES hot_inputs(id)
        );
        """
    )

    old_cols = _get_columns(conn, "hot_evaluations_old")
    if "input_id" in old_cols:
        conn.execute(
            """
            INSERT OR IGNORE INTO hot_evaluations (
              input_id, hotness_score, template_type, publish_mode, risk_level,
              safe_angle, do_not_write, evaluation_json, prompt_version, created_at
            )
            SELECT
              input_id, hotness_score, template_type, publish_mode, risk_level,
              safe_angle, do_not_write, evaluation_json, prompt_version, created_at
            FROM hot_evaluations_old;
            """
        )
    conn.execute("DROP TABLE hot_evaluations_old;")


def _recreate_hot_drafts_if_needed(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hot_drafts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          input_id INTEGER NOT NULL,
          evaluation_id INTEGER NOT NULL,
          core_angle TEXT,
          user_impact_angle TEXT,
          hook_type TEXT,
          hook_candidates_json TEXT,
          selected_hook TEXT,
          why_people_care TEXT,
          main_post_cn TEXT,
          first_comment_cn TEXT,
          visual_prompt_cn TEXT,
          risk_note TEXT,
          approval_status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE (input_id, evaluation_id),
          FOREIGN KEY (input_id) REFERENCES hot_inputs(id),
          FOREIGN KEY (evaluation_id) REFERENCES hot_evaluations(id)
        );
        """
    )

    cols = _get_columns(conn, "hot_drafts")
    required = {"main_post_cn", "first_comment_cn", "visual_prompt_cn", "risk_note"}
    if required.issubset(cols):
        if "core_angle" not in cols:
            conn.execute("ALTER TABLE hot_drafts ADD COLUMN core_angle TEXT;")
        if "user_impact_angle" not in cols:
            conn.execute("ALTER TABLE hot_drafts ADD COLUMN user_impact_angle TEXT;")
        if "hook_type" not in cols:
            conn.execute("ALTER TABLE hot_drafts ADD COLUMN hook_type TEXT;")
        if "hook_candidates_json" not in cols:
            conn.execute("ALTER TABLE hot_drafts ADD COLUMN hook_candidates_json TEXT;")
        if "selected_hook" not in cols:
            conn.execute("ALTER TABLE hot_drafts ADD COLUMN selected_hook TEXT;")
        if "why_people_care" not in cols:
            conn.execute("ALTER TABLE hot_drafts ADD COLUMN why_people_care TEXT;")
        return

    conn.execute("ALTER TABLE hot_drafts RENAME TO hot_drafts_old;")
    conn.execute(
        """
        CREATE TABLE hot_drafts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          input_id INTEGER NOT NULL,
          evaluation_id INTEGER NOT NULL,
          core_angle TEXT,
          user_impact_angle TEXT,
          hook_type TEXT,
          hook_candidates_json TEXT,
          selected_hook TEXT,
          why_people_care TEXT,
          main_post_cn TEXT,
          first_comment_cn TEXT,
          visual_prompt_cn TEXT,
          risk_note TEXT,
          approval_status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE (input_id, evaluation_id),
          FOREIGN KEY (input_id) REFERENCES hot_inputs(id),
          FOREIGN KEY (evaluation_id) REFERENCES hot_evaluations(id)
        );
        """
    )

    old_cols = _get_columns(conn, "hot_drafts_old")
    if {"input_id", "evaluation_id"}.issubset(old_cols):
        if "x_cn_post" in old_cols:
            conn.execute(
                """
                INSERT OR IGNORE INTO hot_drafts (
                  input_id, evaluation_id, main_post_cn, approval_status, created_at, updated_at
                )
                SELECT
                  input_id, evaluation_id, x_cn_post, approval_status, created_at, updated_at
                FROM hot_drafts_old;
                """
            )
    conn.execute("DROP TABLE hot_drafts_old;")


def main() -> None:
    root = _project_root()
    cfg = _load_simple_yaml(root / "config.yaml")
    db_path = root / (cfg.get("db_path") or "hot_follow.db")

    root.joinpath("out").mkdir(parents=True, exist_ok=True)
    root.joinpath("logs").mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF;")

    _ensure_hot_inputs(conn)
    _recreate_hot_evaluations_if_needed(conn)
    _recreate_hot_drafts_if_needed(conn)

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()

    ts = _utc_now_iso()
    print(f"[init_db] ok db={db_path} ts={ts}")


if __name__ == "__main__":
    main()
