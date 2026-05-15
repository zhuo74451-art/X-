from __future__ import annotations

import re
from typing import Any


_TYPE_KEYWORDS: dict[str, list[str]] = {
    "stablecoin_policy": [
        "stablecoin",
        "稳定币",
        "bank of england",
        "英格兰银行",
        "boe",
        "支付稳定币",
        "监管框架",
        "央行",
    ],
    "crypto_regulation": [
        "监管",
        "处罚",
        "罚款",
        "执法",
        "调查",
        "sec",
        "cftc",
        "sfc",
        "fca",
        "mas",
        "法案",
        "条例",
        "合规",
    ],
    "ai_crypto_story": [
        "claude",
        "openai",
        "ai",
        "agent",
        "codex",
        "btc 找回",
        "找回",
        "钱包恢复",
        "助记词",
        "seed phrase",
    ],
    "whale_onchain": [
        "巨鲸",
        "地址",
        "转入",
        "转出",
        "清算价",
        "杠杆",
        "多单",
        "空单",
        "hyperliquid",
        "lookonchain",
        "ember",
        "麻吉",
        "whale alert",
    ],
    "exchange_risk": [
        "交易所风险",
        "暂停提现",
        "冻结",
        "挤兑",
        "爆雷",
        "破产",
        "清算风险",
        "ftx",
        "binance",
        "coinbase",
        "okx",
    ],
    "security_incident": [
        "黑客",
        "被盗",
        "攻击",
        "漏洞",
        "exploit",
        "phishing",
        "hacked",
        "hack",
    ],
    "macro_market": [
        "etf",
        "美联储",
        "cpi",
        "油价",
        "利率",
        "美元",
        "央行",
        "汇率",
        "国债",
        "通胀",
        "收益率",
    ],
    "product_update": [
        "升级",
        "上线",
        "发布",
        "测试网",
        "主网",
        "版本",
        "hardfork",
        "mainnet",
        "testnet",
        "下架",
        "delist",
        "永续",
        "合约",
        "futures",
    ],
}


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def classify_event_type(event_cluster: dict[str, Any]) -> dict[str, Any]:
    title = str(event_cluster.get("cluster_title") or "")
    summary = str(event_cluster.get("raw_summary") or "")
    sources = " ".join([str(x) for x in (event_cluster.get("source_names") or [])])
    text = _norm("\n".join([title, summary, sources]))

    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    for tp, kws in _TYPE_KEYWORDS.items():
        hit: list[str] = []
        score = 0
        for kw in kws:
            k = kw.lower()
            if k and k in text:
                hit.append(kw)
                score += 10
        if hit:
            scores[tp] = score
            reasons[tp] = hit

    if not scores:
        return {"event_type": "unknown", "confidence": 0, "reason": "no keyword matched"}

    best_type = max(scores.items(), key=lambda x: x[1])[0]
    best_score = scores[best_type]

    # tie-breakers / overrides
    if any(x in title for x in ["下架", "永续", "合约"]) or ("delist" in title.lower()) or ("futures" in text):
        best_type = "product_update"
        best_score = max(best_score, 75)

    if "稳定币" in title or "stablecoin" in title.lower():
        best_type = "stablecoin_policy"
        best_score = max(best_score, 70)

    if ("usdt" in text or "usdc" in text) and best_type == "stablecoin_policy":
        policy_markers = [
            "bank of england",
            "boe",
            "英格兰银行",
            "央行",
            "监管",
            "框架",
            "规则",
            "proposal",
            "bill",
            "限制",
            "放宽",
        ]
        if not any(m in text for m in policy_markers):
            best_type = "product_update" if any(x in title for x in ["下架", "永续", "合约"]) else "macro_market"
            best_score = max(60, best_score - 10)

    if "黑客" in title or "被盗" in title or "漏洞" in title:
        best_type = "security_incident"
        best_score = max(best_score, 80)
    if ("claude" in title.lower()) or ("找回" in title) or ("钱包" in title):
        if "黑客" not in title and "被盗" not in title:
            best_type = "ai_crypto_story"
            best_score = max(best_score, 70)

    conf = max(20, min(95, best_score))
    rs = reasons.get(best_type) or []
    return {"event_type": best_type, "confidence": int(conf), "reason": "matched: " + ",".join(rs[:8])}

