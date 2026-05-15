from __future__ import annotations

from typing import Any

from visual_risk_checker import evaluate_visual_usage_risk


def _norm_text(*parts: Any) -> str:
    segs: list[str] = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, str):
            s = p.strip()
            if s:
                segs.append(s)
        else:
            s = str(p).strip()
            if s and s != "None":
                segs.append(s)
    return "\n".join(segs)


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords if k)


def _as_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return int(x)
        return int(x)
    except (TypeError, ValueError):
        return default


def _pick_bullets(event: dict[str, Any], fact_pack: dict[str, Any], limit: int = 4) -> list[str]:
    bullets: list[str] = []
    if isinstance(fact_pack.get("confirmed_facts"), list):
        for x in fact_pack.get("confirmed_facts")[:6]:
            s = str(x).strip()
            if s and s not in bullets:
                bullets.append(s)
            if len(bullets) >= limit:
                return bullets

    raw = str(event.get("raw_summary") or "").strip()
    if raw:
        for seg in raw.replace("；", "。").replace(";", "。").split("。"):
            s = seg.strip()
            if len(s) >= 8 and s not in bullets:
                bullets.append(s)
            if len(bullets) >= limit:
                return bullets

    if isinstance(fact_pack.get("angle_candidates"), list):
        for x in fact_pack.get("angle_candidates")[:6]:
            s = str(x).strip()
            if s and s not in bullets:
                bullets.append(s)
            if len(bullets) >= limit:
                return bullets

    return bullets[:limit]


def _image_candidates(event: dict[str, Any], fact_pack: dict[str, Any]) -> list[dict[str, Any]]:
    cands: list[dict[str, Any]] = []

    if isinstance(event.get("source_urls"), list):
        for url in event.get("source_urls")[:5]:
            u = str(url).strip()
            if not u:
                continue
            cands.append({"type": "source_url", "url": u, "notes": "仅作来源锚点参考，不下载不复用。"})

    if isinstance(fact_pack.get("best_sources"), list):
        for s in fact_pack.get("best_sources")[:5]:
            if not isinstance(s, dict):
                continue
            url = str(s.get("url") or "").strip()
            if not url:
                continue
            cands.append(
                {
                    "type": "best_source",
                    "url": url,
                    "domain": str(s.get("domain") or "").strip(),
                    "source_name": str(s.get("source_name") or "").strip(),
                    "tier": str(s.get("tier") or "").strip(),
                    "notes": "仅作截图/引用锚点候选，不下载不复用。",
                }
            )

    dash = str(event.get("dashboard_url") or "").strip()
    if dash:
        cands.append({"type": "dashboard_url", "url": dash, "notes": "链上看板链接，仅作参考。"})

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in cands:
        u = str(c.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(c)
    return out


def _is_routine_market_flow(text: str) -> bool:
    flow_markers = ["etf", "现货 etf", "现货etf", "净流入", "净流出", "资金流", "flow", "inflow", "outflow"]
    if not _contains_any(text, flow_markers):
        return False
    strong_hooks = [
        "创纪录",
        "历史最大",
        "历史新高",
        "连续",
        "异常",
        "背离",
        "价格大跌",
        "价格大涨",
        "暴跌",
        "暴涨",
        "流动性冲击",
        "机构赎回",
        "贝莱德",
        "ibit",
        "富达",
        "fbtc",
    ]
    for kw in strong_hooks:
        if kw in {"ibit", "fbtc"}:
            if kw in text.lower():
                return False
            continue
        if kw == "背离":
            if "背离" in text and not _contains_any(text, ["无背离", "不背离", "未背离", "没有背离", "无明显背离"]):
                return False
            continue
        if kw in text:
            if not _contains_any(text, ["无" + kw, "不" + kw, "未" + kw, "没有" + kw]):
                return False
    return True


def _build_image_search_queries(event: dict[str, Any], event_type: str, fact_pack: dict[str, Any]) -> list[str]:
    title = str(event.get("cluster_title") or "").strip()
    raw = str(event.get("raw_summary") or "").strip()
    sources = " ".join([str(x) for x in (event.get("source_names") or [])]) if isinstance(event.get("source_names"), list) else ""

    base = title or raw
    queries: list[str] = []

    def add(q: str) -> None:
        s = (q or "").strip()
        if not s:
            return
        if s not in queries:
            queries.append(s)

    if event_type == "ai_crypto_story":
        add("Claude Bitcoin wallet recovery")
        add("AI helps recover lost Bitcoin wallet")
        add("old Mac hard drive Bitcoin wallet backup")
        if base:
            add(base + " AI 找回 钱包 备份")
    elif event_type in {"security_incident", "exchange_risk"}:
        if base:
            add(base + " official statement")
            add(base + " withdrawal suspended")
        add("exchange withdrawal suspended official announcement")
        add("exchange security incident update")
    elif event_type in {"macro_market"}:
        if base:
            add(base + " chart")
        add("BTC spot ETF inflow outflow chart")
        add("ETF flow chart record inflow outflow")
    elif event_type in {"stablecoin_policy", "crypto_regulation"}:
        if base:
            add(base + " key points")
        add("regulatory update key points infographic")
    else:
        if base:
            add(base + " image")
        if sources and base:
            add(base + " " + sources)

    best_sources = fact_pack.get("best_sources") if isinstance(fact_pack.get("best_sources"), list) else []
    domains = []
    for s in best_sources:
        if not isinstance(s, dict):
            continue
        d = str(s.get("domain") or "").strip()
        if d and d not in domains:
            domains.append(d)
    if domains and base:
        add(base + " site:" + domains[0])

    return queries[:5]


def build_visual_brief(
    *,
    event: dict[str, Any],
    queue: str,
    fact_pack: dict[str, Any] | None,
) -> dict[str, Any]:
    eid = str(event.get("event_cluster_id") or "").strip()
    title = str(event.get("cluster_title") or "").strip()
    raw_summary = str(event.get("raw_summary") or "").strip()

    fp = fact_pack if isinstance(fact_pack, dict) else {}
    event_type = str(fp.get("event_type") or event.get("event_type") or "").strip()
    if not event_type:
        try:
            from enrichment.event_type_classifier import classify_event_type

            guessed = classify_event_type(event)
            if isinstance(guessed, dict):
                event_type = str(guessed.get("event_type") or "").strip() or event_type
        except Exception:
            event_type = event_type

    all_text = _norm_text(
        title,
        raw_summary,
        " ".join([str(x) for x in (fp.get("angle_candidates") or [])]) if isinstance(fp.get("angle_candidates"), list) else "",
    )

    visual_mode = "no_image"
    recommended_visual = "不配图。"
    visual_prompt = ""
    image2_prompt = ""
    card_title = ""
    card_subtitle = ""
    card_bullets: list[str] = []
    reason = ""

    visual_strategy = "no_visual"
    auto_generate_allowed = False
    auto_publish_allowed = False
    image_search_queries: list[str] = []
    meme_angle = ""
    template_name = ""
    asset_usage_note = "不下载版权图；不自动发布图片；固定栏目可生成本地模板卡。"
    generated_card_path = ""

    fixed_title = title

    if str(queue or "").strip() == "whale_digest" or ("今天巨鲸在干嘛" in fixed_title) or (event_type in {"whale_onchain"}):
        visual_strategy = "auto_template"
        auto_generate_allowed = True
        visual_mode = "template_card"
        template_name = "whale_digest_card"
        recommended_visual = "固定栏目：自动生成本地模板卡（不使用外部新闻图）。"
        card_title = "今天巨鲸在干嘛"
        card_subtitle = "3 个最值得看的链上动作"
        bullets: list[str] = []
        actor = str(event.get("actor_label") or "").strip()
        asset = str(event.get("asset") or "").strip()
        action = str(event.get("action") or "").strip()
        amt = str(event.get("amount_usd") or "").strip()
        pnl = str(event.get("pnl_usd") or "").strip()
        liq = str(event.get("liquidation_price") or "").strip()
        if actor or asset or action:
            bullets.append(f"{actor}｜{asset}｜{action}".strip("｜"))
        if amt:
            bullets.append(f"金额：{amt}")
        if pnl:
            bullets.append(f"盈亏：{pnl}")
        if liq:
            bullets.append(f"清算价：{liq}")
        if not bullets:
            bullets = _pick_bullets(event, fp, limit=4)
        card_bullets = bullets[:4]
        reason = "固定栏目自动生成模板卡；不依赖外部图片；更适合结构化呈现。"
    elif "一张图看懂市场异动" in fixed_title:
        visual_strategy = "auto_template"
        auto_generate_allowed = True
        visual_mode = "data_card"
        template_name = "market_move_card"
        recommended_visual = "固定栏目：自动生成本地市场异动卡（不使用外部新闻图）。"
        card_title = "一张图看懂市场异动"
        card_subtitle = "关键数字 + 影响解读 + 后续观察"
        card_bullets = _pick_bullets(event, fp, limit=4)
        reason = "固定栏目自动生成数据卡，减少版权与误导风险。"
    elif event_type == "ai_crypto_story":
        visual_strategy = "ai_generated_candidate"
        visual_mode = "generated_image"
        recommended_visual = "普通热点：给出找图候选 + 梗图/image2 方向（不自动生图、不自动发布）。"
        image_search_queries = _build_image_search_queries(event, event_type, fp)
        meme_angle = "AI 不是黑客：它更像不嫌烦的数字侦探，把旧设备里的线索一条条翻出来。"
        visual_prompt = (
            "概念图候选：旧电脑、旧硬盘、备份文件夹、邮件列表与便签线索被逐条串联，"
            "一个“数字侦探”式的 AI 助手在整理线索（不出现真实人物肖像，不出现任何交易所/品牌 Logo）。"
        )
        image2_prompt = (
            "一个 AI 数字侦探在旧电脑、旧硬盘和云端邮件中寻找十年前的钱包备份线索，画面轻松、有科技感，"
            "不出现黑客攻击、不出现破解私钥、不暗示盗币；不出现真实人物肖像；不生成假新闻现场。"
        )
        reason = "AI × Crypto 奇闻更适合“概念图/梗图方向”，但必须明确避免黑客/破解叙事。"
    elif event_type in {"stablecoin_policy", "crypto_regulation"}:
        visual_strategy = "no_visual"
        visual_mode = "no_image"
        recommended_visual = "政策/监管类默认不配图；如需可用数据卡做要点图解（不做人物/建筑渲染）。"
        card_bullets = _pick_bullets(event, fp, limit=3)
        if card_bullets:
            visual_mode = "data_card"
            card_title = "政策变化要点"
            card_subtitle = "只做条款/影响对象图解，不做人物/建筑渲染"
        reason = "政策/监管类容易误导与版权风险高，优先 no_visual 或自制数据卡。"
    elif event_type == "macro_market":
        if _is_routine_market_flow(all_text):
            visual_strategy = "no_visual"
            visual_mode = "no_image"
            recommended_visual = "常规市场流不做强视觉，避免把常规数据渲染成强热点。"
            reason = "常规市场流数据传播价值有限，避免强视觉放大。"
        else:
            visual_strategy = "image_search_candidates"
            visual_mode = "data_card"
            recommended_visual = "普通热点：输出找图方向与数据卡文案（不自动生成、不自动发布）。"
            card_title = "市场数据卡"
            card_subtitle = "关键数字 + 影响解读 + 后续观察"
            card_bullets = _pick_bullets(event, fp, limit=4)
            image_search_queries = _build_image_search_queries(event, event_type, fp)
            image2_prompt = "数据卡/信息卡风格：清晰的关键数字、时间范围、来源锚点与影响解读，不做价格预测。"
            reason = "宏观/市场类更适合数据卡，强调来源与时间范围，避免夸张场景。"
    elif event_type in {"exchange_risk", "security_incident"}:
        visual_strategy = "image_search_candidates"
        visual_mode = "data_card"
        recommended_visual = "普通热点：输出找图方向（优先截图/信息卡），不做夸张黑客图。"
        card_title = "风险信息卡"
        card_subtitle = "中性、克制，不制造恐慌"
        card_bullets = _pick_bullets(event, fp, limit=4)
        image_search_queries = _build_image_search_queries(event, event_type, fp)
        image2_prompt = "信息卡风格：中性、克制。不要画黑客骷髅/盗币/入侵界面；不要让用户误以为是真实现场图或官方截图。"
        reason = "交易所风险/安全事故不适合夸张黑客图，优先信息卡或不配图。"
        if not card_bullets:
            visual_strategy = "no_visual"
            visual_mode = "no_image"
            recommended_visual = "默认不配图，等待更多事实锚点后再做信息卡。"
    else:
        if str(queue or "").strip() in {"queue_review", "enriched_queue_review", "source_research"}:
            visual_strategy = "image_search_candidates"
            visual_mode = "no_image"
            recommended_visual = "普通热点：给出找图候选与视觉建议（不自动配图发布）。"
            image_search_queries = _build_image_search_queries(event, event_type, fp)
            image2_prompt = "抽象概念图/信息卡方向：不含真实人物肖像，不暗示假现场，不使用版权新闻图。"
            reason = "普通热点默认只给找图候选 + 视觉方向，不生成不发布。"
        else:
            visual_strategy = "no_visual"
            visual_mode = "no_image"
            recommended_visual = "不配图。"
            reason = "未匹配到适合的视觉策略，默认 no_visual。"

    out: dict[str, Any] = {
        "event_cluster_id": eid,
        "cluster_title": title,
        "queue": str(queue or "").strip(),
        "event_type": event_type,
        "visual_mode": visual_mode,
        "recommended_visual": recommended_visual,
        "visual_prompt": visual_prompt,
        "visual_strategy": visual_strategy,
        "auto_generate_allowed": bool(auto_generate_allowed),
        "auto_publish_allowed": bool(auto_publish_allowed),
        "image_search_queries": image_search_queries,
        "meme_angle": meme_angle,
        "image2_prompt": image2_prompt,
        "template_name": template_name,
        "generated_card_path": generated_card_path,
        "asset_usage_note": asset_usage_note,
        "card_title": card_title,
        "card_subtitle": card_subtitle,
        "card_bullets": card_bullets,
        "image_candidates": _image_candidates(event, fp),
        "usage_risk": "low",
        "risk_reasons": [],
        "reason": reason,
    }

    risk, reasons = evaluate_visual_usage_risk(out)
    out["usage_risk"] = risk
    out["risk_reasons"] = reasons
    return out

