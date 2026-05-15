from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "out" / "image2_prompts"
COL_DIR = ROOT / "out" / "columns"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _s(x: Any) -> str:
    return str(x or "").strip()


def _num_str(x: Any) -> str:
    s = _s(x)
    return re.sub(r"[^\d\.,]", "", s)


def _short_addr(addr: str) -> str:
    a = _s(addr)
    if a.startswith("0x") and len(a) > 12:
        return a[:6] + "…" + a[-4:]
    return a


def _extract_addr(text: str) -> str:
    m = re.search(r"\b0x[a-fA-F0-9]{10,}\b", text or "")
    return m.group(0) if m else ""


def _extract_trader_name(text: str) -> str:
    t = text or ""
    m = re.search(r"交易员([A-Za-z0-9_\- ]{2,24})", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(James Wynn)\b", t, flags=re.IGNORECASE)
    if m:
        return "James Wynn"
    m = re.search(r"\b(Machi)\b", t, flags=re.IGNORECASE)
    if m:
        return "Machi"
    return ""


def _extract_liq_price(text: str) -> str:
    t = text or ""
    m = re.search(r"清算价(?:为|：)?\s*([\d,\.]+)", t)
    if m:
        return m.group(1)
    m = re.search(r"liq(?:uidation)?\s*[:=]?\s*([\d,\.]+)", t, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def _extract_eth_counts(text: str) -> tuple[str, str]:
    t = text or ""
    dep = ""
    hold = ""
    m = re.search(r"存入了?\s*([\d,\.]+)\s*枚?ETH", t, flags=re.IGNORECASE)
    if m:
        dep = m.group(1)
    m = re.search(r"仍持有\s*([\d,\.]+)\s*枚?ETH", t, flags=re.IGNORECASE)
    if m:
        hold = m.group(1)
    return dep, hold


def _extract_usd_wan(text: str) -> tuple[str, str, str]:
    t = text or ""
    pos = ""
    pnl = ""
    cross = ""
    m = re.search(r"持仓规模约\s*([\d\.]+)\s*万?美元", t)
    if m:
        pos = m.group(1)
    m = re.search(r"(?:累计盈利约|全周期盈利约|盈利约)\s*([\d\.]+)\s*万?美元", t)
    if m:
        pnl = m.group(1)
    m = re.search(r"超过\s*([\d\.]+)\s*万?美元", t)
    if m:
        cross = m.group(1)
    return pos, pnl, cross


def _to_wan_from_amount(amount_usd: str) -> str:
    s = _num_str(amount_usd)
    if not s:
        return ""
    try:
        n = float(s.replace(",", ""))
    except ValueError:
        return ""
    wan = n / 10000.0
    if wan >= 1000:
        return f"{wan:.0f} 万美元"
    if wan >= 100:
        return f"{wan:.0f} 万美元"
    return f"{wan:.1f} 万美元"


def _to_wan_usd_compact(amount_usd: str) -> str:
    s = _num_str(amount_usd)
    if not s:
        return ""
    try:
        n = float(s.replace(",", ""))
    except ValueError:
        return ""
    wan = n / 10000.0
    if abs(wan - round(wan)) < 1e-9:
        return f"{int(round(wan))}万美元"
    return f"{wan:.2f}万美元"


def _to_wan_usd_from_price(price_usd: str) -> str:
    s = _num_str(price_usd)
    if not s:
        return ""
    try:
        n = float(s.replace(",", ""))
    except ValueError:
        return ""
    wan = n / 10000.0
    return f"{wan:.2f}万美元"


def _estimate_fullwidth_chars(text: str) -> int:
    t = text or ""
    score = 0.0
    for ch in t:
        o = ord(ch)
        if ch in {" ", "\t", "\n", "\r"}:
            score += 0.3
        elif 0x4E00 <= o <= 0x9FFF:
            score += 1.0
        elif ch in {"，", "。", "：", "；", "！", "？", "（", "）", "《", "》", "、", "—", "…", "｜"}:
            score += 1.0
        elif "0" <= ch <= "9":
            score += 0.6
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            score += 0.6
        else:
            score += 0.8
    return int(round(score))


def _suggest_shorten_line(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    s = s.replace(",", "")
    s = s.replace("累计", "").replace("约", "")
    s = s.replace("P/L", "盈利").replace("p/l", "盈利")
    s = re.sub(r"\bliq\b", "清算价", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdeposit\b", "存入", s, flags=re.IGNORECASE)

    def _shrink_wan_usd(m: re.Match[str]) -> str:
        num = m.group(1)
        if "." in num:
            num = num.split(".", 1)[0]
        return num + "万美元"

    s2 = re.sub(r"(\d+(?:\.\d+)?)万美元", _shrink_wan_usd, s)
    if s2 != s:
        s = s2

    s = s.replace("老钱包苏醒", "老钱包")
    s = s.replace("跨市场仓位", "仓位")
    s = s.replace("持仓规模", "持仓")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _visual_text_block(must_text: dict[str, Any]) -> str:
    title = _s(must_text.get("title"))
    subtitle = _s(must_text.get("subtitle"))
    footer = _s(must_text.get("footer"))
    bullets = must_text.get("bullets") if isinstance(must_text.get("bullets"), list) else []
    lines: list[str] = []
    lines.append(f"标题：{title}")
    lines.append(f"副标题：{subtitle}")
    lines.append("")
    for i, b in enumerate(bullets[:3], start=1):
        segs = [x.strip() for x in str(b or "").splitlines() if x.strip()]
        lines.append(f"内容{i}：")
        if segs:
            lines.extend(segs[:2])
        else:
            lines.append("(empty)")
        lines.append("")
    lines.append(f"底部署名：{footer}")
    return "\n".join(lines).strip()


def _render_safe_blocks_from_bullets(bullets: list[str]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for i, b in enumerate(bullets[:3], start=1):
        segs = [x.strip() for x in str(b or "").splitlines() if x.strip()]
        line_1 = segs[0] if len(segs) >= 1 else ""
        line_2_raw = segs[1] if len(segs) >= 2 else ""

        line_2 = ""
        line_3 = ""
        if line_2_raw:
            parts = [p.strip() for p in line_2_raw.split("｜") if p.strip()]
            if len(parts) >= 3:
                line_2 = parts[0] + "｜" + parts[1]
                line_3 = parts[2]
            elif len(parts) == 2:
                line_2 = parts[0]
                line_3 = parts[1]
            else:
                line_2 = parts[0] if parts else line_2_raw

        def clean(x: str) -> str:
            s = (x or "").strip()
            s = s.replace("P/L", "盈利").replace("p/l", "盈利")
            s = re.sub(r"\bliq\b", "清算价", s, flags=re.IGNORECASE)
            s = re.sub(r"\bdeposit\b", "存入", s, flags=re.IGNORECASE)
            s = s.replace(",", "")
            s = re.sub(r"\s+", " ", s).strip()
            return s

        blocks.append(
            {
                "label": f"内容 {i}",
                "line_1": clean(line_1),
                "line_2": clean(line_2),
                "line_3": clean(line_3),
            }
        )
    return blocks


def _audit_and_compact_blocks(
    blocks: list[dict[str, str]],
    max_fullwidth_chars_per_line: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    audit_items: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    compact: list[dict[str, str]] = []

    for bi, b in enumerate(blocks):
        nb = dict(b)
        for lk in ["line_1", "line_2", "line_3"]:
            txt = str(b.get(lk) or "").strip()
            if not txt:
                continue
            est = _estimate_fullwidth_chars(txt)
            audit_items.append(
                {
                    "field": f"render_safe_blocks[{bi}].{lk}",
                    "text": txt,
                    "estimated_fullwidth_chars": est,
                }
            )
            if est > max_fullwidth_chars_per_line:
                sug = _suggest_shorten_line(txt)
                warnings.append(
                    {
                        "field": f"render_safe_blocks[{bi}].{lk}",
                        "text": txt,
                        "estimated_fullwidth_chars": est,
                        "suggestion": sug,
                    }
                )
                nb[lk] = sug
        compact.append(nb)

    audit = {
        "max_fullwidth_chars_per_line": max_fullwidth_chars_per_line,
        "items": audit_items,
    }
    return audit, warnings, compact


def _compress_whale_bullets(column: dict[str, Any]) -> list[str]:
    items = column.get("selected_items")
    if not isinstance(items, list):
        items = []

    out: list[str] = []
    for it in items[:3]:
        if not isinstance(it, dict):
            continue
        actor_label = _s(it.get("actor_label"))
        asset = _s(it.get("asset")).upper()
        latest = _s(it.get("latest_status"))
        action0 = ""
        acts = it.get("actions")
        if isinstance(acts, list) and acts:
            action0 = _s(acts[0])

        liq = _extract_liq_price(latest) or _extract_liq_price(action0)
        addr = _extract_addr(latest) or _extract_addr(actor_label) or _extract_addr(action0)
        trader = _extract_trader_name(latest)
        pos_wan, pnl_wan, cross_wan = _extract_usd_wan(latest)

        actor = trader or _s(actor_label) or _short_addr(addr) or "巨鲸地址"
        if addr and (actor_label.startswith("地址") or actor_label.startswith("0x") or actor_label.startswith("巨鲸地址")):
            actor = _short_addr(addr)
        if actor_label.startswith("地址") and "…" in actor_label:
            actor = actor_label.replace("地址", "").strip()
        if "麻吉" in actor_label or "machi" in actor_label.lower():
            actor = "麻吉/Machi"

        long_short = ""
        if "空" in latest and "单" in latest:
            long_short = "空单"
        elif "多" in latest and "单" in latest:
            long_short = "多单"
        elif "存入" in latest or "deposit" in latest.lower():
            long_short = "老钱包苏醒"
        elif "平仓" in latest:
            long_short = "多单已平"

        if long_short:
            line1 = f"{actor}｜{asset}{long_short}".strip("｜")
        else:
            line1 = f"{actor}｜{asset}".strip("｜")

        parts2: list[str] = []
        pnl_wan2_compact = _to_wan_usd_compact(_s(it.get("pnl_usd")))

        if cross_wan and ("跨" in latest or "涉足" in latest):
            parts2.append(f"仓位超{cross_wan}万美元")
        elif pos_wan:
            parts2.append(f"持仓{pos_wan}万美元")
        else:
            amt_wan = _to_wan_usd_compact(_s(it.get("amount_usd")))
            if amt_wan:
                parts2.append(f"持仓{amt_wan}")

        if pnl_wan:
            parts2.append(f"盈利{pnl_wan}万美元")
        elif pnl_wan2_compact:
            parts2.append(f"盈利{pnl_wan2_compact}")

        if liq:
            liq_wan = _to_wan_usd_from_price(liq)
            parts2.append(f"清算价{liq_wan}" if liq_wan else f"清算价{liq}")

        dep_eth, hold_eth = _extract_eth_counts(latest)
        if dep_eth:
            parts2 = [f"存入{dep_eth} ETH"]
            if hold_eth:
                parts2.append(f"仍持有{hold_eth} ETH")

        line2 = "｜".join(parts2) if parts2 else "重点：是否连续调仓/是否逼近清算价"
        out.append(line1 + "\n" + line2)

    return out


def _build_prompt_pack_daily_whale_digest(column: dict[str, Any]) -> dict[str, Any]:
    title = _s(column.get("card_title")) or "今天巨鲸在干嘛"
    subtitle = _s(column.get("card_subtitle")) or "3 个最值得看的链上动作"
    footer = "CoinMeta / 币界网"
    bullets = _compress_whale_bullets(column)

    layout = [
        "画面比例：适合 X 信息流（建议 4:5 或 1:1，优先 4:5）。",
        "顶部：大标题（粗体）+ 副标题（次级文字）。",
        "中部：3 条 bullet，每条最多两行，行距清晰，左右对齐。",
        "底部：小字 footer（CoinMeta / 币界网），不抢主视觉。",
        "留白充足，避免信息拥挤；数字对齐，避免乱码。",
    ]
    style = [
        "深色金融终端风格：深蓝/黑底，微弱网格与数据纹理。",
        "机构情报卡片感：干净、克制、现代排版。",
        "抽象巨鲸剪影 + 链上资金流/交易终端网格（仅作为背景装饰）。",
        "中文字体清晰现代：标题粗体，正文中等粗细，避免花体。",
        "不出现任何交易所 Logo、币种 Logo、真实人物肖像。",
    ]
    negative = (
        "不要火箭、金钱雨、赌场感、暴富感、夸张币价K线；不要黑客盗币画面；"
        "不要真实人物肖像；不要交易所Logo；不要把文字写成投资建议（买入/卖出/跟单/稳赚/暴富）。"
    )

    must_text = {
        "title": title,
        "subtitle": subtitle,
        "bullets": bullets,
        "footer": footer,
    }
    render_safe_blocks = _render_safe_blocks_from_bullets(bullets)
    must_text["render_safe_blocks"] = render_safe_blocks

    max_fullwidth = 22
    line_width_audit, overflow_warnings, render_safe_blocks_compact = _audit_and_compact_blocks(
        render_safe_blocks,
        max_fullwidth_chars_per_line=max_fullwidth,
    )

    bullets_block = "\n".join([f"- {b}" for b in bullets]) if bullets else "- (no_candidate)"
    text_block = _visual_text_block(must_text)

    standard_prompt_cn = (
        "生成一张适合 X 信息流发布的中文加密市场栏目图（带中文文字排版，不是无文字背景）。\n"
        "请把文字当作信息卡正文来排版，所有文字必须清晰可读、不要透视倾斜、不要艺术字、不要发光描边。\n"
        "请在图中尽量逐字准确显示以下中文文字（不要翻译、不要替换符号、不要改数字格式）：\n\n"
        f"标题：{title}\n"
        f"副标题：{subtitle}\n"
        "三条 bullet（每条最多两行，保持换行）：\n"
        f"{bullets_block}\n"
        f"底部署名：{footer}\n\n"
        "为了减少中文乱码与错字：请严格按下面的文本块逐行排版（保持换行与符号不变）：\n"
        "```text\n"
        f"{text_block}\n"
        "```\n\n"
        "风格与布局要求：\n"
        + "\n".join([f"- {x}" for x in layout + style])
        + "\n\n"
        "风险与禁忌：\n"
        f"- {negative}\n"
        "- 不要出现任何投资建议语气。\n"
        "- 不要把数字拆行，不要把“万美元/ETH”拆开。\n"
    )

    prompt_en_short = (
        f'Title: "{title}"\n'
        f'Subtitle: "{subtitle}"\n'
        + "\n".join([f"- {b.replace(chr(10), ' / ')}" for b in bullets])
        + "\n"
        f'Footer: "{footer}"\n'
        "Dark financial terminal style. No logos, no portraits, no hacker scenes, no investment advice words.\n"
    )

    def _content_block(i: int, b: str) -> str:
        lines = [x.strip() for x in (b or "").splitlines() if x.strip()]
        if not lines:
            return f"内容 {i}：\n（empty）"
        if len(lines) == 1:
            return f"内容 {i}：\n{lines[0]}"
        return f"内容 {i}：\n{lines[0]}\n{lines[1]}"

    ultra_safe_prompt_cn = (
        "生成一张适合发布在 X 的中文加密市场栏目图，比例优先 4:5。\n\n"
        "这是一张“带完整中文文字排版”的信息卡，不是纯背景图。\n"
        "请用清晰、现代、易读的中文排版，准确呈现以下内容：\n\n"
        f"标题：{title}\n"
        f"副标题：{subtitle}\n\n"
        + "\n\n".join([_content_block(i + 1, b) for i, b in enumerate(bullets[:3])])
        + "\n\n"
        f"底部署名：{footer}\n\n"
        "文字排版硬要求（为了避免乱码/错行）：\n"
        "- 所有文字必须横向排版、清晰可读，禁止透视、倾斜、扭曲、霓虹发光效果。\n"
        "- 数字使用等宽风格/表格数字（tabular figures）或视觉上对齐的数字字体。\n"
        "- 每个“内容1/2/3”是一个独立信息模块：上行是名称与资产，下行是数字要点。\n"
        "- 不要自动换行拆分数字，不要把“万美元/ETH”拆开。\n\n"
        "视觉要求：\n"
        "- 深色金融终端风格，深蓝黑背景\n"
        "- 整体像机构情报信息卡，干净、克制、现代\n"
        "- 可加入轻微网格、数据流、链上资金流动感\n"
        "- 可加入抽象鲸鱼轮廓作为弱背景元素，但不要抢文字\n"
        "- 标题加粗醒目，副标题较小\n"
        "- 中间分成 3 个清晰信息模块\n"
        "- 留白充足，数字清楚，文字不要拥挤\n"
        "- 所有文字必须清晰可读，避免乱码和错字\n\n"
        "严格限制：\n"
        "- 不要真实人物肖像\n"
        "- 不要交易所 Logo\n"
        "- 不要币种 Logo\n"
        "- 不要黑客盗币画面\n"
        "- 不要火箭、金钱雨、赌场感、暴富感\n"
        "- 不要夸张 K 线\n"
        "- 不要出现投资建议语气\n"
        "- 不要出现“买入、卖出、跟单、稳赚、暴富”等措辞\n"
    )

    checklist = [
        f'标题是否正确显示“{title}”',
        f'副标题是否正确显示“{subtitle}”',
        "是否有 3 条 bullet（每条最多两行）",
        "每条 bullet 的人物/地址/资产/金额是否与 expected_text 一致",
        "是否出现中文乱码/错别字/不可读字体",
        "是否出现错误数字（特别是金额与清算价）",
        "是否出现投资建议语气（买入/卖出/跟单/稳赚/暴富）",
        "是否出现真实人物肖像、交易所 Logo、黑客盗币画面",
        "整体是否适合 CoinMeta 官号 X 发布（克制、信息卡风格）",
    ]

    regen_template_ultra_safe = (
        "你需要在保持相同整体风格与栏目结构的前提下，重新生成这张图片。\n\n"
        "只修正错误文字、错误数字、排版问题和风险问题。\n"
        "不要增加新信息，不要改栏目主题，不要加入投资建议，不要改变整体视觉方向。\n\n"
        "必须准确显示以下文字：\n\n"
        f"标题：{title}\n"
        f"副标题：{subtitle}\n\n"
        + "\n\n".join([_content_block(i + 1, b) for i, b in enumerate(bullets[:3])])
        + "\n\n"
        f"底部署名：{footer}\n\n"
        "视觉风格保持：\n"
        "- 深色金融终端风格\n"
        "- 机构信息卡风格\n"
        "- 干净、克制、现代\n"
        "- 背景可有轻微网格、数据流、抽象鲸鱼元素\n"
        "- 文字必须清晰可读、排版整齐、留白充足\n\n"
        "严格不要出现：\n"
        "- 真实人物肖像\n"
        "- 交易所 Logo\n"
        "- 币种 Logo\n"
        "- 黑客盗币画面\n"
        "- 火箭、金钱雨、赌场感、暴富感\n"
        "- 投资建议措辞\n\n"
        "这次需要重点修正的问题：\n"
        "文字错误：{text_errors}\n"
        "数字错误：{number_errors}\n"
        "布局错误：{layout_errors}\n"
        "风险问题：{risk_errors}\n"
        "风格问题：{style_errors}\n\n"
        "如果有乱码，请重新做中文排版，确保所有中文清晰、可读、无乱码。\n"
    )

    claude_validation_prompt = (
        "你现在充当 CoinMeta 官号图片质检编辑。\n\n"
        "请检查我提供的这张栏目图，判断它是否符合预期，并严格按 JSON 输出结果，不要输出多余解释。\n\n"
        "【预期图片定位】\n"
        "- 用于 X 发布的中文加密市场栏目图\n"
        "- 风格应为：深色金融终端 / 机构信息卡 / 克制现代 / 非土味海报\n"
        "- 必须是完整中文信息卡，而不是纯背景图\n\n"
        "【预期文字】\n"
        f"标题：{title}\n"
        f"副标题：{subtitle}\n\n"
        + "\n\n".join([_content_block(i + 1, b) for i, b in enumerate(bullets[:3])])
        + "\n\n"
        f"底部署名：{footer}\n\n"
        "【检查重点】\n"
        "1. 标题是否正确\n"
        "2. 副标题是否正确\n"
        "3. 是否有 3 条内容\n"
        "4. 每条内容的人物/地址/资产/金额是否正确\n"
        "5. 是否出现错字、漏字、乱码、不可读字体\n"
        "6. 是否出现错误数字\n"
        "7. 布局是否清晰，是否过于拥挤\n"
        "8. 是否符合 CoinMeta 官号风格：克制、信息卡、专业\n"
        "9. 是否出现不允许元素：\n"
        "   - 真实人物肖像\n"
        "   - 交易所 Logo\n"
        "   - 币种 Logo\n"
        "   - 黑客盗币画面\n"
        "   - 火箭、金钱雨、赌场感、暴富感\n"
        "   - 投资建议措辞（买入/卖出/跟单/稳赚/暴富）\n\n"
        "【输出格式】\n"
        "只输出 JSON，格式如下：\n\n"
        "{\n"
        '  "pass": true,\n'
        '  "score": 0,\n'
        '  "summary": "",\n'
        '  "text_errors": [],\n'
        '  "number_errors": [],\n'
        '  "layout_errors": [],\n'
        '  "risk_errors": [],\n'
        '  "style_errors": [],\n'
        '  "detected_text_summary": {\n'
        '    "title": "",\n'
        '    "subtitle": "",\n'
        '    "bullet_1": "",\n'
        '    "bullet_2": "",\n'
        '    "bullet_3": "",\n'
        '    "footer": ""\n'
        "  },\n"
        '  "regenerate_needed": false,\n'
        '  "regenerate_instructions": ""\n'
        "}\n\n"
        "【输出要求】\n"
        "- pass：只有在文字、数字、风格、风险都基本合格时才为 true\n"
        "- score：0-100\n"
        "- summary：一句中文总结\n"
        "- text_errors：列出错字、漏字、乱码问题\n"
        "- number_errors：列出数字错误\n"
        "- layout_errors：列出排版问题\n"
        "- risk_errors：列出任何违规元素\n"
        "- style_errors：列出不符合 CoinMeta 风格的问题\n"
        "- regenerate_needed：是否需要重生成\n"
        "- regenerate_instructions：如果需要重生成，用中文简洁写出修正要求，适合直接贴回 image2\n"
    )

    render_safe_prompt_cn = (
        "生成一张适合发布在 X 的中文加密市场栏目图，比例 4:5。\n\n"
        "这是一张带完整中文文字的信息卡，不是纯背景图。\n"
        "请严格按照以下三段信息模块排版，每个模块最多 3 行。\n"
        "请保持换行，不要自由改写文字。\n\n"
        f"标题：{title}\n"
        f"副标题：{subtitle}\n\n"
        + "\n\n".join(
            [
                f"{b.get('label')}：\n{_s(b.get('line_1'))}\n{_s(b.get('line_2'))}\n{_s(b.get('line_3'))}".rstrip()
                for b in render_safe_blocks[:3]
            ]
        )
        + "\n\n"
        f"底部署名：{footer}\n\n"
        "视觉要求：\n"
        "- 深色金融终端风格\n"
        "- 深蓝黑背景\n"
        "- 机构情报信息卡\n"
        "- 三个内容模块清晰分区\n"
        "- 标题醒目\n"
        "- 副标题克制\n"
        "- 中文必须清晰可读\n"
        "- 数字不要拆行\n"
        "- “万美元”和“ETH”不要被拆开\n"
        "- 留白充足\n"
        "- 可使用轻微网格、数据流、链上资金流动感\n"
        "- 可加入抽象鲸鱼轮廓作为弱背景，但不要抢文字\n\n"
        "严格限制：\n"
        "- 不要真实人物肖像\n"
        "- 不要交易所 Logo\n"
        "- 不要币种 Logo\n"
        "- 不要黑客盗币画面\n"
        "- 不要火箭\n"
        "- 不要金钱雨\n"
        "- 不要赌场感\n"
        "- 不要暴富感\n"
        "- 不要投资建议语气\n"
        "- 不要透视文字\n"
        "- 不要倾斜文字\n"
        "- 不要扭曲文字\n"
        "- 不要霓虹发光艺术字\n"
    )

    return {
        "content_type": "daily_whale_digest",
        "image_goal": "生成一张可直接用于 X 的 CoinMeta 栏目图",
        "must_include_text": must_text,
        "image2_prompt_cn": standard_prompt_cn,
        "image2_prompt_en": prompt_en_short,
        "layout_requirements": layout,
        "style_requirements": style,
        "negative_prompt": negative,
        "validation_checklist": checklist,
        "regenerate_prompt_template": regen_template_ultra_safe,
        "preferred_generation_order": ["render_safe_prompt_cn", "ultra_safe_prompt_cn", "standard_prompt_cn"],
        "prompt_variants": {
            "standard_prompt_cn": standard_prompt_cn,
            "ultra_safe_prompt_cn": ultra_safe_prompt_cn,
            "render_safe_prompt_cn": render_safe_prompt_cn,
            "prompt_en_short": prompt_en_short,
        },
        "validation": {"claude_validation_prompt": claude_validation_prompt},
        "regenerate": {"regenerate_prompt_template": regen_template_ultra_safe},
        "line_width_audit": line_width_audit,
        "overflow_warnings": overflow_warnings,
        "render_safe_blocks_compact": render_safe_blocks_compact if overflow_warnings else [],
        "generated_at": _utc_now_iso(),
        "source_path": str(COL_DIR / "daily_whale_digest.json"),
    }


def _render_prompt_md(pack: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# Image2 Prompt Pack\n\n")
    out.append(f"- content_type: {pack.get('content_type')}\n")
    out.append(f"- image_goal: {pack.get('image_goal')}\n")
    out.append(f"- generated_at: {pack.get('generated_at')}\n")
    out.append(f"- source_path: {pack.get('source_path')}\n")

    out.append("\n## Preferred Generation Order\n")
    pgo = pack.get("preferred_generation_order") if isinstance(pack.get("preferred_generation_order"), list) else []
    if pgo:
        out.append("Preferred Generation Order:\n")
        for i, x in enumerate(pgo, start=1):
            out.append(f"{i}. {x}\n")
    else:
        out.append("- (empty)\n")

    mit = pack.get("must_include_text") if isinstance(pack.get("must_include_text"), dict) else {}
    out.append("\n## Must Include Text\n")
    out.append(f"- title: {mit.get('title')}\n")
    out.append(f"- subtitle: {mit.get('subtitle')}\n")
    out.append(f"- footer: {mit.get('footer')}\n")
    out.append("\n### bullets\n")
    for b in (mit.get("bullets") or [])[:6]:
        out.append(f"- {b}\n")

    pvs = pack.get("prompt_variants") if isinstance(pack.get("prompt_variants"), dict) else {}
    out.append("\n## Prompt Variant - Standard\n")
    out.append(str(pvs.get("standard_prompt_cn") or pack.get("image2_prompt_cn") or "").strip() + "\n")
    out.append("\n## Prompt Variant - Render Safe\n")
    out.append(str(pvs.get("render_safe_prompt_cn") or "").strip() + "\n")
    out.append("\n## Prompt Variant - Ultra Safe\n")
    out.append(str(pvs.get("ultra_safe_prompt_cn") or "").strip() + "\n")
    out.append("\n## Prompt Variant - EN Short\n")
    out.append(str(pvs.get("prompt_en_short") or pack.get("image2_prompt_en") or "").strip() + "\n")

    out.append("\n## Negative Prompt\n")
    out.append(str(pack.get("negative_prompt") or "").strip() + "\n")

    out.append("\n## Validation Checklist\n")
    for x in (pack.get("validation_checklist") or [])[:30]:
        out.append(f"- {x}\n")

    out.append("\n## Render Safe Blocks\n")
    mit2 = pack.get("must_include_text") if isinstance(pack.get("must_include_text"), dict) else {}
    rsb = mit2.get("render_safe_blocks") if isinstance(mit2.get("render_safe_blocks"), list) else []
    if rsb:
        out.append("```json\n")
        out.append(json.dumps(rsb[:3], ensure_ascii=False, indent=2))
        out.append("\n```\n")
    else:
        out.append("- (empty)\n")

    out.append("\n## Line Width Audit\n")
    lwa = pack.get("line_width_audit") if isinstance(pack.get("line_width_audit"), dict) else {}
    out.append("```json\n")
    out.append(json.dumps(lwa, ensure_ascii=False, indent=2))
    out.append("\n```\n")

    out.append("\n## Overflow Warnings\n")
    ows = pack.get("overflow_warnings") if isinstance(pack.get("overflow_warnings"), list) else []
    out.append("```json\n")
    out.append(json.dumps(ows, ensure_ascii=False, indent=2))
    out.append("\n```\n")

    out.append("\n## Claude Validation Prompt\n")
    val = pack.get("validation") if isinstance(pack.get("validation"), dict) else {}
    out.append(str(val.get("claude_validation_prompt") or "").strip() + "\n")

    out.append("\n## Regenerate Prompt Template\n")
    reg = pack.get("regenerate") if isinstance(pack.get("regenerate"), dict) else {}
    out.append(str(reg.get("regenerate_prompt_template") or pack.get("regenerate_prompt_template") or "").strip() + "\n")

    return "".join(out)


def _render_validation_prompt_md(pack: dict[str, Any]) -> str:
    val = pack.get("validation") if isinstance(pack.get("validation"), dict) else {}
    prompt = str(val.get("claude_validation_prompt") or "").strip()
    out: list[str] = []
    out.append(prompt + "\n")
    out.append("\n---\n")
    out.append(f"generated_at: {_utc_now_iso()}\n")
    return "".join(out)


def _render_manual_loop_md(pack: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# Daily Whale Digest 手动 Image2 验证闭环\n\n")
    out.append("## 1. 本轮目标\n")
    out.append("验证「今天巨鲸在干嘛」栏目图能否稳定生成可发布的中文信息卡。\n\n")

    out.append("## 2. Prompt 使用顺序\n")
    pgo = pack.get("preferred_generation_order") if isinstance(pack.get("preferred_generation_order"), list) else []
    if pgo:
        for i, x in enumerate(pgo, start=1):
            out.append(f"{i}. {x}\n")
    else:
        out.append("1. render_safe_prompt_cn\n2. ultra_safe_prompt_cn\n3. standard_prompt_cn\n")
    out.append("\n")

    out.append("## 3. 第一次出图\n")
    out.append("复制 render_safe_prompt_cn 到 image2 生图窗口。\n")
    out.append("不要让模型自由改文案。\n")
    out.append("重点要求：中文准确、数字准确、三段模块清晰。\n\n")

    out.append("## 4. 人工初筛\n")
    out.append("- 标题是否为：今天巨鲸在干嘛\n")
    out.append("- 副标题是否为：3 个最值得看的链上动作\n")
    out.append("- 是否有 3 个模块\n")
    out.append("- Loracle / BTC空单 / 清算价33.12万美元 是否正确\n")
    out.append("- BTC多单 / 仓位超7000万美元 / 盈利5600万美元 是否正确\n")
    out.append("- ETH老钱包苏醒 / 存入1001 ETH / 仍持有3000 ETH 是否正确\n")
    out.append("- CoinMeta / 币界网 是否正确\n")
    out.append("- 是否有乱码\n")
    out.append("- 是否有错别字\n")
    out.append("- 是否有多余英文\n")
    out.append("- 是否有投资建议感\n")
    out.append("- 是否有暴富感\n\n")

    out.append("## 5. Claude 审图\n")
    out.append("把生成图发给 Claude，并粘贴 claude_validation_prompt。\n")
    out.append("要求 Claude 只输出 JSON。\n\n")

    out.append("## 6. 必须重生成的情况\n")
    out.append("- 中文乱码\n")
    out.append("- 数字错误\n")
    out.append("- 标题错误\n")
    out.append("- 少了某个模块\n")
    out.append("- 多了投资建议\n")
    out.append("- 画面太满\n")
    out.append("- 出现真人 / logo / 黑客 / 金钱雨 / 火箭\n")
    out.append("- 文字小到无法阅读\n\n")

    out.append("## 7. 重生成\n")
    out.append("使用 regenerate_prompt_template。\n")
    out.append("输入：\n")
    out.append("- 原始 render_safe_prompt_cn\n")
    out.append("- Claude 审图 JSON\n")
    out.append("- 需要修正的问题\n\n")

    out.append("## 8. 第二版验收\n")
    out.append("第二版只看三件事：\n")
    out.append("- 文字是否准确\n")
    out.append("- 画面是否清楚\n")
    out.append("- 是否符合 CoinMeta 官号安全边界\n\n")

    out.append("## 9. 通过后记录\n")
    out.append("- 使用的 prompt 版本\n")
    out.append("- 第几次生成通过\n")
    out.append("- 主要失败原因\n")
    out.append("- 最终可发布图路径\n")
    out.append("- 人工备注\n\n")

    out.append("## 10. 暂不做\n")
    out.append("- 不自动发 X\n")
    out.append("- 不自动调 API\n")
    out.append("- 不批量生成\n")
    out.append("- 不自动上传后台\n\n")

    out.append("---\n")
    out.append(f"generated_at: {_utc_now_iso()}\n")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--column", choices=["daily_whale_digest"], required=True)
    args = ap.parse_args()

    if args.column == "daily_whale_digest":
        src = COL_DIR / "daily_whale_digest.json"
        col = _read_json(src)
        pack = _build_prompt_pack_daily_whale_digest(col)
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        out_json = OUT_DIR / "daily_whale_digest_image2_prompt.json"
        out_md = OUT_DIR / "daily_whale_digest_image2_prompt.md"
        out_val = OUT_DIR / "daily_whale_digest_validation_prompt.md"
        out_loop = OUT_DIR / "daily_whale_digest_manual_image2_loop.md"

        out_json.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        out_md.write_text(_render_prompt_md(pack), encoding="utf-8")
        out_val.write_text(_render_validation_prompt_md(pack), encoding="utf-8")
        out_loop.write_text(_render_manual_loop_md(pack), encoding="utf-8")

        print(f"[image2_text_prompt_builder] ok column=daily_whale_digest out_dir={OUT_DIR}")
        print(f"[image2_text_prompt_builder] wrote: {out_json}")
        print(f"[image2_text_prompt_builder] wrote: {out_md}")
        print(f"[image2_text_prompt_builder] wrote: {out_val}")
        print(f"[image2_text_prompt_builder] wrote: {out_loop}")


if __name__ == "__main__":
    main()

