from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from llm_client import call_llm


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_debug(root: Path, name: str, content: str) -> Path:
    d = root / "logs" / "debug"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{_utc_stamp()}_{name}.txt"
    p.write_text(content or "", encoding="utf-8")
    return p


def _render_lines(lines: list[str]) -> str:
    return "\n".join([str(x) for x in lines])


def main() -> None:
    root = _project_root()

    title = "马斯克随特朗普访华，被曝未获法官批准离开OpenAI案庭审辖区"
    body = (
        "币界网消息，埃隆·马斯克本周随美国总统特朗普飞赴中国。两名知情人士透露，马斯克此次出境并未提前获得审理OpenAI案的联邦法官批准，"
        "他在该案中依然处于法庭的「随时传唤」状态。马斯克上月在加州出庭作证三天，指控OpenAI设立营利部门违背了创立初衷。4月30日他离开证人席时，"
        "法官应OpenAI律师要求，明确指示马斯克随时准备再次出庭。尽管法官当时并未下达明确的旅行禁令，但法律专家指出，证人在随时可能被传唤期间离开美国属于极其反常的行为。"
        "本周三是该案原定的最后取证日，周四将进行结案陈词。如果OpenAI、微软或法官在最后时刻决定召回马斯克，他必须在极短时间内赶回法庭。"
    )

    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        print("[single_run_v0_2] missing env: OPENROUTER_API_KEY")
        print("PowerShell（示例）：")
        print('$env:MODEL_RUNTIME="openrouter"')
        print('$env:OPENROUTER_API_KEY="你的OpenRouterKey"')
        print('$env:OPENROUTER_MODEL="anthropic/claude-sonnet-latest"')
        print("python scripts/run_single_item_v0_2.py")
        return

    os.environ["MODEL_RUNTIME"] = "openrouter"

    evaluate_prompt = (root / "prompts" / "evaluate_v0_2.md").read_text(encoding="utf-8")
    generate_prompt = (root / "prompts" / "generate_claude_v0_2.md").read_text(encoding="utf-8")
    style_rules = (root / "style" / "coinmeta_x_style_v0_2.md").read_text(encoding="utf-8")

    raw_text = f"{title}\n\n{body}"

    eval_user_payload = {
        "id": 0,
        "input_type": "coinmeta_newsflash",
        "source_tool": "coinmeta",
        "source_name": "CoinMeta 快讯",
        "source_url": "",
        "raw_text": raw_text,
        "related_coinmeta_news_url": "",
        "related_coinmeta_news_text": "",
        "news_card_image": "",
        "lang": "cn",
    }

    eval_r = call_llm(
        task_type="evaluate_hot_input",
        system_prompt=evaluate_prompt,
        user_prompt=json.dumps(eval_user_payload, ensure_ascii=False, indent=2),
        expect_json=True,
        temperature=0.2,
        max_tokens=1000,
    )

    if not eval_r.get("ok"):
        debug_path = _write_debug(root, "evaluate_raw_output", str(eval_r.get("content") or ""))
        print(f"[single_run_v0_2] evaluate_failed error={eval_r.get('error')}")
        print(f"[single_run_v0_2] raw_saved={debug_path}")
        return

    eval_json = eval_r.get("json")
    if not isinstance(eval_json, dict):
        debug_path = _write_debug(root, "evaluate_raw_output", str(eval_r.get("content") or ""))
        print("[single_run_v0_2] evaluate_failed error=evaluate_json_not_object")
        print(f"[single_run_v0_2] raw_saved={debug_path}")
        return

    print("\n=== Evaluate JSON ===")
    print(json.dumps(eval_json, ensure_ascii=False, indent=2))

    allowed = bool(eval_json.get("allowed_to_generate"))
    worth = bool(eval_json.get("worth_spending_claude"))
    if not (allowed and worth):
        print("\n[single_run_v0_2] generate_skipped")
        print(f"- allowed_to_generate={allowed}")
        print(f"- worth_spending_claude={worth}")
        print(f"- publish_mode={eval_json.get('publish_mode')}")
        print(f"- template_type={eval_json.get('template_type')}")
        return

    gen_user_payload = {
        "raw_text": raw_text,
        "input_type": "coinmeta_newsflash",
        "source_name": "CoinMeta 快讯",
        "related_coinmeta_news_text": "",
        "evaluation_json": json.dumps(eval_json, ensure_ascii=False, sort_keys=True),
        "template_type": eval_json.get("template_type"),
        "risk_level": eval_json.get("risk_level"),
        "safe_angle": eval_json.get("safe_angle"),
        "do_not_write": eval_json.get("do_not_write"),
    }

    gen_r = call_llm(
        task_type="generate_hot_draft",
        system_prompt="\n\n".join([generate_prompt, style_rules]),
        user_prompt=json.dumps(gen_user_payload, ensure_ascii=False, indent=2),
        expect_json=True,
        temperature=0.4,
        max_tokens=1800,
    )

    if not gen_r.get("ok"):
        debug_path = _write_debug(root, "generate_raw_output", str(gen_r.get("content") or ""))
        print(f"\n[single_run_v0_2] generate_failed error={gen_r.get('error')}")
        print(f"[single_run_v0_2] raw_saved={debug_path}")
        return

    gen_json = gen_r.get("json")
    if not isinstance(gen_json, dict):
        debug_path = _write_debug(root, "generate_raw_output", str(gen_r.get("content") or ""))
        print("\n[single_run_v0_2] generate_failed error=generate_json_not_object")
        print(f"[single_run_v0_2] raw_saved={debug_path}")
        return

    main_lines = gen_json.get("main_post_cn_lines")
    first_lines = gen_json.get("first_comment_cn_lines")
    if not isinstance(main_lines, list) or not isinstance(first_lines, list):
        debug_path = _write_debug(root, "generate_raw_output", str(gen_r.get("content") or ""))
        print("\n[single_run_v0_2] generate_failed error=lines_not_arrays")
        print(f"[single_run_v0_2] raw_saved={debug_path}")
        return

    print("\n=== Generate JSON ===")
    print(json.dumps(gen_json, ensure_ascii=False, indent=2))

    print("\n=== 渲染后的中文主帖 ===")
    print(_render_lines([str(x) for x in main_lines]))

    print("\n=== 渲染后的首评 ===")
    print(_render_lines([str(x) for x in first_lines]))

    print("\n=== visual_prompt_cn ===")
    print(str(gen_json.get("visual_prompt_cn") or "").strip())

    print("\n=== risk_note ===")
    print(str(gen_json.get("risk_note") or "").strip())


if __name__ == "__main__":
    main()

