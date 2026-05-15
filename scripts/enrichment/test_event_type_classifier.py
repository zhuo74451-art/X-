from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from event_type_classifier import classify_event_type


def _assert_in(label: str, got: str, allowed: list[str]) -> None:
    if got not in allowed:
        raise AssertionError(f"{label}: got={got} allowed={allowed}")


def main() -> None:
    cases = [
        (
            "stablecoin_policy",
            {
                "cluster_title": "英格兰银行准备放宽对稳定币的限制",
                "raw_summary": "Bank of England / BoE stablecoin proposals FT",
                "source_names": ["news:coindesk"],
            },
            ["stablecoin_policy", "crypto_regulation"],
        ),
        (
            "whale_onchain",
            {
                "cluster_title": "巨鲸地址向交易所转入 10,000 ETH，疑似准备卖出",
                "raw_summary": "Lookonchain / Hyperliquid",
                "source_names": ["webhook"],
            },
            ["whale_onchain"],
        ),
        (
            "ai_crypto_story",
            {
                "cluster_title": "比特币投资者利用 Claude 恢复 5 枚 BTC",
                "raw_summary": "AI 找回 / 钱包恢复 / seed phrase",
                "source_names": ["news:cointelegraph"],
            },
            ["ai_crypto_story"],
        ),
        (
            "security_incident",
            {
                "cluster_title": "某 DeFi 协议遭黑客攻击，被盗 5000 万美元",
                "raw_summary": "exploit phishing hacked",
                "source_names": ["news:coindesk"],
            },
            ["security_incident"],
        ),
        (
            "macro_market",
            {
                "cluster_title": "BTC 现货 ETF 单日净流出 6.35 亿美元",
                "raw_summary": "ETF outflow",
                "source_names": ["news:coindesk"],
            },
            ["macro_market"],
        ),
    ]

    for label, ev, allowed in cases:
        out = classify_event_type(ev)
        _assert_in(label, str(out.get("event_type") or ""), allowed)

    print("[test_event_type_classifier] OK")


if __name__ == "__main__":
    main()

