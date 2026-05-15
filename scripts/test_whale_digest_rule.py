from __future__ import annotations

from typing import Any

from rules.event_cluster import cluster_hot_inputs
from rules.hot_engine_rulebook import evaluate_event


def _mk_item(
    *,
    input_id: str,
    title: str,
    raw_text: str,
    source_name: str,
    source_url: str,
    received_at: str,
    event_fingerprint: str = "",
) -> dict[str, Any]:
    return {
        "input_id": input_id,
        "source_platform": "test",
        "source_name": source_name,
        "source_type": "internal_newsflash",
        "content_type": "text",
        "title": title,
        "short_title": "",
        "raw_text": raw_text,
        "source_url": source_url,
        "raw_title": title,
        "raw_author": source_name,
        "received_at": received_at,
        "published_at": received_at,
        "event_fingerprint": event_fingerprint,
        "pipeline_stage": "published",
        "category": "test",
    }


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    hot_inputs: list[dict[str, Any]] = []

    hot_inputs.append(
        _mk_item(
            input_id="t_a16z_hype",
            title="a16z相关钱包再买入 HYPE",
            raw_text="据链上看板显示，a16z相关钱包再次买入 HYPE，价值约 6943 万美元。链接：https://etherscan.io/tx/0x1234567890abcdef",
            source_name="internal_dashboard",
            source_url="https://etherscan.io/tx/0x1234567890abcdef",
            received_at="2026-05-14T00:10:00Z",
            event_fingerprint="a16z_hype_buy",
        )
    )

    hot_inputs.append(
        _mk_item(
            input_id="t_hype_max_long",
            title="HYPE 最大多头补保证金",
            raw_text="某高关注交易员的 HYPE 多仓出现大幅浮亏（约 1300 万美元），并补保证金。市场提示其接近清算线，但未提供清算价/地址/仓位截图。",
            source_name="tg:signal_room",
            source_url="https://t.me/example/123",
            received_at="2026-05-14T08:30:00Z",
            event_fingerprint="hype_max_long_margin",
        )
    )

    hot_inputs.append(
        _mk_item(
            input_id="t_machi_rotate",
            title="麻吉今日多次调仓",
            raw_text="麻吉今日多次调仓（HYPE/ETH），多次换手并出现补保证金动作。看板：https://dune.com/boards/machi",
            source_name="internal_dashboard",
            source_url="https://dune.com/boards/machi",
            received_at="2026-05-14T16:20:00Z",
            event_fingerprint="machi_rotate",
        )
    )

    clusters = cluster_hot_inputs(hot_inputs)
    _assert(len(clusters) == 3, f"expected 3 clusters, got {len(clusters)}")

    results: list[dict[str, Any]] = []
    for c in clusters:
        r = evaluate_event(c.__dict__)
        results.append(r)

    by_title = {str(r.get("cluster_title") or ""): r for r in results}
    r_a16z = by_title.get("a16z相关钱包再买入 HYPE")
    r_hype = by_title.get("HYPE 最大多头补保证金")
    r_machi = by_title.get("麻吉今日多次调仓")

    _assert(r_a16z is not None and r_hype is not None and r_machi is not None, "missing expected titles")

    def _print_one(label: str, r: dict[str, Any]) -> None:
        print("\n---")
        print(f"[{label}] final_queue={r.get('cluster_queue')}")
        print(f"actor_label={r.get('actor_label')}")
        print(f"asset={r.get('asset')}")
        print(f"rule_reason={r.get('rule_reason')}")
        mf = r.get("missing_facts")
        if isinstance(mf, list):
            print(f"missing_facts={mf}")
        else:
            print("missing_facts=[]")

    _print_one("a16z_hype", r_a16z)
    _print_one("hype_max_long", r_hype)
    _print_one("machi_rotate", r_machi)

    for r in (r_a16z, r_hype, r_machi):
        q = str(r.get("cluster_queue") or "")
        _assert(q not in {"reject", "monitor"}, f"unexpected queue={q} for {r.get('cluster_title')}")
        _assert(q in {"whale_digest", "source_research", "queue_review"}, f"unexpected queue={q}")

    _assert(
        str(r_machi.get("cluster_queue") or "") == "whale_digest",
        "machi must be whale_digest",
    )

    hype_q = str(r_hype.get("cluster_queue") or "")
    _assert(hype_q in {"whale_digest", "source_research"}, "hype max long without anchor must not be queue_review")

    print("\n[test_whale_digest_rule] ok")


if __name__ == "__main__":
    main()

