from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _write_debug_output(root: Path, *, task_type: str, input_id: int, err: str, raw_output: str) -> None:
    d = root / "logs" / "debug"
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_err = _clip(err or "unknown error", 240).replace("\n", " ").strip()
    p = d / f"{ts}_{task_type}_input{input_id}.txt"
    header = f"task_type={task_type}\ninput_id={input_id}\nerror={safe_err}\n\n"
    p.write_text(header + (raw_output or ""), encoding="utf-8")


def _is_spam(text: str) -> bool:
    t = text.lower()
    keywords = [
        "1000x",
        "airdrop",
        "referral",
        "guaranteed profit",
        "white list",
        "whitelist",
        "私信",
        "加入群",
        "空投",
        "白名单",
        "稳赚",
        "拉人",
        "返佣",
        "返利",
        "保本",
        "稳赚不赔",
        "领糖果",
        "注册送",
        "u 本位",
    ]
    return any(k in t for k in keywords)


def _is_rumor_or_controversy(text: str) -> bool:
    t = text.lower()
    keywords = [
        "rumor",
        "传闻",
        "exploit",
        "hacked",
        "hack",
        "liquidity",
        "insolv",
        "资不抵债",
        "流动性",
        "限制提币",
        "挤兑",
        "暴雷",
        "被攻击",
        "被黑",
        "ftx",
    ]
    return any(k in t for k in keywords)


def _mock_evaluate(row: sqlite3.Row) -> dict[str, Any]:
    input_type = (row["input_type"] or "").strip()
    text = (row["raw_text"] or "").strip()
    src_name = (row["source_name"] or "").strip()
    src_tool = (row["source_tool"] or "").strip()
    related_url = (row["related_coinmeta_news_url"] or "").strip()
    related_text = (row["related_coinmeta_news_text"] or "").strip()

    def _clip_score(v: int) -> int:
        try:
            n = int(v)
        except Exception:
            n = 0
        if n < 0:
            return 0
        if n > 100:
            return 100
        return n

    def base(
        *,
        is_hot_topic: bool,
        worth_spending_claude: bool,
        allowed_to_generate: bool,
        hotness_score: int,
        angle_score: int,
        user_impact_score: int,
        visual_potential_score: int,
        fact_anchor_status: str,
        source_mode: str,
        need_source_research: bool,
        template_type: str,
        publish_mode: str,
        risk_level: str,
        core_angle: str,
        user_impact_angle: str,
        why_people_care: str,
        missing_facts: list[str],
        safe_angle: str,
        do_not_write: str,
        recommended_post_type: str,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "is_hot_topic": bool(is_hot_topic),
            "worth_spending_claude": bool(worth_spending_claude),
            "allowed_to_generate": bool(allowed_to_generate),
            "hotness_score": _clip_score(hotness_score),
            "angle_score": _clip_score(angle_score),
            "user_impact_score": _clip_score(user_impact_score),
            "visual_potential_score": _clip_score(visual_potential_score),
            "fact_anchor_status": fact_anchor_status,
            "source_mode": source_mode,
            "need_source_research": bool(need_source_research),
            "template_type": template_type,
            "publish_mode": publish_mode,
            "risk_level": risk_level,
            "core_angle": (core_angle or "").strip(),
            "user_impact_angle": (user_impact_angle or "").strip(),
            "why_people_care": (why_people_care or "").strip(),
            "missing_facts": [str(x).strip() for x in (missing_facts or []) if str(x).strip()],
            "safe_angle": (safe_angle or "").strip(),
            "do_not_write": (do_not_write or "").strip(),
            "recommended_post_type": recommended_post_type,
            "reason": (reason or "").strip(),
        }

    def _detect_macro_scene(s: str) -> bool:
        t = (s or "").lower()
        has_macro = any(x in t for x in ["iea", "opec", "油价", "石油", "通胀", "利率", "外汇", "地缘", "战争"])
        has_scene = any(x in t for x in ["车队", "缩减", "省燃油", "账单", "航班", "货柜", "超市", "汇率"])
        return bool(has_macro and has_scene)

    def _fact_anchor_status() -> str:
        if related_url or related_text:
            return "medium"
        if input_type in {"coinmeta_newsflash", "authority_post", "quick_data", "event_calendar"}:
            return "strong"
        return "weak"

    def _source_mode() -> str:
        if input_type == "coinmeta_newsflash":
            return "internal_newsflash"
        if input_type in {"authority_post", "quick_data"}:
            return "verified_news"
        if input_type in {"kol_post"}:
            return "kol_signal_only"
        return "unknown"

    if input_type == "junk" or _is_spam(text):
        return base(
            is_hot_topic=False,
            worth_spending_claude=False,
            allowed_to_generate=False,
            hotness_score=15,
            angle_score=0,
            user_impact_score=0,
            visual_potential_score=0,
            fact_anchor_status="none",
            source_mode="unknown",
            need_source_research=False,
            template_type="none",
            publish_mode="reject",
            risk_level="low",
            core_angle="不跟营销垃圾热点",
            user_impact_angle="",
            why_people_care="",
            missing_facts=[],
            safe_angle="不跟营销垃圾热点",
            do_not_write="不要带引流链接/口号/夸张收益；不要暗示保本/稳赚",
            recommended_post_type="monitor",
            reason="营销/引流垃圾内容，不符合 CoinMeta 官号定位",
        )

    if input_type == "controversy" or _is_rumor_or_controversy(text):
        return base(
            is_hot_topic=True,
            worth_spending_claude=False,
            allowed_to_generate=False,
            hotness_score=78,
            angle_score=60,
            user_impact_score=70,
            visual_potential_score=40,
            fact_anchor_status="weak" if (related_url or related_text) else "none",
            source_mode=_source_mode(),
            need_source_research=not bool(related_url or related_text),
            template_type="none",
            publish_mode="monitor",
            risk_level="high",
            core_angle="只讲已知/未知/待确认",
            user_impact_angle="先保护自己再谈观点",
            why_people_care="高风险但容易被误读",
            missing_facts=["需要补充可信来源/链上截图/官方说明"] if not (related_url or related_text) else [],
            safe_angle="只讲“已知/未知/待确认”，给出风险提醒，不站队不下结论",
            do_not_write="不要写成已暴雷/已被黑/已跑路；不要给资金建议；不要攻击个人/项目",
            recommended_post_type="monitor",
            reason="争议/传闻类高风险内容：可以跟进但只能监控口径",
        )

    if input_type == "coinmeta_newsflash":
        return base(
            is_hot_topic=True,
            worth_spending_claude=True,
            allowed_to_generate=True,
            hotness_score=72,
            angle_score=75,
            user_impact_score=62,
            visual_potential_score=82,
            fact_anchor_status="strong",
            source_mode="internal_newsflash",
            need_source_research=False,
            template_type="news_card_take",
            publish_mode="queue_review",
            risk_level="low",
            core_angle="别复读标题，讲影响点",
            user_impact_angle="用户更关心体验/风险是否变化",
            why_people_care="快讯二次包装更适合 X 传播",
            missing_facts=[],
            safe_angle="一句话把“重点”说出来：别复读标题，讲影响点",
            do_not_write="不要写成传统快讯搬运；不要价格预测；不要制造 FOMO",
            recommended_post_type="visual_post",
            reason="自家快讯有事实锚点，适合二次包装做热点跟进",
        )

    if input_type == "authority_post":
        return base(
            is_hot_topic=True,
            worth_spending_claude=True,
            allowed_to_generate=True,
            hotness_score=70,
            angle_score=72,
            user_impact_score=64,
            visual_potential_score=55,
            fact_anchor_status="strong",
            source_mode="verified_news",
            need_source_research=False,
            template_type="authority_quote_plus",
            publish_mode="queue_review",
            risk_level="medium",
            core_angle="把它当事实锚点，不当结论",
            user_impact_angle="对普通用户是风险/信号，不是喊单",
            why_people_care="可转述、可补背景、可做风控",
            missing_facts=[],
            safe_angle="把权威原帖当“事实锚点”，用中文解释清楚，不延伸到价格结论",
            do_not_write="不要脑补动机；不要把“可能”写成“确定”；不要喊单",
            recommended_post_type="short_post",
            reason=f"权威大号/数据源（{src_name or src_tool}）可作为事实锚点，适合跟进",
        )

    if input_type == "quick_data":
        return base(
            is_hot_topic=True,
            worth_spending_claude=True,
            allowed_to_generate=True,
            hotness_score=68,
            angle_score=74,
            user_impact_score=60,
            visual_potential_score=70,
            fact_anchor_status="strong" if (src_tool or src_name) else "medium",
            source_mode="verified_news",
            need_source_research=False,
            template_type="quick_data_take",
            publish_mode="queue_review",
            risk_level="medium",
            core_angle="数据是信号，不是结论",
            user_impact_angle="把它当风控/跟踪点",
            why_people_care="能触发评论与收藏",
            missing_facts=[],
            safe_angle="只讲数据本身 + “可能意味着什么/不意味着什么”",
            do_not_write="不要把相关性写成因果；不要价格预测；不要 FOMO 口径",
            recommended_post_type="short_post",
            reason="数据异动适合做热点跟进，且易做评论区承接",
        )

    if input_type == "event_calendar":
        return base(
            is_hot_topic=True,
            worth_spending_claude=True,
            allowed_to_generate=True,
            hotness_score=62,
            angle_score=66,
            user_impact_score=65,
            visual_potential_score=75,
            fact_anchor_status="medium",
            source_mode="verified_news",
            need_source_research=False,
            template_type="event_calendar_watch",
            publish_mode="queue_review",
            risk_level="low",
            core_angle="市场交易的是预期",
            user_impact_angle="给用户一个可收藏的观察清单",
            why_people_care="适合转发/收藏",
            missing_facts=[],
            safe_angle="用“交易预期”视角写：别喊利好/利空，讲观察点",
            do_not_write="不要预测价格；不要把事件当确定结果；不要夸张措辞",
            recommended_post_type="thread",
            reason="事件日历适合做“可转发收藏”的热点型内容",
        )

    if input_type in {"hot_topic", "kol_post", "visual_sample"}:
        source_mode = _source_mode()
        if source_mode == "kol_signal_only":
            fact_anchor_status = "weak" if (related_url or related_text) else "none"
        else:
            fact_anchor_status = "medium" if (related_url or related_text) else "weak"
        need_source_research = source_mode == "kol_signal_only" and fact_anchor_status in {"weak", "none"}
        allowed_to_generate = not need_source_research and fact_anchor_status in {"strong", "medium"}
        worth_spending = allowed_to_generate
        publish_mode = "queue_review" if allowed_to_generate else "monitor"
        template_type = "macro_human_scene" if _detect_macro_scene(text) else ("hot_explainer" if allowed_to_generate else "none")
        return base(
            is_hot_topic=True,
            worth_spending_claude=worth_spending,
            allowed_to_generate=allowed_to_generate,
            hotness_score=64,
            angle_score=70,
            user_impact_score=68,
            visual_potential_score=55,
            fact_anchor_status=fact_anchor_status,
            source_mode=source_mode,
            need_source_research=need_source_research,
            template_type=template_type,
            publish_mode=publish_mode,
            risk_level="medium",
            core_angle="宏观压力从报告走进现实动作" if template_type == "macro_human_scene" else "先讲清楚为什么在聊",
            user_impact_angle="先区分已知/未知，再谈影响",
            why_people_care="热点背后有传播角度与风险边界",
            missing_facts=["需要补充原新闻/官方来源/链上截图"] if need_source_research else [],
            safe_angle="先解释“为什么大家在聊”，再明确“哪些点是已知/未知”",
            do_not_write="不要把传闻写成事实；不要价格预测；不要引战",
            recommended_post_type="comment_hook" if allowed_to_generate else "monitor",
            reason="KOL-only 且事实不足：只监控并提示补事实" if need_source_research else "有一定角度空间，可进入人工审核",
        )

    return base(
        is_hot_topic=False,
        worth_spending_claude=False,
        allowed_to_generate=False,
        hotness_score=45,
        angle_score=40,
        user_impact_score=40,
        visual_potential_score=30,
        fact_anchor_status=_fact_anchor_status(),
        source_mode=_source_mode(),
        need_source_research=True,
        template_type="none",
        publish_mode="monitor",
        risk_level="medium",
        core_angle="先确认来源，再决定是否跟进",
        user_impact_angle="",
        why_people_care="",
        missing_facts=["需要补充事实锚点/来源链接"],
        safe_angle="先确认来源，再决定是否跟进",
        do_not_write="不要写成确定事实；不要价格预测",
        recommended_post_type="monitor",
        reason="类型不匹配或信息不完整，先监控",
    )


def _try_llm_evaluate(root: Path, row: sqlite3.Row) -> tuple[dict[str, Any] | None, str]:
    system_prompt = (root / "prompts" / "evaluate_v0_2.md").read_text(encoding="utf-8")
    user_payload = {
        "id": row["id"],
        "input_type": row["input_type"],
        "source_tool": row["source_tool"],
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "raw_text": row["raw_text"],
        "related_coinmeta_news_url": row["related_coinmeta_news_url"],
        "related_coinmeta_news_text": row["related_coinmeta_news_text"],
        "news_card_image": row["news_card_image"],
        "lang": row["lang"],
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)
    r = call_llm(
        task_type="evaluate_hot_input",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        expect_json=True,
        temperature=0.4,
        max_tokens=1200,
    )
    if not r.get("ok"):
        raw_out = str(r.get("content") or "")
        if raw_out:
            _write_debug_output(
                root,
                task_type="evaluate_hot_input",
                input_id=int(row["id"]),
                err=str(r.get("error") or "llm failed"),
                raw_output=raw_out,
            )
        return None, str(r.get("error") or "llm failed")
    obj = r.get("json")
    if not isinstance(obj, dict):
        return None, "llm json is not an object"

    required = [
        "is_hot_topic",
        "worth_spending_claude",
        "allowed_to_generate",
        "hotness_score",
        "angle_score",
        "user_impact_score",
        "visual_potential_score",
        "fact_anchor_status",
        "source_mode",
        "need_source_research",
        "template_type",
        "publish_mode",
        "risk_level",
        "core_angle",
        "user_impact_angle",
        "why_people_care",
        "missing_facts",
        "safe_angle",
        "do_not_write",
        "recommended_post_type",
        "reason",
    ]
    if not all(k in obj for k in required):
        return None, "llm output missing keys"
    if obj.get("publish_mode") == "auto_publish":
        obj["publish_mode"] = "queue_review"
    if (obj.get("source_mode") == "kol_signal_only") and (obj.get("fact_anchor_status") in {"weak", "none"}):
        obj["allowed_to_generate"] = False
        obj["publish_mode"] = "monitor"
        obj["need_source_research"] = True
    return obj, ""


def main() -> None:
    root = _project_root()
    cfg = _load_simple_yaml(root / "config.yaml")
    _setup_logging(root, cfg)

    _ = (root / "prompts" / "evaluate_v0_2.md").read_text(encoding="utf-8")

    db_path = root / (cfg.get("db_path") or "hot_follow.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    max_items_raw = (os.getenv("MAX_ITEMS_PER_RUN") or "").strip()
    max_items: int | None = None
    if max_items_raw:
        try:
            v = int(max_items_raw)
            if v > 0:
                max_items = v
        except ValueError:
            max_items = None

    if max_items is None:
        rows = conn.execute(
            "SELECT * FROM hot_inputs WHERE status = 'new' ORDER BY id ASC;"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM hot_inputs WHERE status = 'new' ORDER BY id ASC LIMIT ?;",
            (max_items,),
        ).fetchall()

    if not rows:
        logging.info("no_new_inputs db=%s", db_path)
        print("[evaluate_hot_input] ok evaluated=0")
        return

    prompt_version = "v0.2"
    evaluated = 0
    now = _utc_now_iso()

    model_runtime = (
        (os.getenv("EVALUATE_MODEL_RUNTIME") or "").strip().lower()
        or (os.getenv("MODEL_RUNTIME") or "").strip().lower()
        or "mock"
    )
    if model_runtime not in {"mock", "openrouter"}:
        model_runtime = "mock"
    use_model = False
    logging.info(
        "evaluate_config runtime=%s max_items_per_run=%s",
        model_runtime,
        max_items if max_items is not None else "all",
    )
    if model_runtime == "openrouter":
        logging.info("evaluate_hot_input legacy_mock_only=true reason=hot_engine_rulebook_first")

    for row in rows:
        obj: dict[str, Any] | None = None
        fallback_reason = ""

        if use_model:
            prev = os.environ.get("MODEL_RUNTIME")
            os.environ["MODEL_RUNTIME"] = model_runtime
            try:
                llm_obj, err = _try_llm_evaluate(root=root, row=row)
            finally:
                if prev is None:
                    os.environ.pop("MODEL_RUNTIME", None)
                else:
                    os.environ["MODEL_RUNTIME"] = prev
            if llm_obj is not None:
                obj = llm_obj
            else:
                fallback_reason = err or "llm failed"
                log_llm_failure("evaluate_hot_input", fallback_reason)

        if obj is None:
            obj = _mock_evaluate(row)
            if use_model and fallback_reason:
                obj["fallback_reason"] = fallback_reason

        evaluation_json = json.dumps(obj, ensure_ascii=False, sort_keys=True)

        conn.execute(
            """
            INSERT OR REPLACE INTO hot_evaluations (
              input_id,
              is_hot_topic, hotness_score,
              algorithm_fit_score, reply_potential_score, retweet_potential_score,
              dwell_time_score, visual_potential_score, coinmeta_angle_score,
              fact_anchor_status, template_type, publish_mode, risk_level,
              safe_angle, do_not_write, interaction_trigger, recommended_post_type,
              evaluation_json, prompt_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                row["id"],
                1 if obj.get("is_hot_topic") else 0,
                int(obj.get("hotness_score", 0)),
                int(obj.get("angle_score", 0)),
                0,
                0,
                int(obj.get("user_impact_score", 0)),
                int(obj.get("visual_potential_score", 0)),
                int(obj.get("angle_score", 0)),
                obj.get("fact_anchor_status"),
                obj.get("template_type"),
                obj.get("publish_mode"),
                obj.get("risk_level"),
                obj.get("safe_angle"),
                obj.get("do_not_write"),
                "",
                obj.get("recommended_post_type"),
                evaluation_json,
                prompt_version,
                now,
            ),
        )

        pm = (obj.get("publish_mode") or "").strip()
        next_status = "evaluated"
        if pm == "reject":
            next_status = "rejected"
        elif pm == "monitor":
            next_status = "monitor"
        conn.execute(
            "UPDATE hot_inputs SET status = ?, updated_at = ? WHERE id = ?;",
            (next_status, now, row["id"]),
        )

        evaluated += 1

    conn.commit()
    conn.close()

    logging.info("evaluated=%s db=%s", evaluated, db_path)
    print(f"[evaluate_hot_input] ok evaluated={evaluated}")


if __name__ == "__main__":
    main()
