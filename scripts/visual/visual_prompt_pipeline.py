from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _slug(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return h


def _s(x: Any) -> str:
    return str(x or "").strip()


def _split_lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def detect_input_type(text: str) -> dict[str, Any]:
    t = text or ""
    lo = t.lower()
    signals: list[str] = []

    post_signals = 0
    raw_signals = 0

    if "主帖" in t:
        post_signals += 2
        signals.append("contains_主帖")
    if "首评" in t:
        post_signals += 2
        signals.append("contains_首评")
    if "main_post" in lo or "first_comment" in lo:
        post_signals += 2
        signals.append("contains_main_post_or_first_comment")
    if "—" in t or "——" in t:
        post_signals += 1
        signals.append("contains_em_dash")

    if "来源" in t or "原文" in t or "公告" in t:
        raw_signals += 2
        signals.append("contains_source_marker")
    if "http://" in lo or "https://" in lo or "www." in lo:
        raw_signals += 2
        signals.append("contains_url")
    if "截图" in t or "ocr" in lo:
        raw_signals += 1
        signals.append("contains_screenshot_or_ocr")
    if "推文" in t:
        raw_signals += 1
        signals.append("contains_tweet_marker")

    detected = "raw"
    if post_signals >= 3 and raw_signals == 0:
        detected = "post"
    elif raw_signals >= 3 and post_signals == 0:
        detected = "raw"
    elif post_signals >= 3 and raw_signals >= 2:
        detected = "mixed"
    else:
        paras = [p for p in re.split(r"\n\s*\n", t) if p.strip()]
        if len(paras) >= 4 and raw_signals <= 1:
            detected = "post"
            signals.append("multi_paragraph_draft_like")
        elif raw_signals >= 2:
            detected = "raw"

    conf = 0.55 + 0.08 * min(5, abs(post_signals - raw_signals))
    if detected == "mixed":
        conf = min(conf, 0.72)
    return {
        "detected_input_type": detected,
        "confidence": round(float(conf), 2),
        "signals": signals[:12],
        "post_signals": post_signals,
        "raw_signals": raw_signals,
    }


def _load_override(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        return {}
    try:
        obj = _read_json(path)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _merge_blocks(auto_blocks: list[dict[str, Any]], override_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = max(len(auto_blocks), len(override_blocks), 3)
    for i in range(n):
        base = auto_blocks[i] if i < len(auto_blocks) and isinstance(auto_blocks[i], dict) else {}
        ov = override_blocks[i] if i < len(override_blocks) and isinstance(override_blocks[i], dict) else {}
        merged = dict(base)
        for k in ["label", "line_1", "line_2", "line_3"]:
            v = ov.get(k)
            if isinstance(v, str) and v.strip() != "":
                merged[k] = v.strip()
        out.append(merged)
    return out[:3]


def _parse_post_sections(text: str) -> dict[str, Any]:
    lines = _split_lines(text)
    mode = "unknown"
    main: list[str] = []
    comment: list[str] = []
    other: list[str] = []

    for ln in lines:
        s = ln.strip()
        if s in {"主帖", "主贴"}:
            mode = "main"
            continue
        if s in {"首评", "首条评论", "评论"}:
            mode = "comment"
            continue
        if mode == "main":
            main.append(ln)
        elif mode == "comment":
            comment.append(ln)
        else:
            other.append(ln)

    main_post = "\n".join([x for x in main]).strip()
    first_comment = "\n".join([x for x in comment]).strip()
    rest = "\n".join([x for x in other]).strip()
    if not main_post and rest:
        main_post = rest
    return {
        "main_post": main_post,
        "first_comment": first_comment,
        "unstructured_rest": rest,
    }


def extract_visual_facts(text: str) -> dict[str, Any]:
    t = text or ""
    lo = t.lower()

    known_entities = [
        "马斯克",
        "特朗普",
        "OpenAI",
        "CoinMeta",
        "币界网",
        "BTC",
        "ETH",
        "Solana",
        "SOL",
        "BNB",
        "美联储",
        "法院",
        "北京",
        "旧金山",
        "香港",
        "中东",
        "欧洲",
        "美国",
        "Binance",
        "Coinbase",
        "CZ",
        "Vitalik",
        "SBF",
    ]

    entities: list[str] = []
    for e in known_entities:
        if e.lower() in lo:
            entities.append(e)
        elif e in t:
            entities.append(e)

    tickers = sorted(set(re.findall(r"\b[A-Z]{2,6}\b", t)))
    for tk in tickers:
        if tk in {"USD", "CNY"}:
            continue
        if tk not in entities:
            entities.append(tk)

    numbers: list[str] = []
    numbers += re.findall(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", t)
    numbers += re.findall(r"\b\d+(?:\.\d+)?\s*%\b", t)
    numbers += re.findall(r"\b\d+(?:\.\d+)?\s*(?:万)?美元\b", t)
    numbers += re.findall(r"\b\d+(?:\.\d+)?\s*(?:ETH|BTC)\b", t, flags=re.IGNORECASE)
    numbers = [x.replace(" ", "") for x in numbers]
    numbers = list(dict.fromkeys(numbers))[:30]

    dates: list[str] = []
    dates += re.findall(r"\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b", t)
    dates += re.findall(r"\b\d{1,2}月\d{1,2}日\b", t)
    dates += [x for x in ["本周三", "周四", "本周", "今天", "昨日", "过去24小时"] if x in t]
    dates = list(dict.fromkeys(dates))[:20]

    locations = [x for x in ["北京", "旧金山", "美国", "香港", "中东", "欧洲"] if x in t]
    locations = list(dict.fromkeys(locations))[:10]

    legal_terms = [x for x in ["法院", "法官", "律师", "取证", "传唤", "出庭", "禁止", "批准", "法律", "诉讼", "案件", "陈词"] if x in t]
    market_terms = [x for x in ["宏观", "趋势", "政策", "监管", "利率", "CPI", "ETF", "美元流动性"] if x in t or x.lower() in lo]
    chain_terms = [x for x in ["巨鲸", "链上", "地址", "钱包", "转入", "转出", "持仓", "清算", "多单", "空单", "USDT", "USDC", "ETH", "BTC"] if x in t or x.lower() in lo]
    product_terms = [x for x in ["工具", "产品", "平台", "Agent", "钱包", "协议", "功能", "使用", "适合", "指标", "参数", "兼容"] if x in t or x.lower() in lo]
    risk_terms = [x for x in ["据称", "传闻", "知情人士", "尚未确认", "可能", "或将", "等待确认", "争议", "未经证实"] if x in t]

    quotes = re.findall(r"「([^」]{2,80})」", t)[:10]
    key_phrases = []
    for kw in ["随时传唤", "联邦法院", "最后取证日", "结束陈词", "出境", "旅行禁令", "等待确认", "链上", "清算价"]:
        if kw in t:
            key_phrases.append(kw)
    key_phrases = list(dict.fromkeys(key_phrases))[:20]

    summary_candidates: list[str] = []
    for sent in re.split(r"[。\n]", t):
        s = sent.strip()
        if not s:
            continue
        if any(x in s for x in ["传唤", "法院", "法官", "取证", "陈词", "尚待", "等待确认", "知情人士"]):
            summary_candidates.append(s)
    summary_candidates = summary_candidates[:10]

    topic = ""
    if "马斯克" in t and "北京" in t:
        topic = "马斯克/特朗普/北京行传闻"
    elif legal_terms:
        topic = "法律/诉讼相关"
    elif chain_terms:
        topic = "链上/巨鲸动态"
    elif product_terms:
        topic = "产品/工具更新"
    else:
        topic = "热点事件"

    return {
        "topic": topic,
        "entities": sorted(set(entities))[:30],
        "key_phrases": key_phrases,
        "numbers": numbers,
        "dates": dates,
        "locations": locations,
        "quotes": quotes,
        "legal_terms": legal_terms,
        "market_terms": market_terms,
        "chain_terms": chain_terms,
        "product_terms": product_terms,
        "risk_terms": risk_terms,
        "summary_candidates": summary_candidates,
    }


ROUTE_NAMES = {
    "A": "观点表达 / 阵营冲突 / 拟人化社论图",
    "B": "百科信息图 / 一图看懂 / 知识解释型海报",
    "C": "奇幻图鉴 / 收藏型设定海报",
    "D": "数据信息卡 / 金融终端风 / Daily Whale Digest",
    "E": "国家剪影拼贴 / 地缘政治叙事封面",
    "F": "360 全景空间 / 沉浸式漫游",
    "G": "液态玻璃 Bento / 产品说明卡",
    "H": "平台 UI 样机 / 社交互动叠层",
    "I": "情绪概念摄影 / 思维可视化",
}


def route_visual_type(facts: dict[str, Any], input_text: str, forced_route: str | None = None) -> dict[str, Any]:
    forced = _s(forced_route).upper()
    if forced:
        return {
            "selected_route": forced,
            "selected_route_name": ROUTE_NAMES.get(forced, ""),
            "forced_route": True,
            "forced_route_value": forced,
            "scores": {k: 0 for k in ROUTE_NAMES.keys()},
            "reason_by_rule": [f"forced by --route {forced}"],
            "not_selected": {},
        }

    scores = {k: 0 for k in ROUTE_NAMES.keys()}
    reasons: list[str] = []
    not_selected: dict[str, str] = {}

    chain_terms = set(facts.get("chain_terms") or [])
    product_terms = set(facts.get("product_terms") or [])
    legal_terms = set(facts.get("legal_terms") or [])
    market_terms = set(facts.get("market_terms") or [])
    locations = set(facts.get("locations") or [])
    risk_terms = set(facts.get("risk_terms") or [])
    numbers = facts.get("numbers") or []

    def has_any(keys: list[str], hay: set[str]) -> bool:
        return any(k in hay for k in keys)

    if has_any(["巨鲸", "链上", "钱包", "地址"], chain_terms):
        scores["D"] += 3
        reasons.append("命中链上/地址/钱包关键词（D +3）")
    if has_any(["BTC", "ETH", "USDT", "USDC"], chain_terms):
        scores["D"] += 2
        reasons.append("命中主流资产关键词（D +2）")
    if has_any(["持仓", "清算", "多单", "空单", "转入", "转出"], chain_terms):
        scores["D"] += 2
        reasons.append("命中仓位/清算/多空关键词（D +2）")
    if isinstance(numbers, list) and len(numbers) >= 3:
        scores["D"] += 2
        reasons.append("数字数量 >= 3（D +2）")

    if product_terms:
        scores["G"] += 3
        reasons.append("命中产品/工具/平台关键词（G +3）")
    if any(x in input_text for x in ["适合谁", "价格", "参数", "兼容"]):
        scores["G"] += 2
        reasons.append("命中参数/适合/价格（G +2）")

    if any(x in input_text for x in ["什么是", "一图看懂", "机制", "原理", "架构"]):
        scores["B"] += 3
        reasons.append("命中机制/原理/一图看懂（B +3）")
    if any(x in input_text for x in ["生态", "结构", "流程", "组成", "步骤"]):
        scores["B"] += 2
        reasons.append("命中结构/流程拆解（B +2）")

    if legal_terms or risk_terms or market_terms:
        if legal_terms:
            scores["I"] += 3
            reasons.append("命中法律/法院/传唤等不确定性关键词（I +3）")
        if risk_terms:
            scores["I"] += 2
            reasons.append("命中传闻/未确认类措辞（I +2）")
        if market_terms:
            scores["I"] += 2
            reasons.append("命中宏观/趋势/监管类议题（I +2）")
        if any(x in input_text for x in ["问题是", "反常", "灰区", "变数", "仍待确认"]):
            scores["I"] += 1
            reasons.append("命中文本不确定性叙事（I +1）")

    if locations and any(x in locations for x in ["北京", "美国", "香港", "中东", "欧洲"]):
        scores["E"] += 3
        reasons.append("命中地区/地缘位置（E +3）")
        if any(x in input_text for x in ["政策", "地缘", "宏观", "监管"]):
            scores["E"] += 2
            reasons.append("命中政策/地缘/监管（E +2）")

    if any(x in input_text for x in ["直播", "AMA", "评论", "用户提问", "互动", "社区"]):
        scores["H"] += 3
        reasons.append("命中互动/AMA/社区（H +3）")

    if any(x in input_text for x in ["vs", "对立", "互怼", "阵营", "争议"]):
        scores["A"] += 3
        reasons.append("命中对立/阵营/争议（A +3）")

    if any(x in input_text for x in ["图鉴", "物种", "世界观", "设定", "奇幻", "节日"]):
        scores["C"] += 3
        reasons.append("命中图鉴/设定/奇幻（C +3）")

    if any(x in input_text for x in ["360", "全景", "漫游", "虚拟展厅", "空间"]):
        scores["F"] += 3
        reasons.append("命中全景/空间/漫游（F +3）")

    selected = max(scores.items(), key=lambda kv: (kv[1], kv[0]))[0]
    if selected == "E" and scores["I"] >= scores["E"]:
        selected = "I"

    if selected != "D":
        not_selected["D"] = "未命中链上数据结构" if scores["D"] == 0 else f"D 分数不足（{scores['D']}）"
    if selected != "G":
        not_selected["G"] = "不是产品说明" if scores["G"] == 0 else f"G 分数不足（{scores['G']}）"
    if selected != "B":
        not_selected["B"] = "不是机制解释" if scores["B"] == 0 else f"B 分数不足（{scores['B']}）"

    return {
        "selected_route": selected,
        "selected_route_name": ROUTE_NAMES.get(selected, ""),
        "forced_route": False,
        "scores": scores,
        "reason_by_rule": reasons[:12],
        "not_selected": not_selected,
    }


def classify_visual_risk(facts: dict[str, Any], route: str) -> dict[str, Any]:
    entities = set(facts.get("entities") or [])
    legal_terms = set(facts.get("legal_terms") or [])
    risk_terms = set(facts.get("risk_terms") or [])

    flags: list[str] = []
    guardrails: list[str] = []

    public_figures = {"马斯克", "特朗普", "CZ", "Vitalik", "SBF"}
    if any(x in entities for x in public_figures):
        flags.append("public_figure")
        guardrails.append("不要使用真实公众人物肖像")

    if legal_terms:
        flags.append("legal_case")
        guardrails.append("不要把传闻/未确认内容画成既定事实")
        guardrails.append("避免使用真实法官/监管人员肖像与官方徽章")

    if risk_terms:
        flags.append("unconfirmed_claim")
        guardrails.append("画面需要保留“待确认/不确定性”氛围，不要下结论")

    logo_keywords = {"OpenAI", "Tesla", "SpaceX", "Binance", "Coinbase"}
    if any(x in entities for x in logo_keywords):
        flags.append("logo_risk")
        guardrails.append("不要使用任何公司/交易所 Logo")

    if route in {"D"}:
        guardrails.append("不要出现投资建议措辞（买入/卖出/跟单/稳赚/暴富）")
        guardrails.append("不要出现黑客盗币画面")
    if route in {"I"}:
        guardrails.append("不要做八卦风格，不要娱乐化")

    uniq_flags = list(dict.fromkeys(flags))
    uniq_guard = list(dict.fromkeys(guardrails))

    level = "low"
    if "legal_case" in uniq_flags and "public_figure" in uniq_flags:
        level = "medium_high"
    elif "legal_case" in uniq_flags or "unconfirmed_claim" in uniq_flags:
        level = "medium"
    elif "logo_risk" in uniq_flags:
        level = "medium"

    return {
        "risk_level": level,
        "risk_flags": uniq_flags,
        "visual_guardrails": uniq_guard,
    }


def _sentence_pick(text: str, keys: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for sent in re.split(r"[。\n]", text or ""):
        s = sent.strip()
        if not s:
            continue
        if any(k in s for k in keys):
            out.append(s)
    return out[:limit]


def build_image_text_pack(facts: dict[str, Any], route: str, text: str) -> dict[str, Any]:
    footer = "CoinMeta / 币界网"
    discarded: list[str] = []
    source_trace: list[dict[str, Any]] = []

    if route == "I":
        t = text or ""
        has_beijing = "北京" in t
        has_subpoena = "传唤" in t
        has_rumor = any(x in t for x in ["据称", "知情人士", "尚未确认", "传闻", "仍待确认"])
        has_policy = any(x in t for x in ["政策", "监管", "批准"])

        if has_subpoena and has_beijing:
            title = "随时传唤中的北京行？"
            subtitle = "行程传闻仍待确认"
        elif facts.get("legal_terms") and has_rumor:
            title = "法律灰区里的新变数"
            subtitle = "传闻仍待进一步确认"
        elif has_policy and has_beijing:
            title = "政策风向出现新信号"
            subtitle = "市场仍在等待确认"
        else:
            title = "一条仍待确认的关键线索"
            subtitle = "把不确定性画出来，而不是下结论"

        b1 = {
            "label": "法律状态",
            "line_1": "仍处于程序进行中",
            "line_2": "关键节点临近（取证/陈词）",
        }
        if "随时传唤" in t:
            b1["line_1"] = "仍处于「随时传唤」状态"
        if "联邦法院" in t:
            b1["line_2"] = "联邦法院程序仍在推进"

        rumor_sents = _sentence_pick(t, ["知情人士", "据称", "尚未确认", "传闻"], limit=2)
        b2 = {
            "label": "行程传闻",
            "line_1": "据称与行程相关",
            "line_2": "目前缺乏二手确认",
        }
        if has_beijing:
            b2["line_1"] = "据称与北京行相关"
        if rumor_sents:
            b2["line_2"] = rumor_sents[0][:18] + ("…" if len(rumor_sents[0]) > 18 else "")

        b3 = {
            "label": "关键变数",
            "line_1": "是否会被临时召回",
            "line_2": "等待法官/律师进一步表态",
        }
        if "召回" in t:
            b3["line_1"] = "最后时刻是否被召回"

        blocks = [b1, b2, b3]
        source_trace = [
            {
                "block_index": 1,
                "source_text": t,
                "extracted_lines": [b1.get("label", ""), b1.get("line_1", ""), b1.get("line_2", "")],
                "compression_rule": "i_legal_status_rule",
            },
            {
                "block_index": 2,
                "source_text": t,
                "extracted_lines": [b2.get("label", ""), b2.get("line_1", ""), b2.get("line_2", "")],
                "compression_rule": "i_rumor_itinerary_rule",
            },
            {
                "block_index": 3,
                "source_text": t,
                "extracted_lines": [b3.get("label", ""), b3.get("line_1", ""), b3.get("line_2", "")],
                "compression_rule": "i_key_variables_rule",
            },
        ]
        used = set()
        for b in blocks:
            used.update([b.get("line_1", ""), b.get("line_2", "")])
        for s in facts.get("summary_candidates") or []:
            if s and s not in used:
                discarded.append(s)

        return {
            "route": route,
            "topic": _s(facts.get("topic")) or "热点事件",
            "title": title,
            "subtitle": subtitle,
            "blocks": blocks,
            "footer": footer,
            "source_trace": source_trace,
            "discarded_info": discarded[:12],
        }

    t = text or ""

    def _pick_nums(s: str) -> list[str]:
        out: list[str] = []
        out += re.findall(r"(?<!\d)\d+(?:\.\d+)?\s*(?:万)?美元", s)
        out += re.findall(r"(?<!\d)\d+(?:\.\d+)?\s*(?:ETH|BTC)", s, flags=re.IGNORECASE)
        out += re.findall(r"(?<!\d)\d+(?:\.\d+)?\s*万?美元", s)
        out = [x.replace(" ", "") for x in out]
        return list(dict.fromkeys(out))[:6]

    if route == "D":
        title = "今天巨鲸在干嘛"
        subtitle = "3 个最值得看的链上动作"

        items = re.findall(r"(?:^|\n)\s*\d+\.\s*([^\n]+)", t)
        if not items:
            items = re.findall(r"(?:^|\n)\s*\d+[、．]\s*([^\n]+)", t)

        blocks: list[dict[str, str]] = []
        for idx, it in enumerate(items[:3], start=1):
            s = it.strip().strip("。")
            actor = ""
            m = re.match(r"([A-Za-z0-9_]+)\s+", s)
            if m:
                actor = m.group(1)
            if not actor and "巨鲸地址" in s:
                actor = "巨鲸地址"
            if not actor and "老钱包" in s:
                actor = "老钱包"

            asset = ""
            for a in ["BTC", "ETH", "SOL", "HYPE", "BNB", "ZEC"]:
                if re.search(rf"\b{a}\b", s, flags=re.IGNORECASE):
                    asset = a
                    break

            action = ""
            if "空单" in s:
                action = "空单"
            elif "多单" in s:
                action = "多单"
            elif "苏醒" in s and ("老钱包" in s or "钱包" in s):
                action = "苏醒"
            elif "存入" in s:
                action = "存入"
            elif "持有" in s:
                action = "持有"

            if (asset or "").upper() == "ETH" and "老钱包" in s and "苏醒" in s:
                line_1 = "ETH老钱包苏醒"
            elif (asset or "").upper() == "ETH" and actor == "老钱包" and "苏醒" in s:
                line_1 = "ETH老钱包苏醒"
            elif "老钱包" in s and "苏醒" in s and (asset or "").upper() == "ETH":
                line_1 = "老钱包｜ETH苏醒"
            else:
                line_1 = "｜".join([x for x in [actor or "巨鲸", (asset or "").upper() + (action or "")] if x])
            nums = _pick_nums(s)

            def pick_after_kw(kw: str) -> str:
                m = re.search(
                    rf"{kw}\s*(?:[:：]?\s*)?(?P<mod>约|超过|超|达|高达|已达)?\s*(?P<val>[0-9][0-9,\.]*\s*(?:万)?美元|[0-9][0-9,\.]*\s*(?:ETH|BTC))",
                    s,
                    flags=re.IGNORECASE,
                )
                if m:
                    mod = (m.group("mod") or "").strip()
                    val = (m.group("val") or "").replace(" ", "")
                    val = re.sub(r"(\d)(ETH|BTC)$", r"\1 \2", val, flags=re.IGNORECASE)
                    if mod in {"超过", "超", "达", "高达", "已达"} and kw in {"仓位", "持仓"}:
                        return kw + "超" + val
                    return (kw + val).replace("约", "")
                return ""

            line_2_parts: list[str] = []
            if "持仓" in s:
                x = pick_after_kw("持仓")
                if x:
                    line_2_parts.append(x)
            if "仓位" in s:
                x = pick_after_kw("仓位")
                if x:
                    line_2_parts.append(x)
            if "浮盈" in s:
                x = pick_after_kw("浮盈")
                if x:
                    line_2_parts.append(x.replace("浮盈", "盈利"))
            if "盈利" in s and not any(p.startswith("盈利") for p in line_2_parts):
                x = pick_after_kw("盈利")
                if x:
                    line_2_parts.append(x)
            if "存入" in s and not any(p.startswith("存入") for p in line_2_parts):
                x = pick_after_kw("存入")
                if x:
                    line_2_parts.append(x)
            if not line_2_parts and nums:
                line_2_parts = nums[:2]
            line_2 = "｜".join(line_2_parts[:2])

            line_3 = ""
            if "清算价" in s:
                x = pick_after_kw("清算价")
                if x:
                    line_3 = x
            if not line_3 and "仍持有" in s:
                x = pick_after_kw("仍持有")
                if x:
                    line_3 = x
            if not line_3 and "存入" in s and "仍持有" not in s:
                x = pick_after_kw("存入")
                if x:
                    line_3 = x
            if not line_3 and len(nums) >= 3:
                line_3 = nums[2]

            blocks.append({"line_1": line_1, "line_2": line_2, "line_3": line_3})
            source_trace.append(
                {
                    "block_index": idx,
                    "source_text": s,
                    "extracted_lines": [line_1, line_2, line_3],
                    "compression_rule": "whale_digest_d_three_block_rule",
                }
            )

        while len(blocks) < 3:
            blocks.append({"line_1": f"要点 {len(blocks)+1}", "line_2": "", "line_3": ""})
            source_trace.append(
                {
                    "block_index": len(source_trace) + 1,
                    "source_text": "",
                    "extracted_lines": [blocks[-1]["line_1"], "", ""],
                    "compression_rule": "padding_block",
                }
            )

        return {
            "route": route,
            "topic": _s(facts.get("topic")) or "链上/巨鲸动态",
            "title": title,
            "subtitle": subtitle,
            "blocks": blocks[:3],
            "footer": footer,
            "source_trace": source_trace[:3],
            "discarded_info": discarded[:12],
        }

    title = "一张图看懂关键数据"
    subtitle = "3 个最值得看的要点"
    blocks = []
    nums = facts.get("numbers") if isinstance(facts.get("numbers"), list) else []
    ents = facts.get("entities") if isinstance(facts.get("entities"), list) else []
    ents2 = [e for e in ents if e not in {"CoinMeta", "币界网"}][:3]

    for i in range(3):
        line_1 = ents2[i] if i < len(ents2) else f"要点 {i+1}"
        line_2 = nums[i] if i < len(nums) else ""
        line_3 = nums[i + 3] if (i + 3) < len(nums) else ""
        blocks.append({"line_1": line_1, "line_2": line_2, "line_3": line_3})
    for n in nums[6:]:
        discarded.append(n)

    return {
        "route": route,
        "topic": _s(facts.get("topic")) or "热点事件",
        "title": title,
        "subtitle": subtitle,
        "blocks": blocks,
        "footer": footer,
        "source_trace": source_trace,
        "discarded_info": discarded[:12],
    }


def _load_template(route: str) -> str:
    tdir = ROOT / "templates" / "visual_routes"
    if route == "I":
        path = tdir / "I_concept_cover.md"
    else:
        path = tdir / "D_data_card.md"
    return _read_text(path)


def _render_template(template_text: str, values: dict[str, str]) -> str:
    out = template_text
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def _load_visual_route_registry() -> dict[str, Any]:
    path = ROOT / "configs" / "visual_route_registry.json"
    if not path.exists():
        return {}
    try:
        obj = _read_json(path)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _load_visual_style_profiles() -> dict[str, Any]:
    path = ROOT / "configs" / "visual_style_profiles.json"
    if not path.exists():
        return {}
    try:
        obj = _read_json(path)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _fmt_bullets(lines: list[str]) -> str:
    xs = [str(x).strip() for x in (lines or []) if str(x).strip()]
    return "\n".join([f"- {x}" for x in xs]) if xs else "- (empty)"


def _fmt_knobs(knobs: dict[str, Any]) -> str:
    if not isinstance(knobs, dict) or not knobs:
        return "- (empty)"
    items: list[str] = []
    for k in sorted(knobs.keys()):
        v = knobs.get(k)
        if v is None:
            continue
        items.append(f"{k}: {v}")
    return "\n".join([f"- {x}" for x in items]) if items else "- (empty)"


def _fmt_x_adaptation(xa: dict[str, Any]) -> str:
    if not isinstance(xa, dict) or not xa:
        return "- (empty)"
    keys = ["main_feed", "cover", "safe_fallback"]
    items: list[str] = []
    for k in keys:
        v = xa.get(k)
        if v:
            items.append(f"{k}: {v}")
    for k, v in xa.items():
        if k in keys:
            continue
        if v:
            items.append(f"{k}: {v}")
    return "\n".join([f"- {x}" for x in items]) if items else "- (empty)"


def build_prompt_pack(route: str, image_text_pack: dict[str, Any], risk_pack: dict[str, Any]) -> dict[str, Any]:
    registry = _load_visual_route_registry()
    profiles = _load_visual_style_profiles()

    reg = registry.get(route) if isinstance(registry.get(route), dict) else {}
    style_profile_used = _s(reg.get("style_profile")) or route
    prof = profiles.get(style_profile_used) if isinstance(profiles.get(style_profile_used), dict) else {}

    size = _s(reg.get("default_x_size")) or _s(prof.get("x_default_size")) or "4:5"
    guardrails = risk_pack.get("visual_guardrails") if isinstance(risk_pack.get("visual_guardrails"), list) else []
    guard_text = "\n".join([f"- {x}" for x in guardrails]) if guardrails else "- 不要使用任何 Logo；不要真人肖像；不要误导性场景。"

    topic = _s(image_text_pack.get("topic"))
    title = _s(image_text_pack.get("title"))
    subtitle = _s(image_text_pack.get("subtitle"))
    footer = _s(image_text_pack.get("footer"))
    blocks = image_text_pack.get("blocks") if isinstance(image_text_pack.get("blocks"), list) else []

    visual_methods = prof.get("visual_methods") if isinstance(prof.get("visual_methods"), list) else []
    open_fields = prof.get("open_fields") if isinstance(prof.get("open_fields"), list) else []
    do_not_hardcode = prof.get("do_not_hardcode") if isinstance(prof.get("do_not_hardcode"), list) else []
    style_knobs = prof.get("style_knobs") if isinstance(prof.get("style_knobs"), dict) else {}
    x_adaptation = prof.get("x_adaptation") if isinstance(prof.get("x_adaptation"), dict) else {}
    reference_cases = prof.get("reference_cases") if isinstance(prof.get("reference_cases"), list) else []
    inspiration_atoms = prof.get("inspiration_atoms") if isinstance(prof.get("inspiration_atoms"), list) else []
    variation_space = prof.get("variation_space") if isinstance(prof.get("variation_space"), list) else []
    avoid_overfitting = prof.get("avoid_overfitting") if isinstance(prof.get("avoid_overfitting"), list) else []

    vals: dict[str, str] = {
        "size": size,
        "topic": topic,
        "title": title,
        "subtitle": subtitle,
        "footer": footer,
        "guardrails": guard_text,
        "visual_methods": _fmt_bullets([_s(x) for x in visual_methods]),
        "open_fields": _fmt_bullets([_s(x) for x in open_fields]),
        "do_not_hardcode": _fmt_bullets([_s(x) for x in do_not_hardcode]),
        "style_knobs": _fmt_knobs(style_knobs),
        "x_adaptation": _fmt_x_adaptation(x_adaptation),
    }

    b = blocks + [{}, {}, {}]
    for i in range(3):
        vals[f"block_{i+1}_label"] = _s(b[i].get("label") if isinstance(b[i], dict) else "")
        vals[f"block_{i+1}_line_1"] = _s(b[i].get("line_1") if isinstance(b[i], dict) else "")
        vals[f"block_{i+1}_line_2"] = _s(b[i].get("line_2") if isinstance(b[i], dict) else "")
        vals[f"block_{i+1}_line_3"] = _s(b[i].get("line_3") if isinstance(b[i], dict) else "")

    template_name = _s(reg.get("prompt_template")) or ("I_concept_cover.md" if route == "I" else "D_data_card.md")
    template_text = _read_text(ROOT / "templates" / "visual_routes" / template_name)
    standard_cn = _render_template(template_text, vals).strip()

    if route == "I":
        render_safe = (
            f"生成一张适合发布在 X 的中文新闻洞察封面图，比例 {size}。\n\n"
            "这是一张带完整中文文字的信息卡式封面，不是纯背景图。\n"
            "请保持换行，不要自由改写文字。\n\n"
            f"标题：{title}\n"
            f"副标题：{subtitle}\n\n"
            f"{vals['block_1_label']}\n{vals['block_1_line_1']}\n{vals['block_1_line_2']}\n\n"
            f"{vals['block_2_label']}\n{vals['block_2_line_1']}\n{vals['block_2_line_2']}\n\n"
            f"{vals['block_3_label']}\n{vals['block_3_line_1']}\n{vals['block_3_line_2']}\n\n"
            f"底部署名：{footer}\n\n"
            "视觉方法：\n"
            + vals["visual_methods"]
            + "\n\n不要写死：\n"
            + vals["do_not_hardcode"]
            + "\n\n严格限制：\n"
            + guard_text
            + "\n"
        )
    else:
        render_safe = (
            f"生成一张适合发布在 X 的中文加密市场信息卡，比例 {size}。\n\n"
            "这是一张带完整中文文字的信息卡，不是纯背景图。\n"
            "请严格按 3 个模块排版，每个模块最多 3 行，保持换行，不要自由改写文字。\n\n"
            f"标题：{title}\n"
            f"副标题：{subtitle}\n\n"
            f"内容 1：\n{vals['block_1_line_1']}\n{vals['block_1_line_2']}\n{vals['block_1_line_3']}\n\n"
            f"内容 2：\n{vals['block_2_line_1']}\n{vals['block_2_line_2']}\n{vals['block_2_line_3']}\n\n"
            f"内容 3：\n{vals['block_3_line_1']}\n{vals['block_3_line_2']}\n{vals['block_3_line_3']}\n\n"
            f"底部署名：{footer}\n\n"
            "视觉方法：\n"
            + vals["visual_methods"]
            + "\n\n不要写死：\n"
            + vals["do_not_hardcode"]
            + "\n\n严格限制：\n"
            + guard_text
            + "\n"
        )

    negative_prompt = "不要真实人物肖像；不要任何公司/交易所 Logo；不要黑客盗币画面；不要火箭/金钱雨/赌场感/暴富感；不要投资建议措辞。"

    return {
        "route": route,
        "route_name": ROUTE_NAMES.get(route, ""),
        "size": size,
        "style_profile_used": style_profile_used,
        "reference_cases": [str(x) for x in reference_cases],
        "inspiration_atoms": [str(x) for x in inspiration_atoms],
        "variation_space": [str(x) for x in variation_space],
        "avoid_overfitting": [str(x) for x in avoid_overfitting],
        "visual_methods": [str(x) for x in visual_methods],
        "style_knobs": style_knobs,
        "open_fields": [str(x) for x in open_fields],
        "do_not_hardcode": [str(x) for x in do_not_hardcode],
        "x_adaptation": x_adaptation,
        "prompt_variants": {
            "render_safe_prompt_cn": render_safe.strip(),
            "standard_prompt_cn": standard_cn.strip(),
        },
        "negative_prompt": negative_prompt,
        "guardrails": guardrails,
        "preferred_generation_order": ["render_safe_prompt_cn", "standard_prompt_cn"],
    }


def build_validation_checklist(route: str, image_text_pack: dict[str, Any], risk_pack: dict[str, Any]) -> dict[str, Any]:
    text_check: list[str] = []
    visual_check: list[str] = []
    risk_check: list[str] = []
    title = _s(image_text_pack.get("title"))
    subtitle = _s(image_text_pack.get("subtitle"))
    footer = _s(image_text_pack.get("footer"))

    text_check.append(f"标题是否正确显示“{title}”")
    text_check.append(f"副标题是否正确显示“{subtitle}”")
    text_check.append(f"底部署名是否正确显示“{footer}”")
    text_check.append("是否有 3 个信息模块")
    text_check.append("模块文字是否按行排版（不自由改写）")

    visual_check.append("中文是否清晰可读，是否有乱码/错字/不可读字体")
    visual_check.append("数字是否被拆行/单位是否被拆开（万美元/ETH 等）")
    visual_check.append("画面是否过于拥挤、文字是否过小不可读")

    risk_check.append("是否出现投资建议措辞（买入/卖出/跟单/稳赚/暴富）")

    flags = set(risk_pack.get("risk_flags") or [])
    if "public_figure" in flags:
        risk_check.append("是否避免使用真实公众人物肖像")
    if "logo_risk" in flags:
        risk_check.append("是否避免出现任何公司/交易所 Logo")
    if "legal_case" in flags or route == "I":
        risk_check.append("是否避免把传闻/未确认画成既定事实（避免夸张断言）")

    return {
        "route": route,
        "risk_level": _s(risk_pack.get("risk_level")),
        "risk_flags": list(risk_pack.get("risk_flags") or []),
        "text_check": text_check,
        "visual_check": visual_check,
        "risk_check": risk_check,
    }


def _render_audit_report(
    normalized: dict[str, Any],
    facts: dict[str, Any],
    route_decision: dict[str, Any],
    risk_pack: dict[str, Any],
    image_text_pack: dict[str, Any],
    prompt_pack: dict[str, Any],
) -> str:
    out: list[str] = []
    out.append("# Visual Prompt Pipeline Audit\n\n")
    if isinstance(route_decision, dict) and route_decision.get("override_applied"):
        out.append("## Override\n")
        out.append(f"- override_file: {_s(route_decision.get('override_file'))}\n")
        out.append("\n")
    out.append("## Input Type\n")
    out.append("```json\n")
    out.append(json.dumps(normalized.get("input_type_detection"), ensure_ascii=False, indent=2))
    out.append("\n```\n\n")


    out.append("## Extracted Facts\n")
    out.append("```json\n")
    out.append(json.dumps(facts, ensure_ascii=False, indent=2))
    out.append("\n```\n\n")

    out.append("## Route Decision\n")
    out.append("```json\n")
    out.append(json.dumps(route_decision, ensure_ascii=False, indent=2))
    out.append("\n```\n\n")

    out.append("## Risk Flags\n")
    out.append("```json\n")
    out.append(json.dumps(risk_pack, ensure_ascii=False, indent=2))
    out.append("\n```\n\n")

    out.append("## Image Text Pack\n")
    out.append("```json\n")
    out.append(json.dumps(image_text_pack, ensure_ascii=False, indent=2))
    out.append("\n```\n\n")

    out.append("## Source Trace (Summary)\n")
    st = image_text_pack.get("source_trace") if isinstance(image_text_pack, dict) else None
    if isinstance(st, list) and st:
        for it in st[:6]:
            if not isinstance(it, dict):
                continue
            bi = it.get("block_index")
            rule = it.get("compression_rule")
            lines = it.get("extracted_lines") if isinstance(it.get("extracted_lines"), list) else []
            head = (str(lines[0]) if lines else "").strip()
            out.append(f"- block_{bi} rule={rule}: {head}\n")
    else:
        out.append("- (empty)\n")
    out.append("\n")

    out.append("## Prompt Pack\n")
    out.append("```json\n")
    out.append(json.dumps(prompt_pack, ensure_ascii=False, indent=2))
    out.append("\n```\n\n")

    out.append("## Next Step\n")
    if isinstance(route_decision, dict) and route_decision.get("forced_route"):
        out.append("- 提示：本次 route 为人工强制（--route），非自动打分结果\n")
    out.append("- 当前状态：prompt_ready\n")
    out.append("- 未调用任何外部 API\n")
    out.append("- 未生成图片\n")
    out.append("- 等待人工确认或后续 image2 调用\n")
    return "".join(out)


def _render_ready_prompt(prompt_pack: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# Ready To Generate (Copy/Paste)\n\n")
    pgo = prompt_pack.get("preferred_generation_order") if isinstance(prompt_pack.get("preferred_generation_order"), list) else []
    pv = prompt_pack.get("prompt_variants") if isinstance(prompt_pack.get("prompt_variants"), dict) else {}
    first = pgo[0] if pgo else "render_safe_prompt_cn"
    prompt = _s(pv.get(first) or pv.get("render_safe_prompt_cn") or "")

    out.append("## Selected Prompt Variant\n")
    out.append(f"- {first}\n\n")
    out.append(prompt.strip() + "\n\n")

    out.append("## Negative Prompt\n")
    out.append(_s(prompt_pack.get("negative_prompt")) + "\n\n")

    out.append("## Guardrails\n")
    for g in (prompt_pack.get("guardrails") or [])[:20]:
        out.append(f"- {g}\n")
    return "".join(out)


def _render_operator_review(
    route_decision: dict[str, Any],
    risk_pack: dict[str, Any],
    image_text_pack: dict[str, Any],
    prompt_pack: dict[str, Any],
    ready_prompt_path: str,
) -> str:
    out: list[str] = []
    out.append("# Visual Operator Review\n\n")

    out.append("## 1. Route\n")
    out.append(f"- selected_route: {_s(route_decision.get('selected_route'))}\n")
    out.append(f"- route_name: {_s(route_decision.get('selected_route_name'))}\n")
    out.append(f"- forced_route: {bool(route_decision.get('forced_route'))}\n")
    if route_decision.get("forced_route"):
        out.append(f"- forced_route_value: {_s(route_decision.get('forced_route_value'))}\n")
    out.append(f"- override_applied: {bool(route_decision.get('override_applied'))}\n")
    if route_decision.get("override_applied"):
        out.append(f"- override_file: {_s(route_decision.get('override_file'))}\n")

    out.append("\n## 2. Image Text Pack\n")
    out.append(f"- 标题：{_s(image_text_pack.get('title'))}\n")
    out.append(f"- 副标题：{_s(image_text_pack.get('subtitle'))}\n")
    blocks = image_text_pack.get("blocks") if isinstance(image_text_pack.get("blocks"), list) else []
    for i, b in enumerate(blocks[:3], start=1):
        if not isinstance(b, dict):
            continue
        out.append(f"- 模块 {i}：\n")
        for k in ["line_1", "line_2", "line_3", "label"]:
            v = _s(b.get(k))
            if v:
                out.append(f"  - {v}\n")
    out.append(f"- 底部：{_s(image_text_pack.get('footer'))}\n")

    out.append("\n## 3. Risk Flags\n")
    out.append(f"- risk_level: {_s(risk_pack.get('risk_level'))}\n")
    rf = risk_pack.get("risk_flags") if isinstance(risk_pack.get("risk_flags"), list) else []
    out.append(f"- risk_flags: {', '.join([_s(x) for x in rf if _s(x)])}\n")
    out.append("- guardrails:\n")
    for g in (risk_pack.get("visual_guardrails") or [])[:20]:
        out.append(f"  - {_s(g)}\n")

    out.append("\n## Visual Style Profile\n")
    out.append(f"- style_profile: {_s(prompt_pack.get('style_profile_used'))}\n")
    out.append("- visual_methods:\n")
    for x in (prompt_pack.get("visual_methods") or [])[:12]:
        s = _s(x)
        if s:
            out.append(f"  - {s}\n")
    out.append("- style_knobs:\n")
    sk = prompt_pack.get("style_knobs") if isinstance(prompt_pack.get("style_knobs"), dict) else {}
    if sk:
        for k in sorted(sk.keys()):
            v = sk.get(k)
            if v is None:
                continue
            out.append(f"  - {k}: {v}\n")
    else:
        out.append("  - (empty)\n")
    out.append("- do_not_hardcode:\n")
    for x in (prompt_pack.get("do_not_hardcode") or [])[:12]:
        s = _s(x)
        if s:
            out.append(f"  - {s}\n")
    out.append("- x_adaptation:\n")
    xa = prompt_pack.get("x_adaptation") if isinstance(prompt_pack.get("x_adaptation"), dict) else {}
    if xa:
        for k in ["main_feed", "cover", "safe_fallback"]:
            v = xa.get(k)
            if v:
                out.append(f"  - {k}: {v}\n")
    else:
        out.append("  - (empty)\n")

    out.append("\n## Visual Inspiration\n")
    out.append("- reference_cases:\n")
    for x in (prompt_pack.get("reference_cases") or [])[:12]:
        s = _s(x)
        if s:
            out.append(f"  - {s}\n")
    out.append("- inspiration_atoms:\n")
    for x in (prompt_pack.get("inspiration_atoms") or [])[:20]:
        s = _s(x)
        if s:
            out.append(f"  - {s}\n")
    out.append("- variation_space:\n")
    for x in (prompt_pack.get("variation_space") or [])[:20]:
        s = _s(x)
        if s:
            out.append(f"  - {s}\n")
    out.append("- avoid_overfitting:\n")
    for x in (prompt_pack.get("avoid_overfitting") or [])[:20]:
        s = _s(x)
        if s:
            out.append(f"  - {s}\n")

    out.append("\n## 4. Source Trace\n")
    st = image_text_pack.get("source_trace") if isinstance(image_text_pack.get("source_trace"), list) else []
    if st:
        for it in st[:6]:
            if not isinstance(it, dict):
                continue
            bi = it.get("block_index")
            src = _s(it.get("source_text"))
            lines = it.get("extracted_lines") if isinstance(it.get("extracted_lines"), list) else []
            rule = _s(it.get("compression_rule"))
            out.append(f"- block_{bi} rule={rule}\n")
            if src:
                out.append(f"  - source_text: {src}\n")
            for ln in lines[:3]:
                s = _s(ln)
                if s:
                    out.append(f"  - {s}\n")
    else:
        out.append("- (empty)\n")

    out.append("\n## 5. Ready Prompt\n")
    out.append(f"- 文件路径：{ready_prompt_path}\n")

    out.append("\n## 6. Human Decision\n")
    out.append("- [ ] 可以出图\n")
    out.append("- [ ] 需要改图上文字\n")
    out.append("- [ ] 需要强制换路线\n")
    out.append("- [ ] 不适合做图\n")

    out.append("\n## 7. Next Command\n")
    out.append("如果确认出图，请复制 ready_to_generate_prompt.md 内容到 image2。\n")
    out.append("注意：当前 pipeline 不生成图片。\n")
    out.append("\n---\n")
    out.append(f"generated_at: {_utc_now_iso()}\n")
    return "".join(out)


@dataclass
class PipelineArgs:
    input_file: Path
    input_type: str
    output_dir: Path
    route: str | None
    override_file: str | None
    dry_run: bool


def run_pipeline(args: PipelineArgs) -> dict[str, Any]:
    raw_text = _read_text(args.input_file)
    det = detect_input_type(raw_text)

    input_type = args.input_type
    if input_type == "auto":
        input_type = det["detected_input_type"]

    post = {}
    if input_type in {"post", "mixed"}:
        post = _parse_post_sections(raw_text)

    override_obj = _load_override(Path(args.override_file) if args.override_file else None)
    override_path = str(args.override_file).replace("\\", "/") if args.override_file else ""

    normalized = {
        "input_file": str(args.input_file),
        "input_type_requested": args.input_type,
        "input_type_detection": det,
        "input_type_used": input_type,
        "post": post,
        "override_file": override_path,
    }

    facts_text = post.get("main_post") if isinstance(post, dict) and post.get("main_post") else raw_text
    facts = extract_visual_facts(facts_text)

    route_decision = route_visual_type(facts, facts_text, forced_route=args.route)
    route = _s(route_decision.get("selected_route")) or "I"

    override_applied = False
    override_notes = ""
    if isinstance(override_obj, dict) and override_obj:
        ov_route = _s(override_obj.get("route")).upper()
        if ov_route in ROUTE_NAMES:
            route = ov_route
            override_applied = True
            route_decision["override_applied"] = True
            route_decision["override_file"] = override_path
            route_decision["selected_route"] = ov_route
            route_decision["selected_route_name"] = ROUTE_NAMES.get(ov_route, "")
            rbr = route_decision.get("reason_by_rule") if isinstance(route_decision.get("reason_by_rule"), list) else []
            rbr.append(f"override route={ov_route}")
            route_decision["reason_by_rule"] = rbr

        override_notes = _s(override_obj.get("notes"))
        if any(_s(override_obj.get(k)) for k in ["title", "subtitle", "footer"]) or isinstance(override_obj.get("blocks"), list):
            override_applied = True
            route_decision["override_applied"] = True
            route_decision["override_file"] = override_path

    risk_pack = classify_visual_risk(facts, route=route)
    image_text_pack = build_image_text_pack(facts, route=route, text=facts_text)

    if override_applied and isinstance(override_obj, dict):
        if _s(override_obj.get("title")):
            image_text_pack["title"] = _s(override_obj.get("title"))
        if _s(override_obj.get("subtitle")):
            image_text_pack["subtitle"] = _s(override_obj.get("subtitle"))
        if _s(override_obj.get("footer")):
            image_text_pack["footer"] = _s(override_obj.get("footer"))

        if isinstance(override_obj.get("blocks"), list):
            auto_blocks = image_text_pack.get("blocks") if isinstance(image_text_pack.get("blocks"), list) else []
            ov_blocks = [b for b in override_obj.get("blocks") if isinstance(b, dict)]
            if ov_blocks:
                image_text_pack["blocks"] = _merge_blocks(auto_blocks, ov_blocks)

        image_text_pack["override_applied"] = True
        image_text_pack["override_notes"] = override_notes

    prompt_pack = build_prompt_pack(route, image_text_pack=image_text_pack, risk_pack=risk_pack)
    checklist = build_validation_checklist(route, image_text_pack=image_text_pack, risk_pack=risk_pack)

    run_ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_dir / f"{run_ts}_{_slug(raw_text)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_text(run_dir / "input_raw.txt", raw_text)
    _write_json(run_dir / "input_normalized.json", normalized)
    _write_json(run_dir / "extracted_facts.json", facts)
    _write_json(run_dir / "route_decision.json", route_decision)
    _write_json(run_dir / "image_text_pack.json", image_text_pack)
    _write_json(run_dir / "prompt_pack.json", prompt_pack)
    _write_json(run_dir / "validation_checklist.json", checklist)
    _write_text(run_dir / "audit_report.md", _render_audit_report(normalized, facts, route_decision, risk_pack, image_text_pack, prompt_pack))
    _write_text(run_dir / "ready_to_generate_prompt.md", _render_ready_prompt(prompt_pack))
    _write_text(
        run_dir / "operator_review.md",
        _render_operator_review(
            route_decision=route_decision if isinstance(route_decision, dict) else {},
            risk_pack=risk_pack if isinstance(risk_pack, dict) else {},
            image_text_pack=image_text_pack if isinstance(image_text_pack, dict) else {},
            prompt_pack=prompt_pack if isinstance(prompt_pack, dict) else {},
            ready_prompt_path=str(run_dir / "ready_to_generate_prompt.md"),
        ),
    )

    latest = {
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "input_file": str(args.input_file).replace("\\", "/"),
        "input_type": input_type,
        "selected_route": route,
        "created_at": _utc_now_iso(),
        "operator_review": str((run_dir / "operator_review.md").relative_to(ROOT)).replace("\\", "/"),
        "ready_to_generate_prompt": str((run_dir / "ready_to_generate_prompt.md").relative_to(ROOT)).replace("\\", "/"),
        "audit_report": str((run_dir / "audit_report.md").relative_to(ROOT)).replace("\\", "/"),
        "check_status": "UNKNOWN",
    }
    (args.output_dir / "latest_run.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "run_dir": str(run_dir),
        "selected_route": route,
        "dry_run": args.dry_run,
        "input_type_used": input_type,
    }


def main() -> None:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--input-file", required=True)
    ap.add_argument("--input-type", choices=["post", "raw", "auto"], required=True)
    ap.add_argument("--output-dir", default=str(ROOT / "out" / "visual_pipeline"))
    ap.add_argument("--route", choices=list(ROUTE_NAMES.keys()))
    ap.add_argument("--override-file")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--no-dry-run", action="store_false", dest="dry_run")
    ns = ap.parse_args()

    res = run_pipeline(
        PipelineArgs(
            input_file=Path(ns.input_file),
            input_type=str(ns.input_type),
            output_dir=Path(ns.output_dir),
            route=str(ns.route) if ns.route else None,
            override_file=str(ns.override_file) if ns.override_file else None,
            dry_run=bool(ns.dry_run),
        )
    )
    print("[visual_prompt_pipeline] ok")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

