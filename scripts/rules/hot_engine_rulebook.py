from __future__ import annotations

import re
from typing import Any


def _clamp(v: int) -> int:
    try:
        n = int(v)
    except Exception:
        n = 0
    if n < 0:
        return 0
    if n > 100:
        return 100
    return n


def _t(*items: str) -> str:
    return "\n".join([x for x in items if x]).lower()


P0_KEYWORDS = [
    "马斯克",
    "openai",
    "binance",
    "币安",
    "sec",
    "美联储",
    "btc",
    "比特币",
    "eth",
    "以太坊",
    "特朗普",
    "黑客",
    "被黑",
    "交易所",
    "暂停提币",
    "巨鲸",
    "清算",
    "etf",
]

P1_KEYWORDS = [
    "ai算力",
    "算力",
    "支付",
    "入口",
    "稳定币",
    "stablecoin",
    "rwa",
    "defi",
    "收益",
    "宏观",
    "能源",
    "芯片",
    "地缘",
]

P2_KEYWORDS = [
    "tvl",
    "restaking",
    "basis trade",
    "funding arbitrage",
    "研报",
    "研究",
    "观点",
    "央行",
    "审议委员",
    "副行长",
]

P3_KEYWORDS = [
    "交易对维护",
    "参数调整",
    "上落价位",
    "最小变动幅度",
    "tick size",
    "最低上落价位",
    "币币交易对",
    "评级",
    "中间价",
    "融资",
]

USER_CONNECTION = [
    "钱",
    "风险",
    "价格",
    "账户",
    "钱包",
    "交易所",
    "支付",
    "提现",
    "清算",
    "手续费",
    "成本",
    "滑点",
    "空投",
    "提币",
]

JARGON_PENALTY = [
    "tvl",
    "rwa",
    "restaking",
    "basis trade",
    "funding arbitrage",
]

WHALE_KEYWORDS = [
    "巨鲸",
    "鲸",
    "地址",
    "钱包",
    "0x",
    "转入",
    "转出",
    "存入",
    "提币",
    "入金",
    "出金",
    "补保证金",
    "追加保证金",
    "保证金",
    "多仓",
    "空仓",
    "仓位",
    "杠杆",
    "清算",
    "清算价",
    "爆仓",
    "强平",
    "浮盈",
    "浮亏",
    "回撤",
    "休眠",
    "lookonchain",
    "arkham",
    "whale alert",
    "hyperliquid",
    "bybit",
    "okx",
    "binance",
    "upbit",
]

WHALE_ASSET_HINTS = [
    "btc",
    "eth",
    "sol",
    "usdt",
    "usdc",
    "hype",
    "zec",
    "sp500",
    "xaut",
    "nkn",
    "pendle",
]


def _is_etf_flow(text: str) -> bool:
    t = (text or "").lower()
    if "etf" not in t and "现货" not in t:
        return False
    flow_terms = ["净流入", "净流出", "资金流", "单日流入", "单日流出", "inflow", "outflow"]
    if not any(k in t for k in flow_terms):
        return False
    if not any(k in t for k in ["btc", "比特币", "eth", "以太坊"]):
        return False
    return True


def _has_etf_strong_hook(text: str) -> bool:
    t = (text or "").lower()
    strong = [
        "历史最大",
        "历史新高",
        "创纪录",
        "创记录",
        "近3个月",
        "近 3 个月",
        "3个月",
        "近6个月",
        "近 6 个月",
        "6个月",
        "年内最大",
        "年内新高",
        "连续",
        "异常",
        "背离",
        "贝莱德",
        "blackrock",
        "ibit",
        "富达",
        "fidelity",
        "fbtc",
        "机构赎回",
        "配置变化",
        "流动性",
        "宏观",
        "风险资产",
        "大跌",
        "大涨",
    ]
    return any(k.lower() in t for k in strong)


def _is_whale_candidate(text: str) -> bool:
    t = (text or "").lower()
    if ("claude" in t or "chatbot" in t) and any(k in t for k in ["找回", "恢复"]) and any(k in t for k in ["seed phrase", "wallet.dat", "助记词"]):
        return False
    return any(k in t for k in WHALE_KEYWORDS)


def _extract_address(text: str) -> str:
    t = text or ""
    m = re.search(r"0x[a-f0-9]{6,64}", t.lower())
    if m:
        return m.group(0)
    m2 = re.search(r"0x[a-f0-9]{3,10}\.\.\.[a-f0-9]{3,10}", t.lower())
    if m2:
        return m2.group(0)
    if ("地址" in t) or ("钱包" in t):
        m3 = re.search(r"0x[a-f0-9]{4,10}", t.lower())
        if m3:
            return m3.group(0)
    return ""


def _extract_asset(text: str) -> str:
    t = (text or "").lower()
    for a in WHALE_ASSET_HINTS:
        if a in t:
            return a.upper()
    return ""


def _extract_amount_usd(text: str) -> float | None:
    t = (text or "").lower()
    matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(亿|万)?\s*(?:美元|usd|美金)", t)
    if not matches:
        return None
    best: float | None = None
    for num_s, unit in matches:
        num = float(num_s)
        if unit == "亿":
            num *= 100_000_000
        elif unit == "万":
            num *= 10_000
        if best is None or num > best:
            best = num
    return best


def _extract_pnl_usd(text: str) -> float | None:
    t = (text or "").lower()
    matches = re.findall(r"(浮亏|亏损|回撤|浮盈|盈利|盈超|盈)\D{0,20}?([0-9]+(?:\.[0-9]+)?)\s*(亿|万)?\s*(?:美元|usd|美金)", t)
    if not matches:
        return None
    best: float | None = None
    for kind, num_s, unit in matches:
        num = float(num_s)
        if unit == "亿":
            num *= 100_000_000
        elif unit == "万":
            num *= 10_000
        if kind in {"浮亏", "亏损", "回撤"}:
            num = -abs(num)
        else:
            num = abs(num)
        if best is None or abs(num) > abs(best):
            best = num
    return best


def _extract_liquidation_price(text: str) -> str:
    t = (text or "").lower()
    m = re.search(r"(?:清算价|强平价)\D{0,10}?([0-9]+(?:\.[0-9]+)?)", t)
    if m:
        return m.group(1)
    return ""


def _extract_action(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["买入", "增持", "再买入", "买进"]):
        return "buy"
    if any(k in t for k in ["卖出", "减持"]):
        return "sell"
    if any(k in t for k in ["转入", "存入", "入金"]):
        return "deposit"
    if any(k in t for k in ["转出", "提币", "出金"]):
        return "withdraw"
    if any(k in t for k in ["补保证金", "追加保证金"]):
        return "add_margin"
    if any(k in t for k in ["接近清算", "清算线", "强平线", "爆仓"]):
        return "liquidation_risk"
    if any(k in t for k in ["浮盈", "浮亏", "回撤"]):
        return "pnl_change"
    if "休眠" in t:
        return "dormancy_wakeup"
    return ""


def _extract_actor_label(text: str) -> str:
    t = (text or "").lower()
    if "a16z" in t:
        return "a16z相关钱包"
    if "bit" in t and "巨鲸" in t:
        return "bit关联巨鲸"
    if "巨鲸" in t:
        return "巨鲸地址"
    if "聪明钱" in t:
        return "聪明钱"
    if "交易员" in t:
        return "高关注交易员"
    addr = _extract_address(t)
    if addr:
        return f"地址 {addr[:10]}…"
    return ""


def _is_strong_whale_story(text: str, amount_usd: float | None) -> bool:
    t = (text or "").lower()
    liq = any(k in t for k in ["清算", "强平", "爆仓", "清算线", "强平线"])
    huge = amount_usd is not None and amount_usd >= 20_000_000
    return bool(liq and huge)


def audience_reach_score(text: str) -> int:
    t = (text or "").lower()
    score = 50

    if any(k.lower() in t for k in ["马斯克", "openai", "binance", "sec", "美联储", "btc", "eth", "特朗普", "黑客", "巨鲸", "清算"]):
        score += 30
    if any(k in t for k in ["钱", "钱包", "账户", "交易所", "提现", "支付", "空投", "风险", "提币"]):
        score += 25
    if re.search(r"\d", t) and any(x in t for x in ["亿美元", "万", "亿", "枚", "btc", "桶/日", "万美元", "美元"]):
        score += 20
    if any(k in t for k in ["法院", "飞机", "旧电脑", "钱包文件", "家庭账单", "油轮", "交易所账户", "车队", "航班"]):
        score += 20
    if any(k in t for k in ["反差", "人在", "但", "仍可能", "随时传唤", "随时召回"]):
        if "法庭" in t or "传唤" in t or "召回" in t:
            score += 15
    if any(k in t for k in ["市场情绪", "风险偏好", "资产价格", "定价", "流动性"]):
        score += 15

    if any(k in t for k in JARGON_PENALTY):
        score -= 30
    if any(k in t for k in ["单一协议", "小圈层", "仅限"]):
        score -= 25
    if any(k in t for k in ["单一国家", "仅影响某国"]) and not any(k in t for k in USER_CONNECTION):
        score -= 20
    if any(k in t for k in ["需要大量背景", "背景很复杂", "难以理解"]):
        score -= 20
    if any(k in t for k in ["表示", "称", "指出", "强调"]) and not any(k in t for k in ["法院", "交易所", "钱包", "清算", "黑客", "飞机", "账单"]):
        score -= 15
    if any(k in t for k in ["研报", "研究员", "报告"]) and not any(k in t for k in ["链上", "地址", "清算", "交易所"]):
        score -= 15

    return _clamp(score)


def topic_priority(text: str) -> str:
    t = (text or "").lower()
    if any(k.lower() in t for k in P0_KEYWORDS):
        return "P0"
    if any(k.lower() in t for k in P1_KEYWORDS):
        return "P1"
    if any(k.lower() in t for k in P2_KEYWORDS):
        return "P2"
    if any(k.lower() in t for k in P3_KEYWORDS):
        return "P3"
    return "P2"


def _has_user_connection(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in USER_CONNECTION)


def _best_source_rank(item: dict[str, Any]) -> int:
    url = str(item.get("source_url") or "").lower().strip()
    source_name = str(item.get("source_name") or "").lower().strip()
    text = _t(str(item.get("title") or ""), str(item.get("raw_text") or ""))

    has_scan = any(x in url for x in ["etherscan.io", "arbiscan.io", "polygonscan.com"])
    has_court = any(x in url for x in ["sec.gov", ".gov", "court"]) or any(x in text for x in ["法院文件", "判决书", "起诉书"])
    has_tx = "txid" in text or bool(re.search(r"0x[a-f0-9]{10,64}", text))

    if has_scan or has_court or has_tx:
        return 1
    if any(x in url for x in ["reuters.com", "bloomberg.com", "ft.com", "wsj.com", "coindesk.com", "theblock.co", "cointelegraph.com"]):
        return 2
    if "coinmeta" in source_name and any(x in text for x in ["据路透", "据彭博", "据ft", "据wsj", "reuters", "bloomberg", "financial times"]):
        return 3
    if any(x in source_name for x in ["jin10", "odaily", "watcherguru", "wublockchain", "tg:", "webhook"]):
        return 4
    return 5


def select_best_source(items: list[dict[str, Any]]) -> tuple[str, int]:
    best_id = ""
    best_rank = 9
    for it in items:
        iid = str(it.get("input_id") or "").strip()
        r = _best_source_rank(it)
        if r < best_rank:
            best_rank = r
            best_id = iid
    return best_id, best_rank


def _is_hot_signal_source(item: dict[str, Any]) -> bool:
    source_name = str(item.get("source_name") or "").lower()
    return any(x in source_name for x in ["tg:", "webhook", "kol"])


def evaluate_event(cluster: dict[str, Any]) -> dict[str, Any]:
    items = cluster.get("items") or []
    text = _t(*[str(x.get("title") or "") for x in items], *[str(x.get("raw_text") or "") for x in items])

    pr = topic_priority(text)
    ar = audience_reach_score(text)

    best_id, best_rank = select_best_source(items)
    has_best_source = bool(best_id)

    cluster_title = str(cluster.get("cluster_title") or "")
    for it in items:
        if str(it.get("input_id") or "").strip() == str(best_id):
            cluster_title = str(it.get("title") or it.get("short_title") or cluster_title).strip()
            break

    hot_signal_ids = [str(x.get("input_id") or "").strip() for x in items if _is_hot_signal_source(x)]
    source_names = sorted({str(x.get("source_name") or "").strip() for x in items if str(x.get("source_name") or "").strip()})

    if pr == "P1" and not _has_user_connection(text):
        pr_effective = "P2"
    else:
        pr_effective = pr

    source_score_map = {1: 95, 2: 85, 3: 75, 4: 60, 5: 45}
    source_score = source_score_map.get(best_rank, 45)
    fact_score = source_score
    heat_score_map = {"P0": 90, "P1": 70, "P2": 50, "P3": 30}
    heat_score = heat_score_map.get(pr, 50)
    content_score = ar
    angle_score = ar
    total_score = _clamp(round((source_score + fact_score + heat_score + content_score + angle_score) / 5))

    jargon_heavy = any(k in text for k in JARGON_PENALTY)
    macro_plain = any(k in text for k in ["央行", "副行长", "审议委员", "政策"]) and not any(
        k in text for k in ["法院", "飞机", "账单", "车队", "交易所", "钱包"]
    )
    plain_announcement = any(k in text for k in ["公告", "宣布", "上线", "更新", "参数调整", "维护"]) and not _has_user_connection(text)
    plain_research = any(k in text for k in ["研报", "研究员", "报告"]) and not any(k in text for k in ["链上", "地址", "清算", "交易所"])

    etf_flow = _is_etf_flow(text)
    etf_strong_hook = _has_etf_strong_hook(text)

    missing_facts: list[str] = []
    if best_rank >= 4:
        missing_facts.append("补一手来源（Reuters/Bloomberg/官方文件/原文链接）")
    if pr in {"P0", "P1"} and any(k in text for k in ["法院", "法官", "庭审", "传唤", "起诉"]):
        missing_facts.append("补权威庭审来源/法院文件/原始报道原链路")
    if any(k in text for k in ["黑客", "被黑", "暂停提币", "挤兑"]):
        missing_facts.append("补交易所公告/链上地址/安全通报或原帖链接")
    if any(k in text for k in ["战争", "制裁", "伊朗", "霍尔木兹", "能源", "油轮"]) and not any(k in text for k in ["油轮", "航班", "账单", "车队"]):
        missing_facts.append("补现实场景/一手报道（否则仅宏观表态）")

    missing_facts = [x for x in missing_facts if x]

    worth_spending_claude = False
    allowed_to_generate = False

    only_secondary = all(_best_source_rank(x) >= 4 for x in items) if items else True
    best_is_secondary = best_rank >= 4
    best_is_signal = any(str(best_id) == str(x.get("input_id") or "").strip() and _is_hot_signal_source(x) for x in items)

    if etf_flow and not etf_strong_hook:
        queue = "monitor" if ar >= 40 else "reject"
        publish_mode = "monitor" if queue == "monitor" else "reject"
        worth_spending_claude = False
        allowed_to_generate = False
        if queue == "reject":
            rule_reason = "进入 reject：routine_etf_flow_low_virality（普通ETF资金流，无强钩子，传播价值低）"
        else:
            rule_reason = "进入 monitor：routine_etf_flow_low_virality（普通ETF资金流，无强钩子，不默认进 queue_review）"
    else:
        if (
            ar >= 70
            and pr_effective in {"P0", "P1"}
            and fact_score >= 70
            and has_best_source
            and not (only_secondary and best_is_secondary and best_is_signal)
            and not plain_announcement
            and not plain_research
            and not macro_plain
            and not jargon_heavy
        ):
            queue = "queue_review"
            publish_mode = "queue_review"
            worth_spending_claude = True
            allowed_to_generate = True
            rule_reason = "进入 queue_review：受众面达标 + P0/P1 + 事实硬 + 有最佳来源 + 可转化为中文X传播角度"
        else:
            is_boe_stablecoin = ("bank of england" in text or "英国央行" in text or "英格兰银行" in text) and ("stablecoin" in text or "稳定币" in text)
            stablecoin_has_user_link = any(k in text for k in ["usdt", "usdc", "交易所", "钱包", "账户", "资金安全", "风险"])

            if is_boe_stablecoin and not stablecoin_has_user_link:
                queue = "monitor"
                publish_mode = "monitor"
                rule_reason = "进入 monitor：英国央行稳定币规则属P1但缺用户连接点（未连接USDT/USDC/主流交易所/资金安全）"
            elif jargon_heavy and pr_effective != "P0":
                if ar < 55:
                    queue = "reject"
                    publish_mode = "reject"
                    rule_reason = "进入 reject：圈内术语堆叠（TVL/RWA/restaking等），受众面窄，补事实也难转化"
                else:
                    queue = "monitor"
                    publish_mode = "monitor"
                    rule_reason = "进入 monitor：圈内术语偏多，受众面有限，暂不适合发X"
            elif ar < 40 or pr_effective == "P3" or plain_announcement:
                queue = "reject"
                publish_mode = "reject"
                rule_reason = "进入 reject：P3/普通公告/受众面过窄，补事实也难变成中文X内容"
            else:
                can_source_research = ar >= 55 and pr_effective in {"P0", "P1"} and (fact_score < 70 or best_rank >= 3)
                if ar < 50 and pr_effective != "P0":
                    can_source_research = False

                if can_source_research and (not jargon_heavy) and (not macro_plain) and (not plain_research):
                    queue = "source_research"
                    publish_mode = "monitor"
                    rule_reason = "进入 source_research：题材受众面够，但事实不够硬；补完后有机会变成中文X内容"
                else:
                    queue = "monitor"
                    publish_mode = "monitor"
                    rule_reason = "进入 monitor：行业可能有意义，但当前受众面/连接点/事实不足，不适合立刻发X"

    risk_level = "low"
    if any(k in text for k in ["法院", "法官", "庭审", "传唤", "起诉", "被曝", "知情人士"]):
        risk_level = "medium"
    if any(k in text for k in ["暂停提币", "挤兑", "被黑", "黑客", "exploit", "hacked"]):
        risk_level = "high"

    actor_label = ""
    asset = ""
    action = ""
    amount_usd: float | None = None
    pnl_usd: float | None = None
    liquidation_price = ""
    comment_angle = ""
    dashboard_url = ""
    source_url = ""

    if _is_whale_candidate(text):
        best_item: dict[str, Any] | None = None
        for it in items:
            if str(it.get("input_id") or "").strip() == str(best_id):
                best_item = it
                break
        if best_item is None and items:
            best_item = items[0]

        whale_text = text
        if best_item is not None:
            whale_text = _t(str(best_item.get("title") or ""), str(best_item.get("raw_text") or ""))

        actor_label = _extract_actor_label(whale_text)
        asset = _extract_asset(whale_text)
        action = _extract_action(whale_text)
        amount_usd = _extract_amount_usd(whale_text)
        pnl_usd = _extract_pnl_usd(whale_text)
        liquidation_price = _extract_liquidation_price(whale_text)
        addr = _extract_address(whale_text)

        if best_item is not None:
            source_url = str(best_item.get("source_url") or "").strip()
            if any(x in source_url.lower() for x in ["etherscan.io", "arbiscan.io", "polygonscan.com", "arkham.com", "nansen.ai", "debank.com", "dune.com"]):
                dashboard_url = source_url

        is_scan_link = any(x in (source_url or "").lower() for x in ["etherscan.io", "arbiscan.io", "polygonscan.com"])
        has_anchor = bool(addr) or bool(dashboard_url) or is_scan_link
        strong_story = _is_strong_whale_story(whale_text, amount_usd)

        if queue == "queue_review" and not strong_story:
            queue = "whale_digest"
            publish_mode = "whale_digest"
            worth_spending_claude = False
            allowed_to_generate = False
            rule_reason = "进入 whale_digest：链上/巨鲸/仓位类事件，适合汇总栏目，不默认进 queue_review"

        if queue != "queue_review":
            if not has_anchor:
                queue = "source_research"
                publish_mode = "monitor"
                worth_spending_claude = False
                allowed_to_generate = False
                if not missing_facts:
                    missing_facts = []
                if "补链上链接/地址/仓位截图" not in missing_facts:
                    missing_facts.append("补链上链接/地址/仓位截图/内部看板链接")
                rule_reason = "进入 source_research：巨鲸/仓位信息缺地址或链上/看板链接，需补事实锚点"
            else:
                if queue not in {"whale_digest", "queue_review"}:
                    queue = "whale_digest"
                    publish_mode = "whale_digest"
                    worth_spending_claude = False
                    allowed_to_generate = False
                    rule_reason = "进入 whale_digest：链上/巨鲸/仓位变化，留作每日汇总栏目"

        if strong_story and has_anchor:
            queue = "queue_review"
            publish_mode = "queue_review"
            worth_spending_claude = True
            allowed_to_generate = True
            rule_reason = "进入 queue_review：巨鲸/仓位事件具备强故事性且金额极大/清算风险，一眼能懂"

        if queue == "whale_digest":
            if action in {"liquidation_risk", "pnl_change"}:
                comment_angle = "清算风险/仓位变化是市场情绪的温度计"
            elif action in {"deposit", "withdraw"}:
                comment_angle = "转入/转出交易所更像资金行为信号，适合放进每日汇总"
            else:
                comment_angle = "聪明钱/巨鲸行为更适合做汇总追踪，而不是单条硬推"

    return {
        "event_cluster_id": cluster.get("event_cluster_id") or "",
        "cluster_title": cluster_title,
        "cluster_queue": queue,
        "topic_priority": pr,
        "audience_reach_score": ar,
        "source_score": source_score,
        "fact_score": fact_score,
        "heat_score": heat_score,
        "content_score": content_score,
        "angle_score": angle_score,
        "total_score": total_score,
        "best_source_item_id": best_id,
        "best_source_rank": best_rank,
        "best_source": best_id,
        "hot_signal_sources": [str(x.get("source_name") or "").strip() for x in items if _is_hot_signal_source(x)],
        "item_count": int(cluster.get("item_count") or len(items)),
        "included_tweet_ids": [str(x.get("input_id") or "").strip() for x in items if str(x.get("input_id") or "").strip()],
        "source_names": source_names,
        "hot_signal_item_ids": [x for x in hot_signal_ids if x and x != best_id],
        "worth_spending_claude": worth_spending_claude,
        "allowed_to_generate": allowed_to_generate,
        "missing_facts": missing_facts,
        "rule_reason": rule_reason,
        "cluster_reason": cluster.get("cluster_reason") or "",
        "actor_label": actor_label,
        "asset": asset,
        "action": action,
        "amount_usd": amount_usd if amount_usd is not None else "",
        "pnl_usd": pnl_usd if pnl_usd is not None else "",
        "liquidation_price": liquidation_price,
        "source_url": source_url,
        "dashboard_url": dashboard_url,
        "comment_angle": comment_angle,
        "risk_level": risk_level,
    }

