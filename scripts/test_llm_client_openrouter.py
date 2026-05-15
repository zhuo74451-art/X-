from __future__ import annotations

import json
import os

from llm_client import call_llm


def main() -> None:
    runtime = (os.getenv("MODEL_RUNTIME") or "").strip().lower()
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    model = (os.getenv("OPENROUTER_MODEL") or "").strip()

    if runtime != "openrouter":
        print("[test_llm_client_openrouter] 跳过：需要设置 $env:MODEL_RUNTIME=\"openrouter\"")
        raise SystemExit(0)
    if not api_key:
        print("[test_llm_client_openrouter] 跳过：缺少 OPENROUTER_API_KEY（请在 PowerShell 当前窗口设置）")
        raise SystemExit(0)
    if not model:
        print("[test_llm_client_openrouter] 提示：未设置 OPENROUTER_MODEL，将使用默认 anthropic/claude-sonnet-4.6")

    actor_daily_pack = {
        "column_name": "今天巨鲸在干嘛",
        "time_window": "2026-05-14 00:00-24:00 UTC",
        "generated_at": "2026-05-14T08:00:00Z",
        "actors": [
            {
                "actor_label": "HYPE 大多头",
                "actor_type": "whale",
                "why_selected": "仓位大且风险变化明显",
                "actions_count": 3,
                "main_assets": ["HYPE"],
                "net_direction": "add_leverage",
                "net_amount_usd": 0,
                "realized_pnl_usd": 0,
                "unrealized_pnl_change_usd": -13000000,
                "risk_change": "higher",
                "summary_line": "回撤扩大后出现补保证金动作，风险线在变紧",
                "notable_actions": ["回撤扩大", "补保证金"],
                "source_links": ["https://example.com/tg/post/123"],
                "confidence": "medium",
                "do_not_claim": ["不要写成确定爆仓", "不要写成投资建议"]
            }
        ],
    }

    r = call_llm(skill_name="coinmeta_whale_digest", input_pack=actor_daily_pack, prompt_version="v0.1")
    print("[test_llm_client_openrouter] ok=", r.get("ok"), "runtime=", r.get("runtime"), "model=", r.get("model"))
    if not r.get("ok"):
        print("[test_llm_client_openrouter] error=", r.get("error"))
        print("[test_llm_client_openrouter] raw_output_path=", r.get("raw_output_path"))
        raise SystemExit(2)
    print(json.dumps(r.get("output") or {}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

