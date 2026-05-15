from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autopublish_guard import evaluate_autopublish


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text_if_exists(p: Path) -> str | None:
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _run_case(
    *,
    label: str,
    event_cluster: dict[str, Any],
    generated_post: dict[str, Any],
    expected_allowed: bool,
    expected_reply_allowed: bool | None = None,
    expected_action_contains: str | None = None,
    expected_block_reason_contains: str | None = None,
    forbidden_block_reason_substrings: list[str] | None = None,
    published_log: list[dict[str, Any]] | None = None,
    dryrun_log: list[dict[str, Any]] | None = None,
    include_dry_run_history: bool = False,
) -> None:
    r = evaluate_autopublish(
        generated_post=generated_post,
        event_cluster=event_cluster,
        published_log=published_log,
        dryrun_log=dryrun_log,
        include_dry_run_history=include_dry_run_history,
    )
    allowed = bool(r.get("allowed_to_autopublish"))
    reply_allowed = bool(r.get("reply_allowed", True))
    reasons = r.get("block_reasons")
    print(f"\n[{label}] allowed={allowed} score={r.get('autopublish_score')} risk={r.get('risk_level')}")
    print(f"[{label}] reply_allowed={reply_allowed} reply_skip_reason={r.get('reply_skip_reason')} adjustment_actions={r.get('adjustment_actions')}")
    print(f"[{label}] block_reasons={reasons}")
    if allowed != expected_allowed:
        raise AssertionError(f"{label}: expected_allowed={expected_allowed}, got={allowed}, reasons={reasons}")
    if expected_reply_allowed is not None and reply_allowed != expected_reply_allowed:
        raise AssertionError(f"{label}: expected_reply_allowed={expected_reply_allowed}, got={reply_allowed}")
    if expected_action_contains:
        acts = r.get("adjustment_actions") if isinstance(r.get("adjustment_actions"), list) else []
        if expected_action_contains not in [str(x) for x in acts]:
            raise AssertionError(f"{label}: expected adjustment_actions contains {expected_action_contains}, got={acts}")
    if expected_block_reason_contains:
        brs = reasons if isinstance(reasons, list) else []
        if expected_block_reason_contains not in [str(x) for x in brs]:
            raise AssertionError(f"{label}: expected block_reasons contains {expected_block_reason_contains}, got={brs}")
    if forbidden_block_reason_substrings:
        brs = reasons if isinstance(reasons, list) else []
        joined = " | ".join([str(x) for x in brs])
        for s in forbidden_block_reason_substrings:
            if s and s in joined:
                raise AssertionError(f"{label}: forbidden block reason matched: {s}, got={brs}")


def main() -> None:
    root = _project_root()
    rules_path = root / "configs" / "autopublish_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {}
    inv = rules.get("investment_advice_keywords") if isinstance(rules.get("investment_advice_keywords"), list) else []
    blk = rules.get("blocked_keywords") if isinstance(rules.get("blocked_keywords"), list) else []
    assert inv, "configs/autopublish_rules.json missing investment_advice_keywords"
    assert blk, "configs/autopublish_rules.json missing blocked_keywords"

    base_event = {
        "cluster_queue": "queue_review",
        "risk_level": "low",
        "best_source_url": "https://example.com/source",
        "source_names": ["cointelegraph"],
        "source_urls": ["https://example.com/source"],
        "cluster_title": "Sample cluster",
        "raw_summary": "Sample summary",
    }
    base_gen = {
        "main_post": "CoinMeta Hot Engine dry-run sample.",
        "first_comment": "More context in the review doc.",
        "editor_risk_note": "",
    }
    empty_log: list[dict[str, Any]] = []

    _run_case(
        label="A_low_risk_normal",
        event_cluster={**base_event, "event_cluster_id": "evt_a_001"},
        generated_post={**base_gen, "main_post": "BTC 网络手续费回落，链上活动保持平稳（有硬来源锚点）。"},
        expected_allowed=True,
        expected_reply_allowed=True,
        published_log=empty_log,
    )

    _run_case(
        label="N_main_ok_reply_too_long",
        event_cluster={
            **base_event,
            "event_cluster_id": "evt_n_001",
            "best_source_url": "https://www.coindesk.com/",
            "source_names": ["coindesk"],
        },
        generated_post={
            **base_gen,
            "main_post": "主帖合格（长度<280），且低风险、有来源锚点。",
            "first_comment": "a" * 300,
        },
        expected_allowed=True,
        expected_reply_allowed=False,
        expected_action_contains="skip_first_comment",
        published_log=empty_log,
    )

    _run_case(
        label="O_main_too_long_block",
        event_cluster={
            **base_event,
            "event_cluster_id": "evt_o_001",
            "best_source_url": "https://www.coindesk.com/",
            "source_names": ["coindesk"],
        },
        generated_post={
            **base_gen,
            "main_post": "b" * 300,
            "first_comment": "ok",
        },
        expected_allowed=False,
        expected_block_reason_contains="main_post_too_long",
        published_log=empty_log,
    )

    _run_case(
        label="L_ordinary_etf_flow_low_virality",
        event_cluster={
            **base_event,
            "event_cluster_id": "evt_l_001",
            "best_source_url": "https://www.coindesk.com/",
            "source_names": ["coindesk"],
        },
        generated_post={
            **base_gen,
            "main_post": "BTC 现货 ETF 单日流出 6.35 亿美元，来源 CoinDesk。",
        },
        expected_allowed=False,
        expected_reply_allowed=True,
        published_log=empty_log,
    )

    _run_case(
        label="M_abnormal_etf_flow_with_hook",
        event_cluster={
            **base_event,
            "event_cluster_id": "evt_m_001",
            "best_source_url": "https://www.coindesk.com/",
            "source_names": ["coindesk"],
        },
        generated_post={
            **base_gen,
            "main_post": "BTC 现货 ETF 创上市以来最大单日流出，且 BTC 同日大跌。",
        },
        expected_allowed=True,
        published_log=empty_log,
    )

    _run_case(
        label="P_negation_context_no_false_positive",
        event_cluster={
            **base_event,
            "event_cluster_id": "evt_p_001",
            "best_source_url": "https://www.coindesk.com/",
            "source_names": ["coindesk"],
            "cluster_title": "Claude 帮用户找回 BTC",
        },
        generated_post={
            **base_gen,
            "main_post": "一个人找了十年的比特币，被 Claude 帮着找回来了。Claude 做的不是破解，也不像黑客，而是帮他翻旧电脑和旧备份。",
            "first_comment": "AI 在这里更像数字侦探，不创造私钥，只帮你把旧线索找出来。",
            "editor_risk_note": "不涉及黑客攻击，不涉及监管处罚，需注意这不是破解钱包。",
        },
        expected_allowed=True,
        forbidden_block_reason_substrings=["blocked_keywords:黑客", "high_risk_topics:监管处罚", "high_risk_topics:黑客/被盗"],
        published_log=empty_log,
    )

    _run_case(
        label="B_legal_court",
        event_cluster={**base_event, "event_cluster_id": "evt_b_001"},
        generated_post={
            **base_gen,
            "main_post": "某公司被起诉，法院将审理该案；据匿名知情人士称，法官已受理。",
        },
        expected_allowed=False,
        published_log=empty_log,
    )

    _run_case(
        label="C_hack_stolen_exchange_risk",
        event_cluster={**base_event, "event_cluster_id": "evt_c_001"},
        generated_post={
            **base_gen,
            "main_post": "交易所风险上升：疑似遭黑客攻击、资金被盗，用户注意安全。",
        },
        expected_allowed=False,
        published_log=empty_log,
    )

    _run_case(
        label="D_reg_sanction_war",
        event_cluster={**base_event, "event_cluster_id": "evt_d_001"},
        generated_post={
            **base_gen,
            "main_post": "监管处罚与制裁升级，地缘战争冲突引发爆炸事件相关讨论。",
        },
        expected_allowed=False,
        published_log=empty_log,
    )

    _run_case(
        label="E_whale_missing_anchor_secondary_only",
        event_cluster={
            **base_event,
            "event_cluster_id": "evt_e_001",
            "cluster_queue": "whale_digest",
            "best_source_url": "",
            "source_urls": [],
            "source_names": ["tg:whale_alert"],
            "raw_summary": "TG/webhook 口径：某鲸鱼疑似转账，但无地址/看板/截图锚点。",
        },
        generated_post={**base_gen, "main_post": "鲸鱼转账提醒（仅二手来源描述），细节待核实。"},
        expected_allowed=False,
        published_log=empty_log,
    )

    _run_case(
        label="F_investment_advice_copytrade",
        event_cluster={**base_event, "event_cluster_id": "evt_f_001"},
        generated_post={
            **base_gen,
            "main_post": "建议买入 XXX，可以跟，抄作业，稳赚。",
        },
        expected_allowed=False,
        published_log=empty_log,
    )

    pub_path = root / "out" / "publish_logs" / "published_posts.jsonl"
    dry_path = root / "out" / "publish_logs" / "dryrun_posts.jsonl"
    old = _read_text_if_exists(pub_path)
    old_dry = _read_text_if_exists(dry_path)
    try:
        now = _utc_now_iso()
        dup_id = "evt_dup_001"
        _write_text(
            pub_path,
            json.dumps(
                {
                    "created_at": now,
                    "status": "published",
                    "queue": "queue_review",
                    "event_cluster_id": dup_id,
                },
                ensure_ascii=False,
            )
            + "\n",
        )
        _run_case(
            label="G_duplicate_event_cluster_id_24h",
            event_cluster={**base_event, "event_cluster_id": dup_id},
            generated_post={**base_gen, "main_post": "Normal post but duplicated event id in last 24h."},
            expected_allowed=False,
        )

        h_id = "evt_dry_001"
        _write_text(pub_path, "")
        _write_text(
            dry_path,
            json.dumps(
                {
                    "created_at": now,
                    "status": "would_publish",
                    "queue": "queue_review",
                    "event_cluster_id": h_id,
                    "dry_run": True,
                },
                ensure_ascii=False,
            )
            + "\n",
        )

        _run_case(
            label="H_dryrun_history_ignored_by_default",
            event_cluster={**base_event, "event_cluster_id": h_id},
            generated_post={**base_gen, "main_post": "Normal post; only dryrun history exists."},
            expected_allowed=True,
            include_dry_run_history=False,
        )

        _run_case(
            label="I_dryrun_history_counted_when_enabled",
            event_cluster={**base_event, "event_cluster_id": h_id},
            generated_post={**base_gen, "main_post": "Normal post; dryrun history should be counted."},
            expected_allowed=False,
            include_dry_run_history=True,
        )
    finally:
        if old is None:
            try:
                pub_path.unlink()
            except FileNotFoundError:
                pass
        else:
            _write_text(pub_path, old)
        if old_dry is None:
            try:
                dry_path.unlink()
            except FileNotFoundError:
                pass
        else:
            _write_text(dry_path, old_dry)

    print("\n[test_autopublish_guard] OK")


if __name__ == "__main__":
    main()

