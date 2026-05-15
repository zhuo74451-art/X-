from __future__ import annotations

import json
import os

from llm_client import call_llm


def main() -> None:
    runtime = (os.getenv("MODEL_RUNTIME") or "mock").strip().lower()
    if runtime != "mock":
        print(f"[test_llm_client_mock] 要求 MODEL_RUNTIME=mock，当前={runtime}")
        raise SystemExit(2)

    actor_daily_pack = {
        "column_name": "今天巨鲸在干嘛",
        "time_window": "2026-05-14 00:00-24:00 UTC",
        "generated_at": "2026-05-14T08:00:00Z",
        "actors": [
            {
                "actor_label": "a16z相关钱包",
                "actor_type": "institution_related",
                "why_selected": "净买入显著且与热门资产相关，具有栏目价值",
                "actions_count": 4,
                "main_assets": ["HYPE"],
                "net_direction": "net_buy",
                "net_amount_usd": 69430000,
                "realized_pnl_usd": 0,
                "unrealized_pnl_change_usd": -6000000,
                "risk_change": "higher",
                "summary_line": "加仓持续，但回撤扩大，风险边界变窄",
                "notable_actions": [
                    "再次买入并抬高净敞口",
                    "浮亏扩大"
                ],
                "source_links": ["https://example.com/dashboard/a16z_wallet"],
                "confidence": "medium",
                "do_not_claim": ["不要写成确定内幕或确定方向", "不要写成建议跟单"]
            }
        ],
    }

    r = call_llm(skill_name="coinmeta_whale_digest", input_pack=actor_daily_pack, prompt_version="v0.1")
    print("[test_llm_client_mock] ok=", r.get("ok"), "runtime=", r.get("runtime"), "model=", r.get("model"))
    print(json.dumps(r.get("output") or {}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

