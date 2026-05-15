from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
VISUAL_DIR = Path(__file__).resolve().parent
for p in [str(SCRIPTS_DIR), str(VISUAL_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from visual.image_brief_builder import build_visual_brief


def test_whale_digest_template_card() -> None:
    event = {
        "event_cluster_id": "w1",
        "cluster_title": "巨鲸地址转出 5000 ETH",
        "raw_summary": "Lookonchain 监测到巨鲸地址转出。",
        "cluster_queue": "whale_digest",
        "source_urls": ["https://example.com/a"],
        "actor_label": "巨鲸地址",
        "asset": "ETH",
        "action": "转出",
        "amount_usd": "10000000",
    }
    brief = build_visual_brief(event=event, queue="whale_digest", fact_pack=None)
    assert brief["visual_strategy"] == "auto_template"
    assert brief["auto_generate_allowed"] is True
    assert brief["auto_publish_allowed"] is False
    assert brief["template_name"] == "whale_digest_card"
    assert brief["visual_mode"] == "template_card"


def test_ai_crypto_story_generated_image_prompt_constraints() -> None:
    event = {
        "event_cluster_id": "a1",
        "cluster_title": "一个人靠 Claude 找回 5 枚 BTC",
        "raw_summary": "不是破解钱包，而是系统性翻旧设备和备份，找回助记词。",
        "cluster_queue": "source_research",
        "source_urls": ["https://example.com/a"],
    }
    fact_pack = {
        "event_type": "ai_crypto_story",
        "angle_candidates": ["普通用户能懂：很多丢失的钱包只是线索散落在旧设备里"],
    }
    brief = build_visual_brief(event=event, queue="source_research", fact_pack=fact_pack)
    assert brief["visual_strategy"] == "ai_generated_candidate"
    assert brief["auto_generate_allowed"] is False
    assert brief["auto_publish_allowed"] is False
    assert brief["visual_mode"] == "generated_image"
    assert isinstance(brief.get("image_search_queries"), list) and len(brief.get("image_search_queries")) >= 2
    p2 = str(brief.get("image2_prompt") or "")
    assert "不出现" in p2
    assert "黑客" in p2
    assert "破解" in p2


def test_stablecoin_policy_no_image_or_data_card() -> None:
    event = {
        "event_cluster_id": "s1",
        "cluster_title": "英格兰银行拟放宽稳定币限制",
        "raw_summary": "涉及监管框架与支付稳定币。",
        "cluster_queue": "source_research",
        "source_urls": ["https://example.com/a"],
    }
    fact_pack = {"event_type": "stablecoin_policy"}
    brief = build_visual_brief(event=event, queue="source_research", fact_pack=fact_pack)
    assert brief["visual_mode"] in {"no_image", "data_card"}
    assert brief["visual_strategy"] == "no_visual"
    assert brief["auto_generate_allowed"] is False
    assert brief["auto_publish_allowed"] is False


def main() -> None:
    test_whale_digest_template_card()
    test_ai_crypto_story_generated_image_prompt_constraints()
    test_stablecoin_policy_no_image_or_data_card()
    print("[test_visual_brief_mvp] ok")


if __name__ == "__main__":
    main()

