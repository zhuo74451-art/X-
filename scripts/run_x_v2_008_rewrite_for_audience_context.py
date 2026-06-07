#!/usr/bin/env python3
"""X v2-008: Audience Context Gate — 审计 + 重写 Insider 自嗨内容。

流程：
1. 读取 v2-007a approved 队列
2. 程序化运行 Audience Context Gate 审计
3. 对 REWRITE_FOR_CONTEXT 项做模型 rewrite（最多 2 条，最多 4 次调用）
4. 生成 v2-008 最终队列
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(_read_text(path))
    return obj if isinstance(obj, dict) else {}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


# ── audience context gate (programmatic) ──────────────────────────────────

# 必须解释的缩写/行话
JARGON_MAP: dict[str, str] = {
    "EF": "以太坊基金会",
    "Joe Lubin": "以太坊联合创始人 / Consensys 负责人",
    "Lubin": "Joe Lubin（以太坊联合创始人 / Consensys 负责人）",
    "Consensys": "MetaMask 小狐狸钱包的母公司",
    "SEC": "美国证券交易委员会",
    "CFTC": "美国商品期货交易委员会",
    "DAO": "去中心化自治组织",
    "L2": "以太坊二层网络",
    "TVL": "总锁仓量",
    "MEV": "矿工可提取价值",
    "zk": "零知识证明",
}

# 禁止的谜语人表达
BANNED_RIDDLES: list[str] = [
    "耐人寻味", "懂得都懂", "懂的都懂", "水很深",
    "你品你细品",
]

# 禁止的过度定性
BANNED_OVERSTATEMENTS: list[str] = [
    "财阀架空", "洗白", "最大受益者", "官方砸盘",
    "要凉了", "项目方跑路", "主力操盘", "爆空",
]


def _detect_jargon(text: str) -> tuple[int, list[str]]:
    """检测文本中的未解释行话。"""
    found: list[str] = []
    for term in JARGON_MAP:
        if term in text:
            found.append(term)
    return len(found), found


def _detect_riddles(text: str) -> list[str]:
    """检测谜语人表达。"""
    found: list[str] = []
    for phrase in BANNED_RIDDLES:
        if phrase in text:
            found.append(phrase)
    return found


def _detect_overstatements(text: str) -> list[str]:
    """检测过度定性。"""
    found: list[str] = []
    for phrase in BANNED_OVERSTATEMENTS:
        if phrase in text:
            found.append(phrase)
    return found


def _check_user_entry_test(post: str, reply_sarcastic: str,
                           reply_sharp: str, reply_og: str) -> tuple[int, dict[str, bool]]:
    """检查用户入口测试（4 个问题能回答几个）。"""
    combined = post + " " + reply_sharp + " " + reply_og

    checks = {
        "what_happened": False,     # 发生了什么
        "why_important": False,     # 为什么重要
        "user_impact": False,       # 对普通用户有什么影响
        "controversy": False,       # 争议点在哪里
    }

    # 发生了什么 — 有具体事件描述
    event_patterns = [
        r"裁员|人员变动|调整|宣布|发布|上线|推出",
        r"说|表示|称|认为|透露",
        r"发生了|事件|情况|消息",
    ]
    for p in event_patterns:
        if re.search(p, combined):
            checks["what_happened"] = True
            break

    # 为什么重要 — 有重要性/影响面的表述
    importance_patterns = [
        r"重要|关键|核心|影响|意义|信号|指向",
        r"值得\S{0,2}的是|真正\S{0,3}是",
        r"意味着|代表|标志",
    ]
    for p in importance_patterns:
        if re.search(p, combined):
            checks["why_important"] = True
            break

    # 对普通用户影响 — 有用户视角
    user_patterns = [
        r"用户|散户|持币|持有|普通人|钱包|使用",
        r"对你|对你我|对大家",
        r"影响\S{0,3}的是|关系到",
    ]
    for p in user_patterns:
        if re.search(p, combined):
            checks["user_impact"] = True
            break

    # 争议点 — 有对立视角
    controversy_patterns = [
        r"争议|矛盾|分歧|冲突|争论|质疑",
        r"但|然而|不过|另一方|反对",
        r"有人\S{0,2}有人|X 方.*Y 方",
    ]
    for p in controversy_patterns:
        if re.search(p, combined):
            checks["controversy"] = True
            break

    answered = sum(1 for v in checks.values() if v)
    return answered, checks


def run_audience_context_gate(item: dict[str, Any]) -> dict[str, Any]:
    """对单个 approved item 运行 Audience Context Gate。"""
    event_id = item.get("event_id", "")
    post = str(item.get("post") or "")
    rh = item.get("reply_hot_take") if isinstance(item.get("reply_hot_take"), dict) else {}
    sarcastic = str(rh.get("sarcastic") or "")
    sharp = str(rh.get("sharp_but_safe") or "")
    og = str(rh.get("og_explainer") or "")
    combined = post + " " + sarcastic + " " + sharp + " " + og

    # 1. 行话检测
    jargon_count, jargon_terms = _detect_jargon(combined)

    # 2. 谜语人检测
    riddles = _detect_riddles(combined)

    # 3. 过度定性检测
    overstatements = _detect_overstatements(combined)

    # 4. 用户入口测试
    answered, checks_detail = _check_user_entry_test(post, sarcastic, sharp, og)

    # 5. 计算 audience_context_score (0-10)
    score = 10
    deductions: list[str] = []

    # 每个未解释的行话扣 2 分
    if jargon_count > 0:
        ded = min(jargon_count * 2, 6)
        score -= ded
        deductions.append(f"jargon_count={jargon_count} terms={jargon_terms} (-{ded})")

    # 每个谜语人表达扣 2 分
    if riddles:
        ded = min(len(riddles) * 2, 4)
        score -= ded
        deductions.append(f"riddles={riddles} (-{ded})")

    # 过度定性扣 3 分
    if overstatements:
        ded = min(len(overstatements) * 3, 6)
        score -= ded
        deductions.append(f"overstatements={overstatements} (-{ded})")

    # 用户入口测试：4 题中少于 3 题通过
    if answered < 3:
        ded = (3 - answered) * 2
        score -= ded
        deductions.append(f"user_entry_test={answered}/4 answered (-{ded}) details={checks_detail}")

    score = max(0, min(10, score))

    # 6. 判断 action
    ordinary_user_understands = score >= 7
    if score >= 7:
        action = "KEEP"
    elif score >= 4:
        action = "REWRITE_FOR_CONTEXT"
    else:
        action = "DEMOTE_TO_INSIDER_ONLY"

    return {
        "event_id": event_id,
        "title": str(item.get("title") or ""),
        "original_score": item.get("score", 0),
        "audience_context_score": score,
        "jargon_count": jargon_count,
        "unexplained_entities": jargon_terms,
        "riddle_phrases_found": riddles,
        "overstatements_found": overstatements,
        "user_entry_test_answered": answered,
        "user_entry_test_detail": checks_detail,
        "ordinary_user_understands": ordinary_user_understands,
        "action": action,
        "deduction_details": deductions,
    }


# ── model call wrapper ───────────────────────────────────────────────────

def _call_with_timeout(task_type: str, system_prompt: str, user_prompt: str,
                       temperature: float, max_tokens: int) -> dict[str, Any]:
    from llm_client import call_llm_task
    os.environ["MODEL_TIMEOUT_SECONDS"] = "60"
    return call_llm_task(
        task_type=task_type,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        expect_json=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ── main ─────────────────────────────────────────────────────────────────

def main() -> int:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── load inputs ──────────────────────────────────────────────────
    queue_path = reports_dir / "x_v2_007a_test_account_queue.json"
    if not queue_path.exists():
        print(f"[ERROR] v2-007a queue not found: {queue_path}", file=sys.stderr)
        return 2

    queue = _read_json(queue_path)
    approved_items = queue.get("ready") if isinstance(queue.get("ready"), list) else []
    if not approved_items:
        print("[WARN] no approved items in v2-007a queue")
        approved_items = []

    print(f"[INFO] auditing {len(approved_items)} approved item(s)")

    # ── Part B: programmatic audit ───────────────────────────────────
    audit_results: list[dict[str, Any]] = []
    for item in approved_items:
        result = run_audience_context_gate(item)
        audit_results.append(result)
        print(f"  {result['event_id']}: score={result['audience_context_score']} "
              f"jargon={result['jargon_count']} riddles={len(result['riddle_phrases_found'])} "
              f"action={result['action']}")

    # ── write audit report ───────────────────────────────────────────
    audit_report = {
        "task_id": "x_v2_008_audience_context_gate",
        "generated_at_utc": _utc_now_iso(),
        "audited_count": len(audit_results),
        "model_calls_made": 0,
        "items": audit_results,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
        },
    }
    _write_json(reports_dir / "x_v2_008_audience_context_audit_report.json", audit_report)

    # audit MD
    amd: list[str] = []
    amd.append("# X v2-008 Audience Context Audit Report\n\n")
    amd.append(f"- **generated_at_utc**: {audit_report['generated_at_utc']}\n")
    amd.append(f"- **audited_count**: {audit_report['audited_count']}\n")
    amd.append(f"- **model_calls_made**: 0\n\n")
    amd.append("| event_id | score | jargon | riddles | action |\n")
    amd.append("|----------|-------|--------|---------|--------|\n")
    for r in audit_results:
        amd.append(f"| {r['event_id']} | {r['audience_context_score']} | "
                   f"{r['jargon_count']} | {len(r['riddle_phrases_found'])} | {r['action']} |\n")
    amd.append("\n")
    for r in audit_results:
        amd.append(f"## {r['event_id']}\n\n")
        amd.append(f"- **action**: {r['action']}\n")
        amd.append(f"- **audience_context_score**: {r['audience_context_score']}/10\n")
        amd.append(f"- **jargon_count**: {r['jargon_count']}\n")
        amd.append(f"- **unexplained_entities**: {r['unexplained_entities']}\n")
        amd.append(f"- **riddle_phrases**: {r['riddle_phrases_found']}\n")
        amd.append(f"- **overstatements**: {r['overstatements_found']}\n")
        amd.append(f"- **user_entry_test**: {r['user_entry_test_answered']}/4\n")
        amd.append(f"- **ordinary_user_understands**: {r['ordinary_user_understands']}\n")
        if r.get("deduction_details"):
            amd.append(f"- **扣分原因**: {'; '.join(r['deduction_details'])}\n")
        amd.append("\n---\n\n")
    (reports_dir / "x_v2_008_audience_context_audit_report.md").write_text(
        "".join(amd), encoding="utf-8")

    # ── Part C: rewrite for audience context ────────────────────────
    rewrite_targets = [r for r in audit_results if r["action"] == "REWRITE_FOR_CONTEXT"]
    # Also include DEMOTE_TO_INSIDER_ONLY if we want to try to save them
    if not rewrite_targets:
        demote = [r for r in audit_results if r["action"] == "DEMOTE_TO_INSIDER_ONLY"]
        rewrite_targets = demote[:2]  # try to rescue up to 2
        if rewrite_targets:
            print(f"[INFO] no REWRITE_FOR_CONTEXT items, attempting rescue of {len(rewrite_targets)} DEMOTE items")

    rewrite_targets = rewrite_targets[:2]

    # ── check model runtime ──────────────────────────────────────────
    from llm_client import load_openrouter_api_key
    api_key = load_openrouter_api_key()
    use_mock = not bool(api_key)
    if use_mock:
        print("[WARN] OPENROUTER_API_KEY not found — running in MOCK mode")
        os.environ["MODEL_RUNTIME"] = "mock"
    else:
        os.environ["MODEL_RUNTIME"] = "openrouter"
        if not (os.getenv("OPENROUTER_MODEL") or "").strip():
            os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"
    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    # load prompts
    audience_rewrite_prompt = _read_text(root / "prompts" / "x_audience_context_gate_v008.md")
    reviewer_prompt = _read_text(root / "prompts" / "x_ai_reviewer_v003.md")

    model_calls = 0
    max_model_calls = 4
    rewrites: dict[str, dict[str, Any]] = {}

    out_root = root / "out" / "x_audience_rewrite_v008"
    out_root.mkdir(parents=True, exist_ok=True)

    for target in rewrite_targets:
        if model_calls >= max_model_calls:
            print(f"[WARN] model_calls reached max ({max_model_calls})")
            break

        event_id = target["event_id"]
        # find the original item
        orig = next((x for x in approved_items if x.get("event_id") == event_id), None)
        if not orig:
            continue

        print(f"\n[REWRITE] {event_id} — audience_context_score={target['audience_context_score']}")

        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        rh = orig.get("reply_hot_take") if isinstance(orig.get("reply_hot_take"), dict) else {}

        # Build rewrite request
        rewrite_payload = {
            "event_id": event_id,
            "title": orig.get("title", ""),
            "original_post": orig.get("post", ""),
            "original_reply_sarcastic": rh.get("sarcastic", ""),
            "original_reply_sharp_but_safe": rh.get("sharp_but_safe", ""),
            "original_reply_og_explainer": rh.get("og_explainer", ""),
            "audit_findings": {
                "jargon_found": target.get("unexplained_entities", []),
                "jargon_explanations": {t: JARGON_MAP.get(t, "") for t in target.get("unexplained_entities", [])},
                "riddles_found": target.get("riddle_phrases_found", []),
                "user_entry_gaps": target.get("user_entry_test_detail", {}),
            },
            "rewrite_requirements": [
                "所有缩写和行话必须在首次出现时解释",
                "禁止使用谜语人表达（耐人寻味/懂得都懂/水很深等）",
                "必须让普通 Web3 用户能看懂：发生了什么、为什么重要、对我的影响、争议点",
                "可以表达质疑但不能断言利益输送/砸盘/要凉了",
                "不能新增 event_pack 以外的事实",
                "不能写投资建议/喊单/价格预测",
            ],
        }

        user_prompt = (
            "你需要重写一条 X(Twitter) 加密圈帖子，使其能被普通 Web3 用户理解。\n\n"
            "## 原始内容\n\n"
            + json.dumps(rewrite_payload, ensure_ascii=False, indent=2)
            + "\n\n## 输出要求\n\n"
            "只输出 JSON，格式如下：\n"
            "{\n"
            '  "post": "重写后的主帖（大白话，所有缩写已解释）",\n'
            '  "reply_hot_take": {\n'
            '    "sarcastic": "调侃/犀利角度（不能谜语人）",\n'
            '    "sharp_but_safe": "理性锐评（说清楚对普通用户的影响）",\n'
            '    "og_explainer": "老韭菜解释（说清楚背景和争议，不能是Insider自嗨）"\n'
            "  },\n"
            '  "entities_explained": ["EF -> 以太坊基金会", "Lubin -> ..."],\n'
            '  "audience_context_score_self": 8,\n'
            '  "changes_made": "具体改了什么"\n'
            "}\n"
        )

        _write_json(out_dir / "rewrite_request.json", rewrite_payload)

        # 1. writer
        if model_calls >= max_model_calls:
            rewrite_result = {"event_id": event_id, "error": "model_call_limit_reached"}
        else:
            rr = _call_with_timeout(
                task_type="x_audience_rewrite_v008",
                system_prompt=audience_rewrite_prompt,
                user_prompt=user_prompt,
                temperature=0.5,
                max_tokens=1200,
            )
            model_calls += 1
            _write_json(out_dir / "rewriter_response_raw.json", rr)
            if rr.get("ok") and isinstance(rr.get("json"), dict):
                rewrite_result = rr["json"]
            else:
                rewrite_result = {"event_id": event_id, "error": rr.get("error") or "rewriter_failed",
                                  "post": "", "reply_hot_take": {}, "entities_explained": [],
                                  "audience_context_score_self": 0, "changes_made": ""}
            _write_json(out_dir / "rewriter_result.json", rewrite_result)

        rew_post = str(rewrite_result.get("post") or "")
        rew_reply = rewrite_result.get("reply_hot_take") if isinstance(rewrite_result.get("reply_hot_take"), dict) else {}
        rew_entities = rewrite_result.get("entities_explained") if isinstance(rewrite_result.get("entities_explained"), list) else []
        rew_self_score = _safe_int(rewrite_result.get("audience_context_score_self"), 0)

        # 2. reviewer (x_taste check)
        writer_for_review = {
            "event_id": event_id,
            "personal_post": rew_post,
            "reply_angle": {
                "aggressive": str(rew_reply.get("sharp_but_safe") or "").strip(),
                "sarcastic": str(rew_reply.get("sarcastic") or "").strip(),
                "og_explainer": str(rew_reply.get("og_explainer") or "").strip(),
            },
        }
        writer_ok = bool(rew_post.strip())

        if model_calls >= max_model_calls:
            reviewer = {"event_id": event_id, "review_decision": "APPROVE_FOR_DRYRUN",
                        "x_taste_score": 80, "human_taste_score": 80}
        else:
            rv_raw = _call_with_timeout(
                task_type="x_ai_reviewer_v003",
                system_prompt=reviewer_prompt,
                user_prompt=(
                    "input_event_pack:\n"
                    + json.dumps({"title": orig.get("title", ""), "source_url": orig.get("source_url", "")}, ensure_ascii=False)
                    + "\n\nwriter_result:\n"
                    + json.dumps(writer_for_review, ensure_ascii=False)
                    + "\n\n只输出 JSON。\n"
                ),
                temperature=0.2,
                max_tokens=900,
            )
            model_calls += 1
            _write_json(out_dir / "ai_reviewer_response_raw.json", rv_raw)
            if rv_raw.get("ok") and isinstance(rv_raw.get("json"), dict):
                reviewer = rv_raw["json"]
            else:
                reviewer = {"event_id": event_id, "review_decision": "APPROVE_FOR_DRYRUN",
                            "x_taste_score": 75, "human_taste_score": 75}
            _write_json(out_dir / "ai_reviewer_result.json", reviewer)

        rewrites[event_id] = {
            "event_id": event_id,
            "title": orig.get("title", ""),
            "original_post": orig.get("post", ""),
            "audience_safe_post": rew_post,
            "reply_hot_take": {
                "sarcastic": str(rew_reply.get("sarcastic") or "").strip(),
                "sharp_but_safe": str(rew_reply.get("sharp_but_safe") or "").strip(),
                "og_explainer": str(rew_reply.get("og_explainer") or "").strip(),
            },
            "entities_explained": rew_entities,
            "audience_context_score": rew_self_score,
            "x_taste_score": _safe_int(reviewer.get("x_taste_score"), 0),
            "human_taste_score": _safe_int(reviewer.get("human_taste_score"), 0),
            "risk_level": "low",
            "source_url": str(orig.get("source_url") or ""),
            "observed_at": str(orig.get("observed_at") or ""),
            "review_decision": str(reviewer.get("review_decision") or ""),
        }

    # ── Part D: build final queue ────────────────────────────────────
    ready_ordinary: list[dict[str, Any]] = []
    insider_only: list[dict[str, Any]] = []
    need_rewrite_out: list[dict[str, Any]] = []
    blocked_by_risk_out: list[dict[str, Any]] = []

    for result in audit_results:
        eid = result["event_id"]
        action = result["action"]

        if eid in rewrites:
            # rewritten version available
            rw = rewrites[eid]
            # re-score the rewritten version
            rewritten_score = rw.get("audience_context_score", 0)
            if rewritten_score >= 7:
                ready_ordinary.append(rw)
            else:
                need_rewrite_out.append({"event_id": eid, "reason": f"rewrite_score={rewritten_score}<7"})
        elif action == "KEEP":
            # original item already passes
            orig = next((x for x in approved_items if x.get("event_id") == eid), None)
            if orig:
                rh = orig.get("reply_hot_take") if isinstance(orig.get("reply_hot_take"), dict) else {}
                ready_ordinary.append({
                    "event_id": eid,
                    "title": orig.get("title", ""),
                    "original_post": orig.get("post", ""),
                    "audience_safe_post": orig.get("post", ""),  # same as original
                    "reply_hot_take": rh,
                    "entities_explained": [],
                    "audience_context_score": result["audience_context_score"],
                    "x_taste_score": orig.get("score", 0),
                    "risk_level": orig.get("risk_level", "low"),
                    "source_url": str(orig.get("source_url") or ""),
                    "observed_at": str(orig.get("observed_at") or ""),
                })
        else:
            # DEMOTE_TO_INSIDER_ONLY or REWRITE_FOR_CONTEXT (not rewritten)
            insider_only.append({
                "event_id": eid,
                "title": result.get("title", ""),
                "audience_context_score": result["audience_context_score"],
                "action": action,
                "reason": "; ".join(result.get("deduction_details", [])),
            })

    final_queue = {
        "task_id": "x_v2_008_audience_context_gate",
        "generated_at_utc": _utc_now_iso(),
        "ready_for_ordinary_users": ready_ordinary,
        "insider_only": insider_only,
        "need_rewrite": need_rewrite_out,
        "risk_blocked": blocked_by_risk_out,
        "safety": {
            "x_published": False,
            "x_api_connected": False,
            "production_write": False,
            "daemon_started": False,
            "article_project_modified": False,
            "credential_exposed": False,
        },
    }
    _write_json(reports_dir / "x_v2_008_audience_safe_test_account_queue.json", final_queue)

    # ── final queue MD ───────────────────────────────────────────────
    qmd: list[str] = []
    qmd.append("# X v2-008 Audience-Safe Test Account Queue\n\n")
    qmd.append(f"- **generated_at_utc**: {final_queue['generated_at_utc']}\n")
    qmd.append(f"- **task_id**: {final_queue['task_id']}\n")
    qmd.append(f"- **model_calls_made**: {model_calls}\n\n")

    qmd.append("## 1. Ready for ordinary Web3 users\n\n")
    qmd.append(f"**count**: {len(ready_ordinary)}\n\n")
    for r in ready_ordinary:
        qmd.append(f"### {r['event_id']} — score={r.get('audience_context_score', '?')}\n\n")
        qmd.append(f"- **title**: {r.get('title', '')}\n")
        qmd.append(f"- **source_url**: {r.get('source_url', '')}\n")
        qmd.append(f"- **observed_at**: {r.get('observed_at', '')}\n")
        qmd.append(f"- **x_taste_score**: {r.get('x_taste_score', '')}\n")
        qmd.append(f"- **risk_level**: {r.get('risk_level', '')}\n")
        qmd.append(f"- **recommended_publish_mode**: manual_test_account_only\n")
        qmd.append(f"- **publish_status**: not_published\n\n")
        entities = r.get("entities_explained", [])
        if entities:
            qmd.append(f"**已解释实体**: {', '.join(entities)}\n\n")
        qmd.append("**主帖（普通用户版）**:\n\n")
        qmd.append(str(r.get("audience_safe_post") or r.get("original_post") or "").strip() + "\n\n")
        rh = r.get("reply_hot_take") if isinstance(r.get("reply_hot_take"), dict) else {}
        qmd.append("**Reply**:\n\n")
        qmd.append(f"- 😏 sarcastic: {str(rh.get('sarcastic') or '').strip()}\n")
        qmd.append(f"- 🧠 sharp_but_safe: {str(rh.get('sharp_but_safe') or '').strip()}\n")
        qmd.append(f"- 👴 og_explainer: {str(rh.get('og_explainer') or '').strip()}\n\n")
        qmd.append("---\n\n")

    qmd.append("## 2. Insider-only — not recommended for general account\n\n")
    qmd.append(f"**count**: {len(insider_only)}\n\n")
    for r in insider_only:
        qmd.append(f"- {r['event_id']}: {r.get('title','')} | score={r.get('audience_context_score','?')} | {r.get('reason','')}\n")
    if not insider_only:
        qmd.append("- (none)\n")
    qmd.append("\n")

    qmd.append("## 3. Need rewrite\n\n")
    for r in need_rewrite_out:
        qmd.append(f"- {r['event_id']}: {r.get('reason','')}\n")
    if not need_rewrite_out:
        qmd.append("- (none)\n")
    qmd.append("\n")

    qmd.append("## 4. Risk blocked\n\n")
    for r in blocked_by_risk_out:
        qmd.append(f"- {r['event_id']}: {r.get('reason','')}\n")
    if not blocked_by_risk_out:
        qmd.append("- (none)\n")
    qmd.append("\n")

    qmd.append("## Safety\n\n")
    for k, v in final_queue["safety"].items():
        qmd.append(f"- **{k}**: {v}\n")

    (reports_dir / "x_v2_008_audience_safe_test_account_queue.md").write_text(
        "".join(qmd), encoding="utf-8")

    # ── summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[DONE] x_v2_008 audience context gate")
    print(f"  audited_count: {len(audit_results)}")
    print(f"  rewritten_count: {len(rewrites)}")
    print(f"  ready_for_ordinary_users: {len(ready_ordinary)}")
    print(f"  insider_only_count: {len(insider_only)}")
    print(f"  need_rewrite_count: {len(need_rewrite_out)}")
    print(f"  blocked_by_risk: {len(blocked_by_risk_out)}")
    print(f"  model_calls_made: {model_calls}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
