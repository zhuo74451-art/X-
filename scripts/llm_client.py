from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _env_int(key: str, default: int) -> int:
    s = _env(key, str(default))
    try:
        return int(s)
    except ValueError:
        return default


def _runtime() -> str:
    v = _env("MODEL_RUNTIME", "mock").lower().strip()
    if v not in {"mock", "openrouter"}:
        return "mock"
    return v


def load_openrouter_api_key() -> str:
    env_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if env_key:
        return env_key

    secret_path = _project_root() / "local_only" / "openrouter_api_key.txt"
    if secret_path.exists():
        key = (secret_path.read_text(encoding="utf-8") or "").strip()
        if key:
            return key

    return ""


def _strip_code_fences(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _content_preview(text: str, limit: int = 1000) -> str:
    s = (text or "").replace("\r\n", "\n").strip()
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _extract_first_json_object(text: str) -> str | None:
    s = text or ""
    start = s.find("{")
    if start < 0:
        return None

    in_str = False
    esc = False
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def _parse_json_from_content(content: str) -> tuple[dict | None, str]:
    raw = content or ""

    fenced = re.search(r"```json\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        fenced_body = fenced.group(1).strip()
        try:
            objf = json.loads(fenced_body)
            if isinstance(objf, dict):
                return objf, ""
            return None, "parsed json is not an object"
        except json.JSONDecodeError as e:
            return None, f"json parse failed: {e}"

    s = _strip_code_fences(raw)
    if not s:
        return None, "empty content"

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj, ""
        return None, "parsed json is not an object"
    except json.JSONDecodeError:
        pass

    candidate = _extract_first_json_object(s)
    if not candidate:
        if s.lstrip().startswith("{"):
            return None, "no json object found in content | likely_truncated_json=true"
        return None, "no json object found in content"

    try:
        obj2 = json.loads(candidate)
        if isinstance(obj2, dict):
            return obj2, ""
        return None, "extracted json is not an object"
    except json.JSONDecodeError as e:
        return None, f"json parse failed: {e}"


def _result_template(runtime: str, model: str) -> dict[str, Any]:
    return {
        "ok": False,
        "runtime": runtime,
        "model": model,
        "content": "",
        "content_preview": "",
        "json": {},
        "json_parse_error": "",
        "error": "",
        "raw": {},
        "raw_output_path": "",
    }


def _mock_eval_json(user_prompt: str) -> dict[str, Any]:
    t = (user_prompt or "").lower()

    def pick_template() -> str:
        if "coinmeta_newsflash" in t:
            return "news_card_take"
        if "authority_post" in t:
            return "authority_quote_plus"
        if "quick_data" in t:
            return "quick_data_take"
        if "event_calendar" in t:
            return "event_calendar_watch"
        return "hot_explainer"

    template_type = pick_template()
    publish_mode = "queue_review"
    risk_level = "low"
    fact_anchor_status = "medium"

    if any(x in t for x in ["junk", "airdrop", "1000x", "稳赚", "私信", "加群", "白名单"]):
        publish_mode = "reject"
        risk_level = "low"
        fact_anchor_status = "none"
    elif any(x in t for x in ["controversy", "传闻", "被攻击", "被黑", "hack", "hacked", "exploit", "限制提币"]):
        publish_mode = "monitor"
        risk_level = "high"
        fact_anchor_status = "weak"

    return {
        "is_hot_topic": publish_mode != "reject",
        "hotness_score": 65 if publish_mode != "reject" else 10,
        "algorithm_fit_score": 65 if publish_mode != "reject" else 5,
        "reply_potential_score": 60 if publish_mode != "reject" else 0,
        "retweet_potential_score": 55 if publish_mode != "reject" else 0,
        "dwell_time_score": 58 if publish_mode != "reject" else 0,
        "visual_potential_score": 70 if template_type in {"news_card_take", "event_calendar_watch"} else 55,
        "coinmeta_angle_score": 68 if publish_mode != "reject" else 0,
        "fact_anchor_status": fact_anchor_status,
        "template_type": template_type,
        "publish_mode": publish_mode,
        "risk_level": risk_level,
        "safe_angle": "提炼一个“为什么值得看”的角度，别复读标题",
        "do_not_write": "不要价格预测；不要制造FOMO；不要把传闻写成事实",
        "interaction_trigger": "你觉得这条的关键变量是什么？",
        "recommended_post_type": "visual_post" if template_type == "news_card_take" else "short_post",
        "reason": "mock 评估：用于本地兜底",
    }


def _mock_draft_json(user_prompt: str) -> dict[str, Any]:
    t = (user_prompt or "").lower()
    template_type = "hot_explainer"
    if '"template_type"' in t:
        if "news_card_take" in t:
            template_type = "news_card_take"
        elif "authority_quote_plus" in t:
            template_type = "authority_quote_plus"
        elif "quick_data_take" in t:
            template_type = "quick_data_take"
        elif "event_calendar_watch" in t:
            template_type = "event_calendar_watch"

    if template_type == "news_card_take":
        main = "这条消息的重点，不在标题里。\n\n真正值得看的不是表层信息，而是它背后的市场变化。\n\n配图：币界网快讯卡片"
        visual = "复用币界网快讯卡片。"
    elif template_type == "authority_quote_plus":
        main = "这条权威来源的信息值得看。\n\n先把事实讲清楚，再谈它可能意味着什么。\n\n真正值得看的不是金额，而是行为变化。"
        visual = "data_terminal_style：深色背景，真实截图优先，不编造数字。"
    elif template_type == "quick_data_take":
        main = "这个数据不能只看表面。\n\n真正值得看的不是涨跌，而是资金/叙事有没有同步变化。\n\n保持克制，不做价格预测。"
        visual = "data_terminal_style：深色背景，真实数据截图优先，不编造数字。"
    elif template_type == "event_calendar_watch":
        main = "本周/下周加密市场有几件事值得关注：\n\n1) 事件A\n2) 事件B\n3) 事件C\n\n市场交易的，往往不是结果，而是预期。"
        visual = "research_infographic_style：时间线/清单长图，分层结构。"
    else:
        main = "为什么市场突然开始讨论这个？\n\n核心原因有三个：\n1) 叙事\n2) 资金\n3) 传播\n\n真正值得关注的不是热度，而是它是否进入下一轮定价。"
        visual = "research_infographic_style：三点解释+一句总结的信息图。"

    return {
        "main_post_cn": main,
        "first_comment_cn": "首评：补充背景/观察指标/一个评论区问题（不要复读主帖）。",
        "visual_prompt_cn": visual,
        "risk_note": "保持克制，不做价格预测。",
    }


def _ensure_llm_debug_dir() -> Path:
    p = _project_root() / "logs" / "llm_debug"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_raw_output(*, skill_name: str, input_id: str, raw_text: str) -> str:
    d = _ensure_llm_debug_dir()
    safe_skill = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (skill_name or "unknown")).strip("_")
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (input_id or "noid")).strip("_")
    fp = d / f"{_now_utc_compact()}_{safe_skill}_{safe_id}.txt"
    fp.write_text(raw_text or "", encoding="utf-8")
    return str(fp)


def _append_call_log(payload: dict[str, Any]) -> None:
    p = _project_root() / "logs" / "llm_calls.jsonl"
    line = json.dumps(payload, ensure_ascii=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _call_openrouter_chat(
    *,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout_s: int,
) -> tuple[str, dict[str, Any]]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    req = urllib.request.Request(
        url=OPENROUTER_BASE_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://coinmeta.local",
            "X-Title": "CoinMeta Hot Engine",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    j = json.loads(raw)
    content = j["choices"][0]["message"]["content"]
    return str(content), j


def _call_openrouter_result(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout_s: int,
    skill_name: str,
    input_id: str,
) -> dict[str, Any]:
    api_key = load_openrouter_api_key()
    model = _env("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")

    res = _result_template("openrouter", model)
    if not api_key:
        res["error"] = "OPENROUTER_API_KEY is missing"
        return res

    try:
        content, raw_j = _call_openrouter_chat(
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        res["ok"] = True
        res["content"] = content
        res["raw"] = raw_j
        res["raw_output_path"] = _write_raw_output(skill_name=skill_name, input_id=input_id, raw_text=content)
        return res
    except TimeoutError:
        res["error"] = "openrouter timeout"
        res["raw"] = {"error_type": "TimeoutError"}
        return res
    except urllib.error.HTTPError as e:
        status_code = getattr(e, "code", None)
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""

        parsed_body: Any = None
        msg = ""
        err_code = ""
        metadata: Any = None
        if body_text:
            try:
                parsed_body = json.loads(body_text)
                if isinstance(parsed_body, dict):
                    err_obj = parsed_body.get("error")
                    if isinstance(err_obj, dict):
                        msg = str(err_obj.get("message") or "")
                        err_code = str(err_obj.get("code") or "")
                        metadata = err_obj.get("metadata")
            except json.JSONDecodeError:
                parsed_body = None

        safe_summary = body_text.strip().replace("\r\n", "\n")
        if len(safe_summary) > 500:
            safe_summary = safe_summary[:500] + "…"

        res["raw"] = {
            "status_code": status_code,
            "error_code": err_code,
            "metadata": metadata,
            "body_json": parsed_body if isinstance(parsed_body, (dict, list)) else None,
            "body_text_preview": safe_summary,
        }

        parts = [f"openrouter http error: {status_code}"]
        if msg:
            parts.append(f"message={msg}")
        if err_code:
            parts.append(f"code={err_code}")
        if safe_summary and not msg:
            parts.append(f"body_preview={safe_summary}")
        res["error"] = " | ".join(parts)
        return res
    except urllib.error.URLError as e:
        res["error"] = f"openrouter url error: {e.reason}"
        return res
    except (KeyError, ValueError) as e:
        res["error"] = f"openrouter response parse error: {e}"
        return res
    except Exception as e:
        res["error"] = f"openrouter call failed: {type(e).__name__}"
        res["raw"] = {"error_type": type(e).__name__, "message": str(e)[:300]}
        return res

def _skill_prompt_path(skill_name: str) -> Path:
    return _project_root() / "skills" / str(skill_name) / "prompt.md"


def _read_skill_prompt(skill_name: str) -> str:
    p = _skill_prompt_path(skill_name)
    if not p.exists():
        raise FileNotFoundError(f"skill prompt not found: {p}")
    return p.read_text(encoding="utf-8")


def _infer_input_id(input_pack: dict[str, Any]) -> str:
    for k in ("input_id", "event_cluster_id", "id"):
        v = str(input_pack.get(k) or "").strip()
        if v:
            return v
    return str(input_pack.get("column_name") or "pack").strip() or "pack"


def _mock_skill_output(skill_name: str) -> dict[str, Any]:
    if skill_name == "coinmeta_whale_digest":
        return {
            "main_post": "今天巨鲸这条线更像在做「风险再定价」：有人加仓、有人补保证金，盘口紧张感在上升。\n\n重点不是某一笔交易，而是：大仓位在硬扛波动，市场会先盯清算线。",
            "first_comment": "边界：不要把「可能清算」写成「确定爆仓」。\n\n观察点：是否继续补保证金、是否出现被动减仓、是否有交易所净流入配合。\n\n如来源偏二手，建议补链上/看板链接后再发布。",
            "visual_prompt": "信息图：按actor汇总「净方向/净额/风险变化」，标注补保证金与清算风险。",
            "editor_risk_note": "避免暗示跟单；避免价格预测；对低置信度信息务必标注待核验。",
            "need_fact_check": False,
            "weak_points": [],
        }
    if skill_name == "coinmeta_hot_post":
        return {
            "main_post": "这条消息别只当成快讯看。\n\n真正值得看的，是它把「行业叙事」推进到了「用户动作/风险边界」这一步。\n\n一句话：热度不等于机会，关键是下一步证据会落在哪里。",
            "first_comment": "补充三点：\n1) 事实锚点来自哪里（best_source/source_urls）\n2) 这条线后续该盯哪个确认信号\n3) 风险边界：哪些话不能写成确定结论",
            "visual_prompt": "一张信息图：标题一句话 + 三个观察点 + 来源锚点（不做价格预测）。",
            "editor_risk_note": "避免公告腔；避免强断言；避免外链默认外带。",
            "need_fact_check": False,
            "weak_points": [],
        }
    return {
        "main_post": "",
        "first_comment": "",
        "visual_prompt": "",
        "editor_risk_note": "",
        "need_fact_check": True,
        "weak_points": ["unknown skill"],
    }


def call_llm_task(
    *,
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    expect_json: bool = True,
    temperature: float = 0.4,
    max_tokens: int = 1800,
) -> dict[str, Any]:
    runtime = _runtime()
    model = _env("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
    timeout_s = _env_int("MODEL_TIMEOUT_SECONDS", 90)
    created_at = _now_utc_compact()
    input_id = "task"

    if runtime == "mock":
        res = _result_template("mock", "mock")
        if task_type == "evaluate_hot_input":
            obj = _mock_eval_json(user_prompt)
        elif task_type == "generate_hot_draft":
            obj = _mock_draft_json(user_prompt)
        else:
            obj = {}
        res["ok"] = True
        res["json"] = obj if isinstance(obj, dict) else {}
        res["content"] = json.dumps(res["json"], ensure_ascii=False)
        _append_call_log(
            {
                "task_type": task_type,
                "skill_name": "",
                "prompt_version": "",
                "model": "mock",
                "created_at": created_at,
                "input_id": input_id,
                "raw_output_path": "",
            }
        )
        return res

    res = _call_openrouter_result(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        skill_name=task_type,
        input_id=input_id,
    )

    _append_call_log(
        {
            "task_type": task_type,
            "skill_name": "",
            "prompt_version": "",
            "model": model,
            "created_at": created_at,
            "input_id": input_id,
            "raw_output_path": res.get("raw_output_path") or "",
        }
    )

    if not expect_json:
        return res

    if not res.get("content"):
        if res.get("ok"):
            res["ok"] = False
            res["error"] = res.get("error") or "empty content"
        return res

    parsed, err = _parse_json_from_content(str(res["content"]))
    if parsed is None:
        res["ok"] = False
        res["json_parse_error"] = err or "json parse failed"
        res["content_preview"] = _content_preview(str(res.get("content") or ""), 1000)
        res["error"] = res["json_parse_error"]
        return res

    res["json"] = parsed
    return res


def call_llm_skill(skill_name: str, input_pack: dict[str, Any], prompt_version: str = "v0.1") -> dict[str, Any]:
    runtime = _runtime()
    model = _env("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
    timeout_s = _env_int("MODEL_TIMEOUT_SECONDS", 90)
    created_at = _now_utc_compact()
    input_id = _infer_input_id(input_pack)

    if runtime == "mock":
        out = _mock_skill_output(skill_name)
        _append_call_log(
            {
                "task_type": "skill_call",
                "skill_name": skill_name,
                "prompt_version": prompt_version,
                "model": "mock",
                "created_at": created_at,
                "input_id": input_id,
                "raw_output_path": "",
            }
        )
        return {
            "ok": True,
            "runtime": "mock",
            "model": "mock",
            "output": out,
            "error": "",
            "raw_output_path": "",
        }

    try:
        prompt = _read_skill_prompt(skill_name)
    except FileNotFoundError as e:
        _append_call_log(
            {
                "task_type": "skill_call",
                "skill_name": skill_name,
                "prompt_version": prompt_version,
                "model": model,
                "created_at": created_at,
                "input_id": input_id,
                "raw_output_path": "",
            }
        )
        return {
            "ok": False,
            "runtime": runtime,
            "model": model,
            "output": {},
            "error": str(e),
            "raw_output_path": "",
        }

    user_prompt = (
        "你会收到一个 JSON 输入 input_pack。只能基于输入，不得编造。\n"
        "只输出 JSON（不要输出解释文字、不要输出 markdown/代码块）。\n\n"
        "input_pack:\n"
        + json.dumps(input_pack, ensure_ascii=False)
    )

    res = _call_openrouter_result(
        system_prompt=prompt,
        user_prompt=user_prompt,
        temperature=0.4,
        max_tokens=1800,
        timeout_s=timeout_s,
        skill_name=skill_name,
        input_id=input_id,
    )

    _append_call_log(
        {
            "task_type": "skill_call",
            "skill_name": skill_name,
            "prompt_version": prompt_version,
            "model": model,
            "created_at": created_at,
            "input_id": input_id,
            "raw_output_path": res.get("raw_output_path") or "",
        }
    )

    if not res.get("ok"):
        return {
            "ok": False,
            "runtime": runtime,
            "model": model,
            "output": {},
            "error": res.get("error") or "openrouter failed",
            "raw_output_path": res.get("raw_output_path") or "",
        }

    parsed, err = _parse_json_from_content(str(res.get("content") or ""))
    if parsed is None:
        raw_path = res.get("raw_output_path") or _write_raw_output(
            skill_name=skill_name, input_id=input_id, raw_text=str(res.get("content") or "")
        )
        return {
            "ok": False,
            "runtime": runtime,
            "model": model,
            "output": {},
            "error": err or "json parse failed",
            "raw_output_path": raw_path,
        }

    return {
        "ok": True,
        "runtime": runtime,
        "model": model,
        "output": parsed,
        "error": "",
        "raw_output_path": res.get("raw_output_path") or "",
    }


def call_llm(*args: Any, **kwargs: Any) -> dict[str, Any]:
    if kwargs.get("skill_name") is not None or kwargs.get("input_pack") is not None:
        return call_llm_skill(
            skill_name=str(kwargs.get("skill_name") or ""),
            input_pack=kwargs.get("input_pack") or {},
            prompt_version=str(kwargs.get("prompt_version") or "v0.1"),
        )
    if args and len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], dict):
        return call_llm_skill(skill_name=args[0], input_pack=args[1], prompt_version=str(kwargs.get("prompt_version") or "v0.1"))

    task_type = kwargs.get("task_type") or (args[0] if len(args) >= 1 else "")
    system_prompt = kwargs.get("system_prompt") or (args[1] if len(args) >= 2 else "")
    user_prompt = kwargs.get("user_prompt") or (args[2] if len(args) >= 3 else "")
    expect_json = bool(kwargs.get("expect_json", True))
    temperature = float(kwargs.get("temperature", 0.4))
    max_tokens = int(kwargs.get("max_tokens", 1800))
    return call_llm_task(
        task_type=str(task_type),
        system_prompt=str(system_prompt),
        user_prompt=str(user_prompt),
        expect_json=expect_json,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def log_llm_failure(task_type: str, err: str) -> None:
    safe_err = (err or "").strip()
    if not safe_err:
        safe_err = "unknown error"
    logging.warning("llm_failed task_type=%s err=%s", task_type, safe_err)

