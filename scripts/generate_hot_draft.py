from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from llm_client import call_llm, log_llm_failure


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


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {r[1] for r in rows}


def _ensure_hot_drafts_columns(conn: sqlite3.Connection) -> None:
    cols = _get_columns(conn, "hot_drafts")
    add: list[tuple[str, str]] = []
    if "ordinary_reading" not in cols:
        add.append(("ordinary_reading", "TEXT"))
    if "reframed_reading" not in cols:
        add.append(("reframed_reading", "TEXT"))
    if "aha_line" not in cols:
        add.append(("aha_line", "TEXT"))
    if "macro_mainline" not in cols:
        add.append(("macro_mainline", "TEXT"))
    if "human_scene" not in cols:
        add.append(("human_scene", "TEXT"))
    if "scene_bridge_line" not in cols:
        add.append(("scene_bridge_line", "TEXT"))
    if "macro_reframe" not in cols:
        add.append(("macro_reframe", "TEXT"))
    if "scene_risk" not in cols:
        add.append(("scene_risk", "TEXT"))
    if "structure_signature" not in cols:
        add.append(("structure_signature", "TEXT"))
    if "second_order_market_read" not in cols:
        add.append(("second_order_market_read", "TEXT"))
    if "cold_realism_line" not in cols:
        add.append(("cold_realism_line", "TEXT"))
    if "repetition_risk" not in cols:
        add.append(("repetition_risk", "TEXT"))
    if "narrative_echo" not in cols:
        add.append(("narrative_echo", "TEXT"))
    if "skepticism_line" not in cols:
        add.append(("skepticism_line", "TEXT"))
    if "concrete_scene_analogy" not in cols:
        add.append(("concrete_scene_analogy", "TEXT"))
    if "analogy_risk" not in cols:
        add.append(("analogy_risk", "TEXT"))
    if "reality_weight_translation" not in cols:
        add.append(("reality_weight_translation", "TEXT"))
    if "sharpness_level" not in cols:
        add.append(("sharpness_level", "TEXT"))
    if "commentary_style" not in cols:
        add.append(("commentary_style", "TEXT"))
    if "behavior_goal" not in cols:
        add.append(("behavior_goal", "TEXT"))
    if "rhythm_break_line" not in cols:
        add.append(("rhythm_break_line", "TEXT"))
    if "main_post_cn_lines_json" not in cols:
        add.append(("main_post_cn_lines_json", "TEXT"))
    if "first_comment_cn_lines_json" not in cols:
        add.append(("first_comment_cn_lines_json", "TEXT"))
    for name, typ in add:
        conn.execute(f"ALTER TABLE hot_drafts ADD COLUMN {name} {typ};")


def _risk_note(risk_level: str, do_not_write: str) -> str:
    rl = (risk_level or "").strip()
    if rl == "high":
        prefix = "不建议发布，仅作为观察素材。"
    elif rl == "medium":
        prefix = "避免把传闻写成事实，建议人工审核。"
    else:
        prefix = "保持克制，不做价格预测。"
    extra = (do_not_write or "").strip()
    if extra:
        return f"{prefix}\n不要写：{extra}"
    return prefix


def _visual_prompt_for(template_type: str, raw: str) -> str:
    base = "视觉风格优先：黑金链上情报风 / 研究报告长图风 / 快讯卡片风。"
    if template_type == "news_card_take":
        return "复用币界网快讯卡片。"
    if template_type == "quick_data_take":
        return f"{base}\n数据内容：使用真实数据截图，不要编造数字。\n要点：{_clip(raw, 70)}"
    if template_type == "event_calendar_watch":
        return f"{base}\n事件日历：做收藏型清单长图（3-5 条）。\n要点：{_clip(raw, 70)}"
    if template_type == "authority_quote_plus":
        return f"{base}\n权威原帖：引用框+中文解释一行+来源署名。\n要点：{_clip(raw, 70)}"
    return f"{base}\n概念图：可以做信息图（三点解释 + 一句总结）。\n要点：{_clip(raw, 70)}"


def _user_impact_angle(template_type: str, raw: str, core_angle: str) -> str:
    if template_type == "news_card_take":
        return _clip("对普通用户：别只复读标题，重点看它会不会改变你用链/用产品的体验。", 120)
    if template_type == "authority_quote_plus":
        return _clip("对普通用户：这是事实锚点/行为信号，不是喊单；对交易者：更适合做风控与跟踪。", 120)
    if template_type == "quick_data_take":
        return _clip("对普通用户：别被涨跌带节奏，先看资金/数据有没有变；对交易者：看扩散与兑现。", 120)
    if template_type == "event_calendar_watch":
        return _clip("对普通用户：把它当成一张“预期交易清单”；对交易者：重点看事件前后预期差。", 120)
    return _clip("对普通用户：先搞清楚它为什么重要、已知/未知是什么；对交易者：看热度与确认信号。", 120)


def _hook_pack(template_type: str, raw: str, safe_angle: str, source: str) -> tuple[str, str, str, list[str], str, str]:
    angle = (safe_angle or "").strip()
    if not angle:
        if template_type == "event_calendar_watch":
            angle = "把事件当成“预期交易清单”，看市场怎么提前定价"
        elif template_type == "quick_data_take":
            angle = "数据背后是资金行为变化，而不是涨跌情绪"
        elif template_type == "authority_quote_plus":
            angle = "权威帖是事实锚点，重点在中文解释与风险边界"
        elif template_type == "news_card_take":
            angle = "标题不是重点，重点是背后的结构性变化"
        else:
            angle = "把热点讲成人话：为什么重要、已知/未知是什么"

    if template_type == "quick_data_take":
        hook_type = "数据冲击型"
        candidates = [
            "这个数据不能只看表面。",
            f"今天最值得看的不是涨跌，而是这组数据：{_clip(raw, 32)}。",
            "比起表面数字，更关键的是资金行为有没有变。",
        ]
    elif template_type == "event_calendar_watch":
        hook_type = "预期交易型"
        candidates = [
            "如果只看价格，很容易错过真正的时间点。",
            "下周加密市场有几件事值得关注。",
            "市场交易的，往往不是结果，而是预期。",
        ]
    elif template_type == "authority_quote_plus":
        hook_type = "大号背书型"
        src = _clip(source, 18) or "权威大号"
        candidates = [
            f"{src} 这条数据值得看。",
            "这不是单纯的链上异动。",
            "这类数据最值得看的不是金额，而是行为变化。",
        ]
    elif template_type == "news_card_take":
        hook_type = "反常识型"
        candidates = [
            "这条消息的重点，不在标题里。",
            "如果只把它当成普通快讯，可能会漏掉关键点。",
            "真正值得看的不是这个事件本身，而是它背后的市场变化。",
        ]
    else:
        hook_type = "解释科普型"
        candidates = [
            "为什么市场突然开始讨论这个？",
            "这波热度不是突然来的。",
            "如果只看表层，很容易看错这件事。",
        ]

    selected = candidates[0] if candidates else ""
    why = _clip(angle, 120)
    user_impact = _user_impact_angle(template_type, raw, angle)
    return angle, user_impact, hook_type, candidates, selected, why


def _apply_selected_hook(main_post_cn: str, selected_hook: str) -> str:
    hook = (selected_hook or "").strip()
    if not hook:
        return (main_post_cn or "").strip()
    text = (main_post_cn or "").strip()
    if not text:
        return hook
    lines = text.splitlines()
    lines[0] = hook
    return "\n".join(lines).strip()


def _join_lines(lines_val: object) -> str:
    if not isinstance(lines_val, list):
        return ""
    parts = [str(x) for x in lines_val]
    return "\n".join(parts).strip()


def _draft_news_card_take(raw: str, safe_angle: str, has_card: bool) -> tuple[str, str]:
    hook = "这条消息的重点，不在标题里。"
    angle = _clip(safe_angle or "它背后代表的 Web3 / AI / 市场变化", 120)
    main = f"{hook}\n\n真正值得看的不是{_clip(raw, 40)}，而是{angle}。\n\n配图：币界网快讯卡片"
    comment = "首评补三点背景：\n1. 这个事件直接影响什么？\n2. 它和当前市场叙事有什么关系？\n3. 后续应该看什么确认信号？"
    return main.strip(), comment.strip()


def _draft_authority_quote_plus(raw: str, source: str, safe_angle: str) -> tuple[str, str]:
    lead = f"{_clip(source, 24)} 提到了一条值得看的信息。"
    explain = _clip(raw, 160)
    angle = _clip(safe_angle or "把它当成事实锚点，用中文解释清楚，不延伸到价格结论", 120)
    main = f"{lead}\n\n{explain}\n\n真正值得看的不是表面信息，而是{angle}。"
    comment = "首评：补充观察：\n1. 这条信息的“事实锚点”是什么？\n2. 哪些是推断（不要写成确定）。\n3. 这类案例更适合作为风险/叙事样本，而不是单纯看热闹。"
    return main.strip(), comment.strip()


def _draft_quick_data_take(raw: str, safe_angle: str) -> tuple[str, str]:
    lead = _clip(raw, 160)
    angle = _clip(safe_angle or "资金是否正在从高波动叙事里撤出", 120)
    main = f"{lead}\n\n真正值得看的不是数字本身，而是{angle}。"
    comment = "首评：如果这种变化继续扩散，后续需要观察：交易量、KOL 讨论热度、链上资金是否同步变化。"
    return main.strip(), comment.strip()


def _draft_event_calendar_watch(raw: str, safe_angle: str) -> tuple[str, str]:
    lead = "本周/下周加密市场有几件事值得关注："
    body = _clip(raw, 400)
    main = f"{lead}\n\n{body}\n\n真正值得看的不是这些事件是否“利好”，而是市场是否已经提前交易了预期。"
    comment = _clip(safe_angle or "首评：市场交易的，往往不是结果，而是预期。看“预期—现实—差值”。", 140)
    return main.strip(), comment.strip()


def _draft_hot_explainer(raw: str, safe_angle: str, interaction_trigger: str) -> tuple[str, str]:
    lead = f"为什么市场突然开始讨论{_clip(raw, 36)}？"
    body = "核心原因有三个：\n\n1. 叙事层：它解决的是谁的痛点？\n2. 资金层：有没有数据/行为在配合？\n3. 传播层：是谁把话题带起来的？"
    close = f"\n\n真正值得关注的不是这个词还火不火，而是{_clip(safe_angle or '它有没有进入“第二轮叙事重定价”', 120)}。"
    main = f"{lead}\n\n{body}{close}"
    comment = _clip(interaction_trigger or "你更关心它的“产品落地”还是“叙事扩散速度”？", 120)
    return main.strip(), comment.strip()


def _generate(template_type: str, raw: str, source: str, safe_angle: str, interaction_trigger: str, news_card_image: str) -> tuple[str, str]:
    if template_type == "news_card_take":
        return _draft_news_card_take(raw, safe_angle, bool((news_card_image or "").strip()))
    if template_type == "authority_quote_plus":
        return _draft_authority_quote_plus(raw, source, safe_angle)
    if template_type == "quick_data_take":
        return _draft_quick_data_take(raw, safe_angle)
    if template_type == "event_calendar_watch":
        return _draft_event_calendar_watch(raw, safe_angle)
    return _draft_hot_explainer(raw, safe_angle, interaction_trigger)


def _write_debug_output(root: Path, *, task_type: str, input_id: int, evaluation_id: int, err: str, raw_output: str) -> None:
    d = root / "logs" / "debug"
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_err = _clip(err or "unknown error", 240).replace("\n", " ").strip()
    p = d / f"{ts}_{task_type}_input{input_id}_eval{evaluation_id}.txt"
    header = f"task_type={task_type}\ninput_id={input_id}\nevaluation_id={evaluation_id}\nerror={safe_err}\n\n"
    p.write_text(header + (raw_output or ""), encoding="utf-8")


def _try_llm_generate(root: Path, row: sqlite3.Row) -> tuple[dict | None, str, str, str]:
    prompt_main = (root / "prompts" / "generate_claude_v0_2.md").read_text(encoding="utf-8")
    style_rules = (root / "style" / "coinmeta_x_style_v0_2.md").read_text(encoding="utf-8")
    system_prompt = "\n\n".join([prompt_main, style_rules])

    user_payload = {
        "raw_text": row["raw_text"],
        "input_type": row["input_type"],
        "source_name": row["source_name"],
        "related_coinmeta_news_text": row["related_coinmeta_news_text"],
        "evaluation_json": row["evaluation_json"],
        "template_type": row["template_type"],
        "risk_level": row["risk_level"],
        "safe_angle": row["safe_angle"],
        "do_not_write": row["do_not_write"],
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

    r = call_llm(
        task_type="generate_hot_draft",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        expect_json=True,
        temperature=0.4,
        max_tokens=1800,
    )
    if not r.get("ok"):
        return (
            None,
            str(r.get("error") or "llm failed"),
            str(r.get("content_preview") or ""),
            str(r.get("content") or ""),
        )
    obj = r.get("json")
    if not isinstance(obj, dict):
        return None, "llm json is not an object", str(r.get("content_preview") or ""), str(r.get("content") or "")

    available_keys = sorted(obj.keys())

    main_lines = obj.get("main_post_cn_lines")
    first_lines = obj.get("first_comment_cn_lines")

    has_main_lines = isinstance(main_lines, list) and len(main_lines) > 0
    has_first_lines = isinstance(first_lines, list) and len(first_lines) > 0

    missing: list[str] = []
    if not has_main_lines:
        missing.append("main_post_cn_lines(non-empty list)")
    if not isinstance(main_lines, list):
        missing.append("main_post_cn_lines must be list")

    if not has_first_lines:
        missing.append("first_comment_cn_lines(non-empty list)")
    if not isinstance(first_lines, list):
        missing.append("first_comment_cn_lines must be list")

    if missing:
        try:
            raw_json = json.dumps(obj, ensure_ascii=False)
        except TypeError:
            raw_json = str(obj)
        json_preview = _clip(raw_json, 900)
        err = (
            "llm output missing keys"
            f" missing_keys={missing}"
            f" available_keys={available_keys}"
            f" json_preview={json_preview}"
        )
        return None, err, str(r.get("content_preview") or ""), str(r.get("content") or "")
    return obj, "", "", ""


def main() -> None:
    root = _project_root()
    cfg = _load_simple_yaml(root / "config.yaml")
    _setup_logging(root, cfg)

    _ = (root / "prompts" / "generate_claude_v0_2.md").read_text(encoding="utf-8")
    _ = (root / "style" / "coinmeta_x_style_v0_2.md").read_text(encoding="utf-8")

    db_path = root / (cfg.get("db_path") or "hot_follow.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    _ensure_hot_drafts_columns(conn)

    max_items_raw = (os.getenv("MAX_ITEMS_PER_RUN") or "").strip()
    max_items: int | None = None
    if max_items_raw:
        try:
            v = int(max_items_raw)
            if v > 0:
                max_items = v
        except ValueError:
            max_items = None

    base_sql = """
        SELECT
          i.*,
          e.id AS evaluation_id,
          e.template_type,
          e.publish_mode,
          e.risk_level,
          e.safe_angle,
          e.do_not_write,
          e.interaction_trigger,
          e.evaluation_json
        FROM hot_inputs i
        JOIN hot_evaluations e ON e.input_id = i.id
        LEFT JOIN hot_drafts d ON d.input_id = i.id AND d.evaluation_id = e.id
        WHERE i.status = 'evaluated'
          AND e.publish_mode = 'queue_review'
          AND d.id IS NULL
        ORDER BY i.id ASC
    """
    if max_items is None:
        rows = conn.execute(base_sql + ";").fetchall()
    else:
        rows = conn.execute(base_sql + " LIMIT ?;", (max_items,)).fetchall()

    if not rows:
        logging.info("no_items_to_draft db=%s", db_path)
        print("[generate_hot_draft] ok drafted=0")
        return

    drafted = 0
    now = _utc_now_iso()

    model_runtime = (
        (os.getenv("GENERATE_MODEL_RUNTIME") or "").strip().lower()
        or (os.getenv("MODEL_RUNTIME") or "").strip().lower()
        or "mock"
    )
    if model_runtime not in {"mock", "openrouter"}:
        model_runtime = "mock"
    use_model = model_runtime == "openrouter"
    logging.info(
        "generate_config runtime=%s max_items_per_run=%s",
        model_runtime,
        max_items if max_items is not None else "all",
    )

    for row in rows:
        raw = (row["raw_text"] or "").strip()
        src = (row["source_name"] or "").strip() or (row["source_tool"] or "").strip()
        template_type = (row["template_type"] or "").strip()
        safe_angle = (row["safe_angle"] or "").strip()
        risk_level = (row["risk_level"] or "").strip()
        do_not_write = (row["do_not_write"] or "").strip()
        interaction_trigger = (row["interaction_trigger"] or "").strip()
        news_card_image = (row["news_card_image"] or "").strip()
        try:
            ej = json.loads(row["evaluation_json"] or "{}")
            if not isinstance(ej, dict):
                ej = {}
        except json.JSONDecodeError:
            ej = {}
        allowed_to_generate = bool(ej.get("allowed_to_generate"))
        worth_spending_claude = bool(ej.get("worth_spending_claude"))

        if not (allowed_to_generate and worth_spending_claude):
            logging.info(
                "skip_generate input_id=%s allowed_to_generate=%s worth_spending_claude=%s publish_mode=%s template_type=%s",
                row["id"],
                allowed_to_generate,
                worth_spending_claude,
                (row["publish_mode"] or "").strip(),
                template_type,
            )
            continue

        llm_obj = None
        llm_err = ""
        llm_preview = ""
        llm_raw = ""
        if use_model:
            prev = os.environ.get("MODEL_RUNTIME")
            os.environ["MODEL_RUNTIME"] = model_runtime
            try:
                llm_obj, llm_err, llm_preview, llm_raw = _try_llm_generate(root=root, row=row)
            finally:
                if prev is None:
                    os.environ.pop("MODEL_RUNTIME", None)
                else:
                    os.environ["MODEL_RUNTIME"] = prev

        if llm_obj is not None:
            core_angle = str(llm_obj.get("core_angle") or "").strip()
            user_impact_angle = str(llm_obj.get("user_impact_angle") or "").strip()
            ordinary_reading = str(llm_obj.get("ordinary_reading") or "").strip()
            reframed_reading = str(llm_obj.get("reframed_reading") or "").strip()
            aha_line = str(llm_obj.get("aha_line") or "").strip()
            macro_mainline = str(llm_obj.get("macro_mainline") or "").strip()
            human_scene = str(llm_obj.get("human_scene") or "").strip()
            scene_bridge_line = str(llm_obj.get("scene_bridge_line") or "").strip()
            macro_reframe = str(llm_obj.get("macro_reframe") or "").strip()
            scene_risk = str(llm_obj.get("scene_risk") or "").strip()
            structure_signature = str(llm_obj.get("structure_signature") or "").strip()
            second_order_market_read = str(llm_obj.get("second_order_market_read") or "").strip()
            cold_realism_line = str(llm_obj.get("cold_realism_line") or "").strip()
            repetition_risk = str(llm_obj.get("repetition_risk") or "").strip()
            narrative_echo = str(llm_obj.get("narrative_echo") or "").strip()
            skepticism_line = str(llm_obj.get("skepticism_line") or "").strip()
            concrete_scene_analogy = str(llm_obj.get("concrete_scene_analogy") or "").strip()
            analogy_risk = str(llm_obj.get("analogy_risk") or "").strip()
            reality_weight_translation = str(llm_obj.get("reality_weight_translation") or "").strip()
            sharpness_level = str(llm_obj.get("sharpness_level") or "").strip()
            commentary_style = str(llm_obj.get("commentary_style") or "").strip()
            behavior_goal = str(llm_obj.get("behavior_goal") or "").strip()
            hook_type = str(llm_obj.get("hook_type") or "").strip()
            hook_candidates = llm_obj.get("hook_candidates")
            if not isinstance(hook_candidates, list):
                hook_candidates = []
            hook_candidates = [str(x).strip() for x in hook_candidates if str(x).strip()]
            selected_hook = str(llm_obj.get("selected_hook") or "").strip()
            why_people_care = str(llm_obj.get("why_people_care") or "").strip()
            rhythm_break_line = str(llm_obj.get("rhythm_break_line") or "").strip()

            main_lines = llm_obj.get("main_post_cn_lines")
            first_lines = llm_obj.get("first_comment_cn_lines")
            main_post_cn = _join_lines(main_lines)
            first_comment_cn = _join_lines(first_lines)
            main_post_cn_lines_json = json.dumps(main_lines if isinstance(main_lines, list) else [], ensure_ascii=False)
            first_comment_cn_lines_json = json.dumps(first_lines if isinstance(first_lines, list) else [], ensure_ascii=False)
            visual_prompt_cn = str(llm_obj.get("visual_prompt_cn") or "").strip()
            risk_note = str(llm_obj.get("risk_note") or "").strip()
        else:
            if use_model and llm_err:
                if llm_raw:
                    _write_debug_output(
                        root,
                        task_type="generate_hot_draft",
                        input_id=int(row["id"]),
                        evaluation_id=int(row["evaluation_id"]),
                        err=llm_err,
                        raw_output=llm_raw,
                    )
                if llm_preview:
                    log_llm_failure(
                        "generate_hot_draft", f"{llm_err} | content_preview={llm_preview}"
                    )
                else:
                    log_llm_failure("generate_hot_draft", llm_err)
            main_post_cn, first_comment_cn = _generate(
                template_type=template_type,
                raw=raw,
                source=src,
                safe_angle=safe_angle,
                interaction_trigger=interaction_trigger,
                news_card_image=news_card_image,
            )
            (
                core_angle,
                user_impact_angle,
                hook_type,
                hook_candidates,
                selected_hook,
                why_people_care,
            ) = _hook_pack(
                template_type=template_type,
                raw=raw,
                safe_angle=safe_angle,
                source=src,
            )
            ordinary_reading = ""
            reframed_reading = ""
            aha_line = ""
            macro_mainline = ""
            human_scene = ""
            scene_bridge_line = ""
            macro_reframe = ""
            scene_risk = "low"
            structure_signature = ""
            second_order_market_read = ""
            cold_realism_line = ""
            repetition_risk = "low"
            narrative_echo = ""
            skepticism_line = ""
            concrete_scene_analogy = ""
            analogy_risk = "low"
            reality_weight_translation = ""
            sharpness_level = "medium"
            commentary_style = "neutral"
            behavior_goal = "dwell"
            rhythm_break_line = ""
            main_post_cn = _apply_selected_hook(main_post_cn, selected_hook)
            main_post_cn_lines_json = json.dumps(main_post_cn.split("\n"), ensure_ascii=False)
            first_comment_cn_lines_json = json.dumps(first_comment_cn.split("\n"), ensure_ascii=False)
            visual_prompt_cn = _visual_prompt_for(template_type, raw)
            risk_note = _risk_note(risk_level, do_not_write)
            if use_model:
                risk_note = (risk_note + "\n模型调用失败，已使用 mock fallback").strip()

        payload = {
            "core_angle": core_angle,
            "user_impact_angle": user_impact_angle,
            "ordinary_reading": ordinary_reading,
            "reframed_reading": reframed_reading,
            "aha_line": aha_line,
            "macro_mainline": macro_mainline,
            "human_scene": human_scene,
            "scene_bridge_line": scene_bridge_line,
            "macro_reframe": macro_reframe,
            "scene_risk": scene_risk,
            "structure_signature": structure_signature,
            "second_order_market_read": second_order_market_read,
            "cold_realism_line": cold_realism_line,
            "repetition_risk": repetition_risk,
            "narrative_echo": narrative_echo,
            "skepticism_line": skepticism_line,
            "concrete_scene_analogy": concrete_scene_analogy,
            "analogy_risk": analogy_risk,
            "reality_weight_translation": reality_weight_translation,
            "sharpness_level": sharpness_level,
            "commentary_style": commentary_style,
            "behavior_goal": behavior_goal,
            "hook_type": hook_type,
            "hook_candidates": hook_candidates,
            "selected_hook": selected_hook,
            "why_people_care": why_people_care,
            "rhythm_break_line": rhythm_break_line,
            "main_post_cn": main_post_cn,
            "first_comment_cn": first_comment_cn,
            "main_post_cn_lines": json.loads(main_post_cn_lines_json or "[]"),
            "first_comment_cn_lines": json.loads(first_comment_cn_lines_json or "[]"),
            "visual_prompt_cn": visual_prompt_cn,
            "risk_note": risk_note,
        }
        _ = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        conn.execute(
            """
            INSERT INTO hot_drafts (
              input_id, evaluation_id,
              core_angle, user_impact_angle, ordinary_reading, reframed_reading, aha_line,
              macro_mainline, human_scene, scene_bridge_line, macro_reframe, scene_risk,
              structure_signature, second_order_market_read, cold_realism_line, repetition_risk,
              narrative_echo, skepticism_line, concrete_scene_analogy, analogy_risk, reality_weight_translation,
              sharpness_level, commentary_style, behavior_goal,
              hook_type, hook_candidates_json, selected_hook, why_people_care, rhythm_break_line,
              main_post_cn_lines_json, first_comment_cn_lines_json,
              main_post_cn, first_comment_cn, visual_prompt_cn, risk_note,
              approval_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                row["id"],
                row["evaluation_id"],
                core_angle,
                user_impact_angle,
                ordinary_reading,
                reframed_reading,
                aha_line,
                macro_mainline,
                human_scene,
                scene_bridge_line,
                macro_reframe,
                scene_risk,
                structure_signature,
                second_order_market_read,
                cold_realism_line,
                repetition_risk,
                narrative_echo,
                skepticism_line,
                concrete_scene_analogy,
                analogy_risk,
                reality_weight_translation,
                sharpness_level,
                commentary_style,
                behavior_goal,
                hook_type,
                json.dumps(hook_candidates, ensure_ascii=False),
                selected_hook,
                why_people_care,
                rhythm_break_line,
                main_post_cn_lines_json,
                first_comment_cn_lines_json,
                main_post_cn,
                first_comment_cn,
                visual_prompt_cn,
                risk_note,
                "pending",
                now,
                now,
            ),
        )

        conn.execute(
            "UPDATE hot_inputs SET status = 'drafted', updated_at = ? WHERE id = ?;",
            (now, row["id"]),
        )

        drafted += 1

    conn.commit()
    conn.close()

    logging.info("drafted=%s db=%s", drafted, db_path)
    print(f"[generate_hot_draft] ok drafted={drafted}")


if __name__ == "__main__":
    main()
