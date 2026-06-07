#!/usr/bin/env python3
"""X v2-008 Chinese Web3 Sharp Style: 审计 + 锐评风重写。

流程：
1. 读取 v2-007a approved 队列
2. 程序化预审（行话、谜语、空洞词、语感）
3. 对不通过项调模型重写（writer + dual reviewer）
4. 输出 v2-008 最终队列
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
    return json.loads(_read_text(path))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


# ── entity dictionary ────────────────────────────────────────────────────

ENTITY_MAP: dict[str, str] = {
    "EF": "以太坊官方基金会",
    "Joe Lubin": "以太坊联合创始人 / Consensys 老板",
    "Lubin": "Joe Lubin（以太坊联合创始人 / Consensys 老板）",
    "Consensys": "小狐狸钱包 MetaMask 背后的公司",
    "MetaMask": "小狐狸钱包",
    "SEC": "美国证监会",
    "CFTC": "美国期货监管",
    "L2": "以太坊二层网络",
    "TVL": "总锁仓量",
    "DAO": "去中心化自治组织",
}

BANNED_WORDS: list[str] = [
    "耐人寻味", "懂得都懂", "懂的都懂", "水很深", "你品你细品",
    "值得关注", "引发市场关注", "基础设施", "基本常识", "良性竞争",
    "值得注意的是", "从某种程度上说", "综上所述",
]

HARD_ASSERTIONS: list[str] = [
    "已经被架空", "明确利益输送", "最大受益者已经坐实",
    "官方砸盘", "以太坊要凉", "项目方跑路",
    "必然", "毫无疑问", "已坐实",
]

VAGUE_PATTERNS: list[str] = [
    r"重新分工", r"划边界",
]

GPT_TONE_MARKERS: list[str] = [
    r"首先.*其次", r"首先.*最后", r"综上所述", r"值得注意的是",
    r"从某种程度上", r"在.{1,10}的背景下", r"随着.{1,10}的发展",
    r"值得关注的是", r"需要指出的是",
]


# ── programmatic pre-audit ───────────────────────────────────────────────

def _detect_entities(text: str) -> tuple[int, list[str]]:
    found = [t for t in ENTITY_MAP if t in text]
    return len(found), found


def _detect_banned(text: str) -> list[str]:
    return [w for w in BANNED_WORDS if w in text]


def _detect_hard_assertions(text: str) -> list[str]:
    return [a for a in HARD_ASSERTIONS if a in text]


def _detect_vague(text: str) -> list[str]:
    found = []
    for pat in VAGUE_PATTERNS:
        if re.search(pat, text):
            found.append(pat)
    return found


def _detect_gpt_tone(text: str) -> list[str]:
    found = []
    for pat in GPT_TONE_MARKERS:
        if re.search(pat, text):
            found.append(pat)
    return found


def _check_opens_with_jargon(text: str) -> bool:
    """检查是否以冷门实体开头。"""
    stripped = text.strip().split("\n")[0].strip()
    for term in ["Lubin", "EF ", "Consensys"]:
        if stripped.startswith(term):
            return True
    return False


def pre_audit(item: dict[str, Any]) -> dict[str, Any]:
    """程序化预审 approved item。"""
    eid = item.get("event_id", "")
    post = str(item.get("post") or "")
    rh = item.get("reply_hot_take") if isinstance(item.get("reply_hot_take"), dict) else {}
    combined = post + " " + str(rh.get("sarcastic", "")) + " " + str(rh.get("sharp_but_safe", "")) + " " + str(rh.get("og_explainer", ""))

    entity_count, entities = _detect_entities(combined)
    banned = _detect_banned(combined)
    hard = _detect_hard_assertions(combined)
    vague = _detect_vague(combined)
    gpt_tone = _detect_gpt_tone(combined)
    opens_jargon = _check_opens_with_jargon(post)

    # 计算 audience_context_score (0-10)
    audience = 10
    deductions: list[str] = []
    if entity_count > 0:
        ded = min(entity_count * 2, 6)
        audience -= ded
        deductions.append(f"未解释实体×{entity_count}: {entities} (-{ded})")
    if banned:
        ded = min(len(banned) * 2, 6)
        audience -= ded
        deductions.append(f"禁止词×{len(banned)}: {banned} (-{ded})")
    if opens_jargon:
        audience -= 3
        deductions.append("开头就是冷门实体 (-3)")
    audience = max(0, min(10, audience))

    # 计算 sharpness_score (0-10)
    sharpness = 10
    if gpt_tone:
        ded = min(len(gpt_tone) * 2, 6)
        sharpness -= ded
        deductions.append(f"GPT稳健口吻×{len(gpt_tone)}: {gpt_tone} (-{ded})")
    if vague:
        ded = min(len(vague) * 2, 4)
        sharpness -= ded
        deductions.append(f"模糊表达×{len(vague)}: {vague} (-{ded})")
    if hard:
        sharpness -= len(hard) * 3
        deductions.append(f"硬断言×{len(hard)}: {hard}")
    if banned:
        # 已经扣过 audience，不再重复扣 sharpness
        pass
    sharpness = max(0, min(10, sharpness))

    needs_rewrite = audience < 8 or sharpness < 8
    action = "REWRITE" if needs_rewrite else "KEEP"

    return {
        "event_id": eid,
        "title": str(item.get("title") or ""),
        "audience_context_score": audience,
        "sharpness_score": sharpness,
        "entities_found": entities,
        "banned_found": banned,
        "hard_assertions_found": hard,
        "vague_found": vague,
        "gpt_tone_found": gpt_tone,
        "opens_with_jargon": opens_jargon,
        "needs_rewrite": needs_rewrite,
        "action": action,
        "deduction_details": deductions,
    }


# ── model call ───────────────────────────────────────────────────────────

def _call_model(task_type: str, system_prompt: str, user_prompt: str,
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
        print(f"[ERROR] v2-007a queue not found", file=sys.stderr)
        return 2

    queue = _read_json(queue_path)
    approved_items = queue.get("ready") if isinstance(queue.get("ready"), list) else []
    print(f"[INFO] loaded {len(approved_items)} approved item(s)")

    # ── Part B: pre-audit ────────────────────────────────────────────
    audit_results = [pre_audit(it) for it in approved_items]
    for r in audit_results:
        print(f"  {r['event_id']}: audience={r['audience_context_score']} "
              f"sharpness={r['sharpness_score']} action={r['action']}")

    # ── model setup ──────────────────────────────────────────────────
    from llm_client import load_openrouter_api_key
    api_key = load_openrouter_api_key()
    use_mock = not bool(api_key)
    if use_mock:
        print("[WARN] OPENROUTER_API_KEY not found — MOCK mode")
        os.environ["MODEL_RUNTIME"] = "mock"
    else:
        os.environ["MODEL_RUNTIME"] = "openrouter"
        if not (os.getenv("OPENROUTER_MODEL") or "").strip():
            os.environ["OPENROUTER_MODEL"] = "anthropic/claude-sonnet-4.6"
    model = (os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6").strip()

    sharp_prompt = _read_text(root / "prompts" / "x_chinese_web3_sharp_style_v008.md")
    reviewer_prompt = _read_text(root / "prompts" / "x_audience_sharpness_reviewer_v008.md")

    # ── Part C: rewrite items that need it ───────────────────────────
    rewrite_targets = [r for r in audit_results if r["needs_rewrite"]]
    rewrite_targets = rewrite_targets[:2]  # max 2

    model_calls = 0
    max_model_calls = 6
    rewrites: dict[str, dict[str, Any]] = {}

    out_root = root / "out" / "x_sharp_rewrite_v008"
    out_root.mkdir(parents=True, exist_ok=True)

    for target in rewrite_targets:
        if model_calls >= max_model_calls:
            print(f"[WARN] model_calls reached max ({max_model_calls})")
            break

        eid = target["event_id"]
        orig = next((x for x in approved_items if x.get("event_id") == eid), None)
        if not orig:
            continue

        print(f"\n[REWRITE] {eid} (audience={target['audience_context_score']} sharpness={target['sharpness_score']})")

        out_dir = out_root / eid
        out_dir.mkdir(parents=True, exist_ok=True)

        rh = orig.get("reply_hot_take") if isinstance(orig.get("reply_hot_take"), dict) else {}

        # Build rewrite user prompt
        user_prompt = (
            "你收到一条 X（Twitter）加密圈帖子和审稿意见，请用中文 Web3 锐评风重写。\n\n"
            "## 原始内容\n"
            f"title: {orig.get('title', '')}\n"
            f"source_url: {orig.get('source_url', '')}\n\n"
            f"original_post: {orig.get('post', '')}\n\n"
            f"original_sarcastic: {rh.get('sarcastic', '')}\n"
            f"original_sharp_but_safe: {rh.get('sharp_but_safe', '')}\n"
            f"original_og_explainer: {rh.get('og_explainer', '')}\n\n"
            "## 审稿意见\n"
            + json.dumps(target, ensure_ascii=False, indent=2)
            + "\n\n## 输出要求\n"
            "生成三个版本：\n"
            "1. personal_sharp：锐评风主帖（有瓜味、有冲突、敢质疑但不造谣）\n"
            "2. personal_balanced：稍微克制的版本（有观点但不那么冲）\n"
            "3. reply_hot_take：三条热评回复（sarcastic / sharp_but_safe / og_explainer）\n\n"
            "关键约束：\n"
            "- 冷门实体必须翻译\n"
            "- 禁止谜语人和空洞词\n"
            "- 允许锐评但用质疑式表达，不能硬断言\n"
            "- 中文X语感：短句、口语、有节奏\n"
            "- 不喊单不预测不造谣不新增事实\n\n"
            "只输出 JSON：\n"
            "{\n"
            '  "event_id": "xxx",\n'
            '  "personal_sharp": "...",\n'
            '  "personal_balanced": "...",\n'
            '  "reply_hot_take": {\n'
            '    "sarcastic": "...",\n'
            '    "sharp_but_safe": "...",\n'
            '    "og_explainer": "..."\n'
            "  },\n"
            '  "entities_explained": ["EF -> 以太坊官方基金会", ...],\n'
            '  "changes_made": "具体改了什么"\n'
            "}\n"
        )

        _write_json(out_dir / "rewrite_request.json", {"event_id": eid, "audit": target})

        # 1. Writer
        if model_calls >= max_model_calls:
            rewrite = {"event_id": eid, "error": "model_call_limit"}
        else:
            rr = _call_model("x_sharp_rewrite_v008", sharp_prompt, user_prompt, 0.7, 1500)
            model_calls += 1
            _write_json(out_dir / "rewriter_response_raw.json", rr)
            if rr.get("ok") and isinstance(rr.get("json"), dict):
                rewrite = rr["json"]
            else:
                rewrite = {"event_id": eid, "personal_sharp": "", "personal_balanced": "",
                           "reply_hot_take": {}, "entities_explained": [], "changes_made": "",
                           "error": rr.get("error") or "rewriter_failed"}
            _write_json(out_dir / "rewriter_result.json", rewrite)

        # 2. Dual Reviewer
        sharp_post = str(rewrite.get("personal_sharp") or "")
        rew_reply = rewrite.get("reply_hot_take") if isinstance(rewrite.get("reply_hot_take"), dict) else {}

        review_user_prompt = (
            "## 待审内容\n\n"
            f"event_id: {eid}\n"
            f"title: {orig.get('title', '')}\n\n"
            f"personal_sharp: {sharp_post}\n\n"
            f"personal_balanced: {rewrite.get('personal_balanced', '')}\n\n"
            f"sarcastic: {rew_reply.get('sarcastic', '')}\n"
            f"sharp_but_safe: {rew_reply.get('sharp_but_safe', '')}\n"
            f"og_explainer: {rew_reply.get('og_explainer', '')}\n\n"
            "entities_explained: " + json.dumps(rewrite.get("entities_explained", []), ensure_ascii=False) + "\n\n"
            "请按 audience_context_score + sharpness_score + safety 三维审查。只输出 JSON。\n"
        )

        if model_calls >= max_model_calls:
            review = {"audience_context_score": 7, "sharpness_score": 7, "review_decision": "NEED_REWRITE"}
        else:
            rv = _call_model("x_dual_reviewer_v008", reviewer_prompt, review_user_prompt, 0.2, 900)
            model_calls += 1
            _write_json(out_dir / "dual_reviewer_response_raw.json", rv)
            if rv.get("ok") and isinstance(rv.get("json"), dict):
                review = rv["json"]
            else:
                review = {"audience_context_score": 7, "sharpness_score": 7,
                          "review_decision": "NEED_REWRITE", "safety_pass": True}
            _write_json(out_dir / "dual_reviewer_result.json", review)

        rew_entities = rewrite.get("entities_explained", [])
        rewrites[eid] = {
            "event_id": eid,
            "title": orig.get("title", ""),
            "original_post": orig.get("post", ""),
            "personal_sharp": sharp_post,
            "personal_balanced": str(rewrite.get("personal_balanced") or ""),
            "reply_hot_take": {
                "sarcastic": str(rew_reply.get("sarcastic") or ""),
                "sharp_but_safe": str(rew_reply.get("sharp_but_safe") or ""),
                "og_explainer": str(rew_reply.get("og_explainer") or ""),
            },
            "entities_explained": rew_entities,
            "audience_context_score": _safe_int(review.get("audience_context_score"), 0),
            "sharpness_score": _safe_int(review.get("sharpness_score"), 0),
            "x_taste_score": _safe_int(review.get("x_taste_score"), 0),
            "risk_level": "low",
            "review_decision": str(review.get("review_decision") or ""),
            "safety_pass": review.get("safety_pass", True),
            "source_url": str(orig.get("source_url") or ""),
            "observed_at": str(orig.get("observed_at") or ""),
            "recommended_publish_mode": "manual_test_account_only",
            "publish_status": "not_published",
        }
        print(f"  -> audience={review.get('audience_context_score')} "
              f"sharpness={review.get('sharpness_score')} "
              f"decision={review.get('review_decision')}")

    # ── Part D: build final queue ────────────────────────────────────
    ready: list[dict[str, Any]] = []
    insider_only: list[dict[str, Any]] = []
    need_rewrite_out: list[dict[str, Any]] = []
    risk_blocked: list[dict[str, Any]] = []

    for audit in audit_results:
        eid = audit["event_id"]

        if eid in rewrites:
            rw = rewrites[eid]
            audience_ok = rw["audience_context_score"] >= 8
            sharpness_ok = rw["sharpness_score"] >= 8
            safety_ok = rw.get("safety_pass", True)
            if audience_ok and sharpness_ok and safety_ok:
                ready.append(rw)
            elif not safety_ok:
                risk_blocked.append({"event_id": eid, "reason": "safety_check_failed"})
            else:
                reasons = []
                if not audience_ok:
                    reasons.append(f"audience={rw['audience_context_score']}<8")
                if not sharpness_ok:
                    reasons.append(f"sharpness={rw['sharpness_score']}<8")
                need_rewrite_out.append({"event_id": eid, "reason": "; ".join(reasons)})
        elif audit["action"] == "KEEP":
            orig = next((x for x in approved_items if x.get("event_id") == eid), None)
            if orig:
                rh = orig.get("reply_hot_take") if isinstance(orig.get("reply_hot_take"), dict) else {}
                ready.append({
                    "event_id": eid,
                    "title": orig.get("title", ""),
                    "original_post": orig.get("post", ""),
                    "personal_sharp": orig.get("post", ""),
                    "personal_balanced": orig.get("post", ""),
                    "reply_hot_take": rh,
                    "entities_explained": [],
                    "audience_context_score": audit["audience_context_score"],
                    "sharpness_score": audit["sharpness_score"],
                    "x_taste_score": orig.get("score", 0),
                    "risk_level": orig.get("risk_level", "low"),
                    "source_url": str(orig.get("source_url") or ""),
                    "observed_at": str(orig.get("observed_at") or ""),
                    "recommended_publish_mode": "manual_test_account_only",
                    "publish_status": "not_published",
                })
        else:
            insider_only.append({
                "event_id": eid,
                "title": audit.get("title", ""),
                "audience_context_score": audit["audience_context_score"],
                "sharpness_score": audit["sharpness_score"],
                "reason": "; ".join(audit.get("deduction_details", [])),
            })

    # ── write reports ────────────────────────────────────────────────
    report = {
        "task_id": "x_v2_008_chinese_web3_sharp_audience_style",
        "generated_at_utc": _utc_now_iso(),
        "model": model,
        "model_calls_made": model_calls,
        "audited_count": len(audit_results),
        "rewritten_count": len(rewrites),
        "ready_for_test_account": len(ready),
        "insider_only_count": len(insider_only),
        "need_rewrite_count": len(need_rewrite_out),
        "blocked_by_risk": len(risk_blocked),
        "items": audit_results,
        "rewrites": [{"event_id": k, **{kk: vv for kk, vv in v.items() if kk != "reply_hot_take"}} for k, v in rewrites.items()],
        "safety": {"x_published": False, "x_api_connected": False, "production_write": False,
                   "daemon_started": False, "article_project_modified": False, "credential_exposed": False},
    }
    _write_json(reports_dir / "x_v2_008_chinese_sharp_audience_report.json", report)

    # MD report
    rmd: list[str] = []
    rmd.append("# X v2-008 Chinese Web3 Sharp Audience Report\n\n")
    rmd.append(f"- **model_calls_made**: {model_calls}\n")
    rmd.append(f"- **audited_count**: {len(audit_results)}\n")
    rmd.append(f"- **rewritten_count**: {len(rewrites)}\n")
    rmd.append(f"- **ready_for_test_account**: {len(ready)}\n\n")
    for rw in rewrites.values():
        rmd.append(f"## {rw['event_id']}\n\n")
        rmd.append(f"### personal_sharp (audience={rw['audience_context_score']} sharpness={rw['sharpness_score']})\n\n")
        rmd.append(str(rw.get("personal_sharp", "")).strip() + "\n\n")
        rmd.append(f"### personal_balanced\n\n")
        rmd.append(str(rw.get("personal_balanced", "")).strip() + "\n\n")
        rmd.append(f"### reply_hot_take\n\n")
        repl = rw.get("reply_hot_take", {})
        rmd.append(f"- sarcastic: {repl.get('sarcastic', '')}\n")
        rmd.append(f"- sharp_but_safe: {repl.get('sharp_but_safe', '')}\n")
        rmd.append(f"- og_explainer: {repl.get('og_explainer', '')}\n\n")
        rmd.append(f"entities_explained: {rw.get('entities_explained', [])}\n\n---\n\n")
    (reports_dir / "x_v2_008_chinese_sharp_audience_report.md").write_text("".join(rmd), encoding="utf-8")

    # Queue
    final_queue = {
        "task_id": "x_v2_008_chinese_web3_sharp_audience_style",
        "generated_at_utc": _utc_now_iso(),
        "model_calls_made": model_calls,
        "READY_FOR_TEST_ACCOUNT": ready,
        "INSIDER_ONLY_NOT_RECOMMENDED": insider_only,
        "NEED_REWRITE": need_rewrite_out,
        "RISK_BLOCKED": risk_blocked,
        "safety": report["safety"],
    }
    _write_json(reports_dir / "x_v2_008_chinese_sharp_test_account_queue.json", final_queue)

    # Queue MD
    qmd: list[str] = []
    qmd.append("# X v2-008 Chinese Web3 Sharp Test Account Queue\n\n")
    qmd.append(f"- **model_calls_made**: {model_calls}\n\n")
    for section, title in [("READY_FOR_TEST_ACCOUNT", "Ready for test account"),
                            ("INSIDER_ONLY_NOT_RECOMMENDED", "Insider only"),
                            ("NEED_REWRITE", "Need rewrite"),
                            ("RISK_BLOCKED", "Risk blocked")]:
        items = final_queue.get(section) if isinstance(final_queue.get(section), list) else []
        qmd.append(f"## {title} ({len(items)})\n\n")
        for it in items:
            if section == "READY_FOR_TEST_ACCOUNT":
                qmd.append(f"### {it.get('event_id')} — {it.get('title', '')}\n\n")
                qmd.append(f"- audience_context_score: {it.get('audience_context_score')}\n")
                qmd.append(f"- sharpness_score: {it.get('sharpness_score')}\n")
                qmd.append(f"- x_taste_score: {it.get('x_taste_score')}\n")
                qmd.append(f"- risk_level: {it.get('risk_level')}\n")
                qmd.append(f"- source_url: {it.get('source_url', '')}\n")
                qmd.append(f"- observed_at: {it.get('observed_at', '')}\n")
                qmd.append(f"- entities_explained: {it.get('entities_explained', [])}\n\n")
                qmd.append(f"**personal_sharp:**\n{it.get('personal_sharp', '')}\n\n")
                qmd.append(f"**personal_balanced:**\n{it.get('personal_balanced', '')}\n\n")
                repl = it.get('reply_hot_take', {})
                qmd.append(f"**reply:** sarcastic={repl.get('sarcastic','')} | sharp={repl.get('sharp_but_safe','')} | og={repl.get('og_explainer','')}\n\n")
            else:
                qmd.append(f"- {it.get('event_id')}: {it.get('title', '')} | {it.get('reason', '')}\n")
            qmd.append("\n")
    (reports_dir / "x_v2_008_chinese_sharp_test_account_queue.md").write_text("".join(qmd), encoding="utf-8")

    # ── summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[DONE] x_v2_008 Chinese Web3 Sharp Style")
    print(f"  audited_count: {len(audit_results)}")
    print(f"  rewritten_count: {len(rewrites)}")
    print(f"  ready_for_test_account: {len(ready)}")
    print(f"  insider_only: {len(insider_only)}")
    print(f"  need_rewrite: {len(need_rewrite_out)}")
    print(f"  blocked_by_risk: {len(risk_blocked)}")
    print(f"  model_calls_made: {model_calls}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
