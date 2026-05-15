from __future__ import annotations

import os

from llm_client import call_llm


def _print_result(label: str, res: dict) -> None:
    ok = res.get("ok")
    runtime = res.get("runtime")
    model = res.get("model")
    err = res.get("error")
    print(f"[{label}] ok={ok} runtime={runtime} model={model} error={err}")


def _content_preview(res: dict, n: int = 240) -> str:
    c = str(res.get("content") or "").replace("\r\n", "\n").strip()
    if len(c) <= n:
        return c
    return c[:n] + "…"


def main() -> None:
    runtime = (os.getenv("MODEL_RUNTIME") or "mock").strip().lower()
    print(f"[legacy_test_llm_client_old] MODEL_RUNTIME={runtime}")

    if runtime == "mock":
        r1 = call_llm(
            task_type="evaluate_hot_input",
            system_prompt="(test)",
            user_prompt='{"input_type":"coinmeta_newsflash","raw_text":"测试快讯卡"}',
            expect_json=True,
        )
        _print_result("evaluate_hot_input", r1)

        r2 = call_llm(
            task_type="generate_hot_draft",
            system_prompt="(test)",
            user_prompt='{"template_type":"news_card_take","raw_text":"测试快讯卡"}',
            expect_json=True,
        )
        _print_result("generate_hot_draft", r2)
        print("[legacy_test_llm_client_old] mock ok")
        return

    if runtime == "openrouter":
        r = call_llm(
            task_type="test_openrouter_json",
            system_prompt="你是一个严格的 JSON API。只能输出 JSON，不要输出解释，不要输出 markdown。",
            user_prompt='请返回 {"status":"ok","message":"openrouter connected"}，只能返回 JSON。',
            expect_json=True,
        )
        _print_result("openrouter", r)
        if r.get("ok") is True:
            print(f"[openrouter] json={r.get('json')}")
        else:
            preview = _content_preview(r)
            if preview:
                print(f"[openrouter] content_preview={preview}")
            if r.get("error") == "OPENROUTER_API_KEY is missing":
                print("[legacy_test_llm_client_old] OPENROUTER_API_KEY 未设置：已按预期返回，不报崩")
        return

    print("[legacy_test_llm_client_old] unknown MODEL_RUNTIME, nothing to do")


if __name__ == "__main__":
    main()

