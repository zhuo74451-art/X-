from __future__ import annotations

import json
import logging
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


def _setup_logging(root: Path, cfg: dict) -> None:
    log_rel = cfg.get("log_path") or "logs/run.log"
    log_path = root / log_rel
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _md_escape(s: str) -> str:
    return (s or "").replace("\r\n", "\n").strip()


def _safe_json_loads(s: str) -> dict:
    try:
        obj = json.loads(s or "{}")
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _safe_json_loads_list(s: str) -> list[str]:
    try:
        obj = json.loads(s or "[]")
        if isinstance(obj, list):
            return [str(x) for x in obj]
        return []
    except json.JSONDecodeError:
        return []


def main() -> None:
    root = _project_root()
    cfg = _load_simple_yaml(root / "config.yaml")
    _setup_logging(root, cfg)

    db_path = root / (cfg.get("db_path") or "hot_follow.db")
    out_path = root / (cfg.get("out_review_queue_path") or "out/x_review_queue.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    rows = conn.execute(
        """
        SELECT
          d.*,
          i.input_type,
          i.source_tool,
          i.source_name,
          i.source_url,
          i.raw_text,
          i.related_coinmeta_news_url,
          i.related_coinmeta_news_text,
          i.news_card_image,
          i.lang,
          e.is_hot_topic,
          e.hotness_score,
          e.algorithm_fit_score,
          e.reply_potential_score,
          e.retweet_potential_score,
          e.dwell_time_score,
          e.visual_potential_score,
          e.coinmeta_angle_score,
          e.fact_anchor_status,
          e.template_type,
          e.publish_mode,
          e.risk_level,
          e.safe_angle,
          e.do_not_write,
          e.interaction_trigger,
          e.recommended_post_type,
          e.evaluation_json,
          e.prompt_version
        FROM hot_drafts d
        JOIN hot_inputs i ON i.id = d.input_id
        JOIN hot_evaluations e ON e.id = d.evaluation_id
        WHERE d.approval_status = 'pending'
          AND e.prompt_version = 'v0.2'
        ORDER BY d.id ASC;
        """
    ).fetchall()

    ts = _utc_now_iso()
    lines: list[str] = []
    lines.append(f"# X Review Queue (CoinMeta v0.2)\n")
    lines.append(f"- Exported at (UTC): {ts}\n")
    lines.append(f"- Pending items: {len(rows)}\n")

    for idx, r in enumerate(rows, start=1):
        lines.append("\n---\n")
        lines.append(f"## Item {idx} (draft_id={r['id']}, input_id={r['input_id']})\n")

        lines.append("### 原始热点\n")
        lines.append(f"- input_type: {r['input_type']}\n")
        lines.append(f"- source_tool: {r['source_tool']}\n")
        lines.append(f"- source_name: {r['source_name']}\n")
        lines.append(f"- source_url: {r['source_url']}\n")
        lines.append(f"- lang: {r['lang']}\n")
        if r["news_card_image"]:
            lines.append(f"- news_card_image: {r['news_card_image']}\n")
        if r["related_coinmeta_news_url"] or r["related_coinmeta_news_text"]:
            lines.append(f"- related_coinmeta_news_url: {r['related_coinmeta_news_url']}\n")
        lines.append("\n```text\n")
        lines.append(_md_escape(r["raw_text"]) + "\n")
        lines.append("```\n")
        if r["related_coinmeta_news_text"]:
            lines.append("\n```text\n")
            lines.append(_md_escape(r["related_coinmeta_news_text"]) + "\n")
            lines.append("```\n")

        lines.append("\n### AI 判断\n")
        ej = _safe_json_loads(r["evaluation_json"] or "{}")
        lines.append(f"- is_hot_topic: {bool(ej.get('is_hot_topic', bool(r['is_hot_topic'])))}\n")
        lines.append(f"- worth_spending_claude: {bool(ej.get('worth_spending_claude', False))}\n")
        lines.append(f"- allowed_to_generate: {bool(ej.get('allowed_to_generate', False))}\n")
        lines.append(f"- publish_mode: {_md_escape(str(ej.get('publish_mode') or r['publish_mode'] or ''))}\n")
        lines.append(f"- template_type: {_md_escape(str(ej.get('template_type') or r['template_type'] or ''))}\n")
        lines.append(f"- reason: {_md_escape(str(ej.get('reason') or ''))}\n")

        lines.append("\n<details>\n<summary>evaluation_json</summary>\n\n```json\n")
        lines.append(json.dumps(ej, ensure_ascii=False, indent=2) + "\n")
        lines.append("```\n\n</details>\n")

        lines.append("\n### 生成关键字段\n")
        core_angle = _md_escape(str((r["core_angle"] if "core_angle" in r.keys() else "") or ej.get("core_angle") or ""))
        user_impact_angle = _md_escape(str((r["user_impact_angle"] if "user_impact_angle" in r.keys() else "") or ej.get("user_impact_angle") or ""))
        why_people_care = _md_escape(str((r["why_people_care"] if "why_people_care" in r.keys() else "") or ej.get("why_people_care") or ""))
        missing_facts = ej.get("missing_facts")
        if not isinstance(missing_facts, list):
            missing_facts = []
        missing_facts = [str(x).strip() for x in missing_facts if str(x).strip()]

        lines.append(f"- core_angle: {core_angle}\n")
        lines.append(f"- user_impact_angle: {user_impact_angle}\n")
        lines.append(f"- why_people_care: {why_people_care}\n")
        lines.append("- missing_facts:\n")
        if missing_facts:
            for x in missing_facts:
                lines.append(f"  - {_md_escape(x)}\n")
        else:
            lines.append("  - \n")

        main_lines = _safe_json_loads_list(r["main_post_cn_lines_json"] if "main_post_cn_lines_json" in r.keys() else "")
        if not main_lines:
            main_lines = _md_escape(r["main_post_cn"]).split("\n") if r["main_post_cn"] else []
        first_lines = _safe_json_loads_list(r["first_comment_cn_lines_json"] if "first_comment_cn_lines_json" in r.keys() else "")
        if not first_lines:
            first_lines = _md_escape(r["first_comment_cn"]).split("\n") if r["first_comment_cn"] else []

        lines.append("\n### main_post_cn_lines\n\n```json\n")
        lines.append(json.dumps(main_lines, ensure_ascii=False, indent=2) + "\n")
        lines.append("```\n")

        lines.append("\n### first_comment_cn_lines\n\n```json\n")
        lines.append(json.dumps(first_lines, ensure_ascii=False, indent=2) + "\n")
        lines.append("```\n")

        lines.append("\n### 可选配图 Prompt（visual_prompt_cn）\n\n```text\n")
        lines.append(_md_escape(r["visual_prompt_cn"]) + "\n")
        lines.append("```\n")

        lines.append("\n### 风险提示（risk_note）\n\n```text\n")
        lines.append(_md_escape(r["risk_note"]) + "\n")
        lines.append("```\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    conn.close()

    logging.info("exported=%s path=%s", len(rows), out_path)
    print(f"[export_review_queue] ok exported={len(rows)} path={out_path}")


if __name__ == "__main__":
    main()
