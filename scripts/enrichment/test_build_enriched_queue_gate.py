from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENRICHMENT_DIR = Path(__file__).resolve().parent
if str(ENRICHMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENRICHMENT_DIR))

from build_enriched_queue import should_promote_enriched_event


def _base_fact_pack(event_type: str) -> dict:
    return {
        "event_type": event_type,
        "upgrade_recommendation": "queue_review",
        "source_risk": "low",
        "best_sources": [{"tier": "P0", "source_name": "Official", "domain": "example.com", "url": "https://example.com"}],
        "confirmed_facts": ["Fact A"],
        "missing_facts": [],
        "angle_candidates": ["对普通用户的直接影响是什么？"],
        "required_facts_status": {"satisfied": ["x"], "missing": [], "not_required_removed": []},
        "reason": "ok",
    }


def test_a_kucoin_routine_delist_not_promoted() -> None:
    event = {
        "event_cluster_id": "524932f22e56",
        "cluster_title": "KuCoin 将下架 MLNUSDT 永续合约",
        "raw_summary": "公告：将下架永续合约，暂停新开仓，平仓不受影响。",
        "source_names": ["kucoin_ann"],
        "audience_reach_score": 80,
        "angle_score": 80,
        "content_score": 80,
        "total_score": 80,
        "topic_priority": "P2",
    }
    fact_pack = _base_fact_pack("product_update")
    out = should_promote_enriched_event(event, fact_pack)
    assert out["promote"] is False
    assert "routine_exchange_update_low_virality" in (out.get("demotion_reasons") or [])


def test_b_claude_recover_btc_promoted_when_ok() -> None:
    event = {
        "event_cluster_id": "eb0dc6cf6022",
        "cluster_title": "一个人靠 Claude 找回 5 枚 BTC",
        "raw_summary": "不是破解钱包，而是系统性翻旧设备和备份，找回助记词。",
        "source_names": ["coindesk"],
        "audience_reach_score": 72,
        "angle_score": 78,
        "content_score": 75,
        "total_score": 77,
        "topic_priority": "P1",
    }
    fact_pack = _base_fact_pack("ai_crypto_story")
    fact_pack["angle_candidates"] = ["普通用户能懂：丢失的钱包可能只是线索散落在旧设备里"]
    out = should_promote_enriched_event(event, fact_pack)
    assert out["promote"] is True


def test_c_exchange_withdrawal_halt_not_demoted_as_routine() -> None:
    event = {
        "event_cluster_id": "ex_halt_1",
        "cluster_title": "某交易所突发暂停提款",
        "raw_summary": "平台公告：暂停提币与充提，用户资金安全引发担忧。",
        "source_names": ["official"],
        "audience_reach_score": 65,
        "angle_score": 70,
        "content_score": 70,
        "total_score": 72,
        "topic_priority": "P1",
    }
    fact_pack = _base_fact_pack("exchange_risk")
    fact_pack["angle_candidates"] = ["强用户影响：提款暂停/充提关闭可能影响大量用户资产流动性"]
    out = should_promote_enriched_event(event, fact_pack)
    assert out["promote"] is True
    assert "routine_exchange_update_low_virality" not in (out.get("demotion_reasons") or [])


def test_d_routine_etf_flow_not_promoted() -> None:
    event = {
        "event_cluster_id": "etf_flow_1",
        "cluster_title": "BTC 现货 ETF 单日净流出 6.35 亿美元",
        "raw_summary": "无历史纪录、无连续趋势、无明显价格背离。",
        "source_names": ["coindesk"],
        "audience_reach_score": 75,
        "angle_score": 70,
        "content_score": 70,
        "total_score": 70,
        "topic_priority": "P2",
    }
    fact_pack = _base_fact_pack("macro_market")
    fact_pack["angle_candidates"] = ["数据更新：关注明日是否反转"]
    out = should_promote_enriched_event(event, fact_pack)
    assert out["promote"] is False
    assert "routine_market_flow_low_virality" in (out.get("demotion_reasons") or [])


def main() -> None:
    test_a_kucoin_routine_delist_not_promoted()
    test_b_claude_recover_btc_promoted_when_ok()
    test_c_exchange_withdrawal_halt_not_demoted_as_routine()
    test_d_routine_etf_flow_not_promoted()
    print("[test_build_enriched_queue_gate] ok")


if __name__ == "__main__":
    main()

