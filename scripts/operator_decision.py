from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


Decision = dict[str, Any]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def clip(text: object, limit: int) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def normalize_text(*parts: object) -> str:
    return "\n".join(str(x or "") for x in parts).lower()


def has_any(text: str, terms: list[str]) -> bool:
    t = text.lower()
    return any(term.lower() in t for term in terms)


USER_CONNECTION_TERMS = [
    "usdc",
    "usdt",
    "stablecoin",
    "稳定币",
    "支付",
    "出金",
    "创作者",
    "钱包",
    "账户",
    "交易所",
    "提现",
    "资金安全",
    "清算",
    "爆仓",
    "手续费",
    "风险",
    "meta",
]

SHARP_OR_CONFLICT_TERMS = [
    "ef",
    "ethereum foundation",
    "以太坊基金会",
    "lubin",
    "consensys",
    "裁员",
    "高层出走",
    "权力",
    "争议",
    "危机",
    "治理",
    "利益",
    "站队",
    "被曝",
    "知情人士",
]

LOW_FIT_TERMS = [
    "普通公告",
    "参数调整",
    "维护",
    "上线",
    "融资",
    "研报",
    "研究员",
    "报告称",
]

DATA_TERMS = [
    "etf",
    "净流入",
    "净流出",
    "资金流",
    "巨鲸",
    "链上",
    "清算",
    "地址",
    "0x",
]


def index_generated_posts(root: Path) -> dict[str, dict[str, Any]]:
    """Index generated post artifacts by event_cluster_id.

    This is intentionally best-effort. The operator layer should still work when
    generated drafts are absent, because运营决策不能被草稿文件缺失阻塞。
    """

    indexed: dict[str, dict[str, Any]] = {}
    raw_dir = root / "out" / "generated_posts" / "raw_json"
    if not raw_dir.exists():
        return indexed

    for fp in sorted(raw_dir.glob("*.json")):
        obj = read_json(fp)
        event_id = str(obj.get("event_cluster_id") or "").strip()
        if not event_id:
            continue
        indexed[event_id] = obj
    return indexed


def load_v2_008_queue(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "reports" / "x_v2_008_chinese_sharp_test_account_queue.json"
    obj = read_json(path)
    rows = obj.get("READY_FOR_TEST_ACCOUNT")
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        event_id = str(row.get("event_id") or "").strip()
        if event_id:
            out[event_id] = row
    return out


def load_events(root: Path) -> list[dict[str, Any]]:
    events_path = root / "out" / "hot_engine_queues" / "events.jsonl"
    events = read_jsonl(events_path)
    if events:
        return events

    # Fallback: use the latest manually-audited queue so the operator layer can
    # still demonstrate real operating decisions in a freshly cloned repo.
    queue = load_v2_008_queue(root)
    fallback_events: list[dict[str, Any]] = []
    for event_id, row in queue.items():
        title = str(row.get("title") or "")
        text = " ".join(
            [
                title,
                str(row.get("original_post") or ""),
                str(row.get("personal_sharp") or ""),
                str(row.get("personal_balanced") or ""),
            ]
        )
        is_eth_governance = has_any(text, SHARP_OR_CONFLICT_TERMS)
        fallback_events.append(
            {
                "event_cluster_id": event_id,
                "cluster_title": title,
                "cluster_queue": "queue_review",
                "topic_priority": "P0" if is_eth_governance else "P1",
                "audience_reach_score": int(row.get("audience_context_score") or 70) * 10
                if int(row.get("audience_context_score") or 0) <= 10
                else int(row.get("audience_context_score") or 70),
                "source_score": 85,
                "fact_score": 85,
                "total_score": int(row.get("x_taste_score") or 75),
                "best_source_rank": 2,
                "risk_level": str(row.get("risk_level") or "low"),
                "missing_facts": [],
                "raw_summary": text,
                "source_urls": [str(row.get("source_url") or "").strip()]
                if str(row.get("source_url") or "").strip()
                else [],
                "source_names": ["v2_008_queue"],
                "rule_reason": "fallback_from_x_v2_008_audited_queue",
            }
        )
    return fallback_events


def best_generated_text(generated: dict[str, Any], queue_item: dict[str, Any]) -> tuple[str, str]:
    gen_json = generated.get("generated_json")
    if not isinstance(gen_json, dict):
        gen_json = {}

    main = (
        gen_json.get("main_post")
        or gen_json.get("main_post_cn")
        or queue_item.get("personal_balanced")
        or queue_item.get("personal_sharp")
        or queue_item.get("original_post")
        or ""
    )
    first_comment = gen_json.get("first_comment") or gen_json.get("first_comment_cn") or ""

    reply_hot_take = queue_item.get("reply_hot_take")
    if not first_comment and isinstance(reply_hot_take, dict):
        first_comment = (
            reply_hot_take.get("sharp_but_safe")
            or reply_hot_take.get("og_explainer")
            or reply_hot_take.get("sarcastic")
            or ""
        )

    return str(main or "").strip(), str(first_comment or "").strip()


def fallback_main_post(title: str, text: str, account_fit: str) -> str:
    if account_fit == "official_post":
        if has_any(text, ["stablecoin", "稳定币", "usdc", "支付", "meta"]):
            return "稳定币走出交易场景以后，真正的问题不是到账，而是怎么花、怎么换、怎么合规使用。"
        if has_any(text, ["巨鲸", "链上", "清算"]):
            return "这类链上异动不能只看金额，关键是它有没有变成市场风险信号。"
        return f"{clip(title, 56)}\n\n这条更适合从用户影响和后续观察点切入，而不是复读快讯标题。"
    if account_fit == "reply_or_quote":
        return f"{clip(title, 70)}\n\n适合做引用或评论：抓住一个冲突点，但不要把推断写成事实。"
    if account_fit == "editor_take":
        return f"{clip(title, 70)}\n\n这条有观点空间，但更像编辑锐评，不建议默认放到 CoinMeta 官号主帖。"
    return ""


def decide_one(event: dict[str, Any], generated: dict[str, Any], queue_item: dict[str, Any]) -> Decision:
    event_id = str(event.get("event_cluster_id") or queue_item.get("event_id") or "").strip()
    title = str(event.get("cluster_title") or queue_item.get("title") or "").strip()
    raw_summary = str(event.get("raw_summary") or queue_item.get("original_post") or "").strip()
    text = normalize_text(title, raw_summary, queue_item.get("personal_sharp"), queue_item.get("personal_balanced"))

    cluster_queue = str(event.get("cluster_queue") or "").strip()
    risk_level = str(event.get("risk_level") or queue_item.get("risk_level") or "medium").strip() or "medium"
    missing_facts = event.get("missing_facts")
    if not isinstance(missing_facts, list):
        missing_facts = []

    best_source_rank = int(event.get("best_source_rank") or 9)
    fact_score = int(event.get("fact_score") or 0)
    audience = int(event.get("audience_reach_score") or 0)
    total_score = int(event.get("total_score") or 0)

    has_user_connection = has_any(text, USER_CONNECTION_TERMS)
    sharp_or_conflict = has_any(text, SHARP_OR_CONFLICT_TERMS)
    low_fit = has_any(text, LOW_FIT_TERMS) and not has_user_connection
    data_or_whale = has_any(text, DATA_TERMS)

    decision = "monitor"
    account_fit = "monitor_only"
    reason = "信息有一定价值，但还没有达到当天自动运营推荐阈值。"

    if cluster_queue == "reject" or low_fit:
        decision = "reject"
        account_fit = "monitor_only"
        reason = "普通公告/弱用户连接/低传播价值，不适合作为 CoinMeta X 当日运营内容。"
    elif risk_level == "high" or missing_facts or best_source_rank >= 4 or fact_score < 70:
        decision = "monitor"
        account_fit = "monitor_only"
        reason = "事实锚点或风险边界不足，先补来源，不进入自动运营主帖。"
    elif sharp_or_conflict:
        decision = "quote"
        account_fit = "reply_or_quote"
        reason = "有冲突和讨论价值，但容易带主观判断，适合引用/评论或编辑锐评，不默认进官号主帖。"
    elif cluster_queue == "whale_digest":
        decision = "reply"
        account_fit = "reply_or_quote"
        reason = "链上/巨鲸信息适合做评论区承接或每日汇总，除非金额极大且有清算风险，否则不默认单条硬推。"
    elif cluster_queue == "queue_review" and has_user_connection and audience >= 65 and total_score >= 70:
        decision = "post"
        account_fit = "official_post"
        reason = "具备事实锚点、普通用户连接点和 X 传播钩子，适合 CoinMeta 官号主帖。"
    elif cluster_queue in {"queue_review", "enriched_queue_review"} and data_or_whale:
        decision = "reply"
        account_fit = "reply_or_quote"
        reason = "有数据/链上信号，但更适合用作补充评论或观察点，不一定值得官号主帖。"
    elif cluster_queue == "source_research":
        decision = "monitor"
        account_fit = "monitor_only"
        reason = "题材可能值得跟，但当前需要先补一手来源和事实包。"

    main, first_comment = best_generated_text(generated, queue_item)
    if decision in {"monitor", "reject"}:
        recommended_main_post = ""
        recommended_first_comment = ""
    else:
        recommended_main_post = main or fallback_main_post(title, text, account_fit)
        recommended_first_comment = first_comment
        if not recommended_first_comment and account_fit == "official_post":
            recommended_first_comment = "首评补一个后续观察点：这件事接下来要看使用场景、资金流向和平台实际动作是否同步。"

    if account_fit == "official_post":
        user_hook = clip(recommended_main_post.splitlines()[0] if recommended_main_post else title, 90)
    elif account_fit == "reply_or_quote":
        user_hook = "适合抓一个冲突点做引用/评论，但不要把推断写成事实。"
    else:
        user_hook = ""

    if risk_level == "high":
        risk_boundary = "不可自动发布；必须补官方/链上/权威来源，只能写已知事实。"
    elif missing_facts:
        risk_boundary = "先补事实锚点：" + "；".join(str(x) for x in missing_facts[:3])
    elif account_fit == "reply_or_quote":
        risk_boundary = "避免阴谋化、攻击性定性和利益输送暗示；保留不确定性。"
    elif account_fit == "official_post":
        risk_boundary = "不喊单、不预测价格、不把相关性写成因果。"
    else:
        risk_boundary = "不进入发布动作。"

    if decision == "post":
        publish_window = "12:00-14:00 或 20:00-22:00，优先等人工确认最终文本"
    elif decision in {"quote", "reply"}:
        publish_window = "热点原帖出现后 30-90 分钟内，作为引用/评论承接"
    else:
        publish_window = "不排期"

    if has_any(text, ["稳定币", "stablecoin", "usdc", "支付", "出金"]):
        expected_metric = "bookmark_or_reply"
        feedback_tag = "stablecoin_real_use"
    elif sharp_or_conflict:
        expected_metric = "reply"
        feedback_tag = "governance_conflict"
    elif data_or_whale:
        expected_metric = "bookmark"
        feedback_tag = "data_or_whale_watch"
    elif decision == "reject":
        expected_metric = "none"
        feedback_tag = "reject_low_fit"
    else:
        expected_metric = "impression"
        feedback_tag = "monitor_watch"

    return {
        "event_id": event_id,
        "title": title,
        "decision": decision,
        "account_fit": account_fit,
        "reason": reason,
        "user_hook": user_hook,
        "recommended_main_post": clip(recommended_main_post, 420),
        "recommended_first_comment": clip(recommended_first_comment, 260),
        "recommended_quote_angle": "用一句话指出冲突点，再补事实边界。" if decision == "quote" else "",
        "risk_boundary": risk_boundary,
        "publish_window": publish_window,
        "expected_metric": expected_metric,
        "feedback_tag": feedback_tag,
        "scores": {
            "audience_reach_score": audience,
            "fact_score": fact_score,
            "total_score": total_score,
            "best_source_rank": best_source_rank,
            "risk_level": risk_level,
        },
        "source_urls": event.get("source_urls") or ([queue_item.get("source_url")] if queue_item.get("source_url") else []),
    }


def build_operator_decisions(root: Path | None = None, limit: int = 10) -> dict[str, Any]:
    root = root or project_root()
    events = load_events(root)
    generated_index = index_generated_posts(root)
    queue_index = load_v2_008_queue(root)

    decisions: list[Decision] = []
    for event in events[: max(0, int(limit))]:
        event_id = str(event.get("event_cluster_id") or "").strip()
        decisions.append(
            decide_one(
                event=event,
                generated=generated_index.get(event_id, {}),
                queue_item=queue_index.get(event_id, {}),
            )
        )

    counts = Counter(str(x.get("decision") or "unknown") for x in decisions)
    fit_counts = Counter(str(x.get("account_fit") or "unknown") for x in decisions)

    return {
        "version": "x_operator_decision_v0.2",
        "generated_at_utc": utc_now_iso(),
        "input_events": len(events),
        "decision_count": len(decisions),
        "decision_counts": dict(sorted(counts.items())),
        "account_fit_counts": dict(sorted(fit_counts.items())),
        "decisions": decisions,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
            "daemon_started": False,
            "credential_exposed": False,
            "model_called": False,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []

    def section(title: str, predicate) -> list[str]:
        rows = [d for d in decisions if predicate(d)]
        lines = [f"\n## {title}\n"]
        if not rows:
            lines.append("- 暂无。\n")
            return lines
        for i, d in enumerate(rows, start=1):
            lines.append(f"\n### {i}. {d.get('title') or d.get('event_id')}\n")
            lines.append(f"- decision: `{d.get('decision')}`\n")
            lines.append(f"- account_fit: `{d.get('account_fit')}`\n")
            lines.append(f"- reason: {d.get('reason')}\n")
            if d.get("user_hook"):
                lines.append(f"- user_hook: {d.get('user_hook')}\n")
            if d.get("recommended_main_post"):
                lines.append("\n**推荐主帖**\n\n")
                lines.append(str(d.get("recommended_main_post")).strip() + "\n")
            if d.get("recommended_first_comment"):
                lines.append("\n**首评/承接**\n\n")
                lines.append(str(d.get("recommended_first_comment")).strip() + "\n")
            if d.get("recommended_quote_angle"):
                lines.append(f"- quote_angle: {d.get('recommended_quote_angle')}\n")
            lines.append(f"- risk_boundary: {d.get('risk_boundary')}\n")
            lines.append(f"- publish_window: {d.get('publish_window')}\n")
            lines.append(f"- expected_metric: `{d.get('expected_metric')}`\n")
            lines.append(f"- feedback_tag: `{d.get('feedback_tag')}`\n")
        return lines

    lines: list[str] = []
    lines.append("# CoinMeta X Operator Today Decision\n\n")
    lines.append(f"- version: `{payload.get('version')}`\n")
    lines.append(f"- generated_at_utc: {payload.get('generated_at_utc')}\n")
    lines.append(f"- input_events: {payload.get('input_events')}\n")
    lines.append(f"- decision_count: {payload.get('decision_count')}\n")
    lines.append(f"- decision_counts: `{json.dumps(payload.get('decision_counts') or {}, ensure_ascii=False)}`\n")
    lines.append(f"- account_fit_counts: `{json.dumps(payload.get('account_fit_counts') or {}, ensure_ascii=False)}`\n")
    lines.append("\n> 目标：先做运营判断，再做内容生成。安全闸门仍在，但不再让安全报告替代运营价值。\n")

    lines.extend(section("官号主帖候选", lambda d: d.get("account_fit") == "official_post"))
    lines.extend(section("引用 / 评论承接候选", lambda d: d.get("account_fit") == "reply_or_quote"))
    lines.extend(section("仅监控 / 拒绝", lambda d: d.get("decision") in {"monitor", "reject"}))

    lines.append("\n## Safety\n")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ["x_published", "x_api_connected", "production_write", "daemon_started", "credential_exposed", "model_called"]:
        lines.append(f"- {key}: `{str(bool(safety.get(key))).lower()}`\n")
    return "".join(lines)


def write_outputs(payload: dict[str, Any], root: Path | None = None) -> tuple[Path, Path]:
    root = root or project_root()
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "operator_today_decision.json"
    md_path = reports / "operator_today_decision.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CoinMeta X operator decision report.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    payload = build_operator_decisions(limit=args.limit)
    json_path, md_path = write_outputs(payload)
    print(
        "[operator_decision] ok"
        f" decisions={payload.get('decision_count')}"
        f" json={json_path}"
        f" md={md_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
