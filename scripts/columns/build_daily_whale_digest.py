from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVENTS_JSONL = ROOT / "out" / "hot_engine_queues" / "events.jsonl"

OUT_DIR = ROOT / "out" / "columns"
OUT_JSON = OUT_DIR / "daily_whale_digest.json"
OUT_MD = OUT_DIR / "daily_whale_digest.md"

CARDS_DIR = ROOT / "out" / "visual_cards"
OUT_CARD = CARDS_DIR / "daily_whale_digest.svg"

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
VISUAL_DIR = SCRIPTS_DIR / "visual"
for p in [str(SCRIPTS_DIR), str(VISUAL_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from visual.template_card_renderer import render_template_card


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                j = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(j, dict):
                out.append(j)
    return out


def _parse_ts(s: str) -> datetime | None:
    t = (s or "").strip()
    if not t:
        return None
    try:
        if t.endswith("Z"):
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _event_time_utc(event: dict[str, Any]) -> datetime | None:
    for k in ["created_at", "generated_at", "fetched_at", "updated_at"]:
        v = event.get(k)
        if isinstance(v, str):
            dt = _parse_ts(v)
            if dt:
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
    return None


_ADDR_RE = re.compile(r"\b0x[a-fA-F0-9]{6,}\b")


def _extract_address(text: str) -> str:
    m = _ADDR_RE.search(text or "")
    return m.group(0) if m else ""


def _norm_actor_label(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    low = t.lower()
    if "麻吉" in t or "machi" in low:
        return "麻吉/Machi"
    if "james wynn" in low or "wynn" == low:
        return "James Wynn"
    if "a16z" in low:
        return "a16z 相关钱包"
    if "hyperliquid" in low or "hype" in low:
        return "Hyperliquid 大户"
    return t


def _actor_key(event: dict[str, Any]) -> str:
    actor = _norm_actor_label(str(event.get("actor_label") or "").strip())
    title = str(event.get("cluster_title") or "").strip()
    summary = str(event.get("raw_summary") or "").strip()

    addr = _extract_address(title) or _extract_address(summary)
    if addr:
        return addr.lower()
    if actor:
        return actor.lower()

    txt = (title + "\n" + summary).lower()
    if "machi" in txt or "麻吉" in txt:
        return "麻吉/machi"
    if "james wynn" in txt:
        return "james wynn"
    if "a16z" in txt:
        return "a16z"
    if "hyperliquid" in txt or "hype" in txt:
        return "hyperliquid"
    return (title or summary or "unknown").lower()[:64]


def _display_actor(event: dict[str, Any]) -> str:
    actor = _norm_actor_label(str(event.get("actor_label") or "").strip())
    title = str(event.get("cluster_title") or "").strip()
    summary = str(event.get("raw_summary") or "").strip()
    if actor:
        return actor
    addr = _extract_address(title) or _extract_address(summary)
    if addr:
        return addr
    if "machi" in (title + summary).lower() or ("麻吉" in (title + summary)):
        return "麻吉/Machi"
    return "巨鲸地址"


def _as_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return float(int(x))
        return float(x)
    except (TypeError, ValueError):
        return default


def _hot_asset_bonus(asset: str) -> int:
    a = (asset or "").strip().upper()
    if a in {"HYPE", "BTC", "ETH", "SOL", "ZEC"}:
        return 120
    if a:
        return 40
    return 0


def _actor_priority_bonus(actor: str) -> int:
    low = (actor or "").lower()
    if "麻吉" in actor or "machi" in low:
        return 1000
    if "james wynn" in low:
        return 900
    if "a16z" in low:
        return 850
    if "hyperliquid" in low:
        return 800
    if "聪明钱" in actor:
        return 650
    return 0


def _build_action_line(event: dict[str, Any]) -> str:
    actor = _display_actor(event)
    asset = str(event.get("asset") or "").strip().upper()
    action = str(event.get("action") or "").strip()
    amt = _as_float(event.get("amount_usd"), 0.0)
    pnl = _as_float(event.get("pnl_usd"), 0.0)
    liq = str(event.get("liquidation_price") or "").strip()

    parts: list[str] = []
    if asset:
        parts.append(asset)
    if action:
        parts.append(action)
    if amt > 0:
        parts.append(f"${amt:,.0f}")
    if pnl != 0:
        parts.append(f"P/L ${pnl:,.0f}")
    if liq:
        parts.append(f"liq {liq}")
    core = " ".join(parts).strip()
    return f"{actor}：{core}" if core else f"{actor}：链上动作"


def _score_event(event: dict[str, Any]) -> int:
    actor = _display_actor(event)
    asset = str(event.get("asset") or "").strip()
    amt = _as_float(event.get("amount_usd"), 0.0)
    pnl = _as_float(event.get("pnl_usd"), 0.0)
    liq = str(event.get("liquidation_price") or "").strip()
    summary = str(event.get("raw_summary") or "").lower()

    score = 0
    score += _actor_priority_bonus(actor)
    score += _hot_asset_bonus(asset)
    if amt > 0:
        score += min(500, int(amt / 200_000))
    if pnl != 0:
        score += 80
    if liq:
        score += 180
    if any(x in summary for x in ["清算", "爆仓", "强平", "liq"]):
        score += 120
    if any(x in summary for x in ["连续", "再次", "加仓", "减仓", "调仓"]):
        score += 60
    return score


def _merge_group(events: list[dict[str, Any]]) -> dict[str, Any]:
    events_sorted = sorted(events, key=_score_event, reverse=True)
    top = events_sorted[0]
    actor = _display_actor(top)
    asset = str(top.get("asset") or "").strip().upper()

    actions = []
    for e in events_sorted[:6]:
        actions.append(_build_action_line(e))

    source_urls: list[str] = []
    for e in events_sorted:
        urls = e.get("source_urls")
        if isinstance(urls, list):
            for u in urls:
                s = str(u).strip()
                if s and s not in source_urls:
                    source_urls.append(s)
        bu = str(e.get("best_source_url") or "").strip()
        if bu and bu not in source_urls:
            source_urls.append(bu)

    amt = _as_float(top.get("amount_usd"), 0.0)
    pnl = _as_float(top.get("pnl_usd"), 0.0)
    liq = str(top.get("liquidation_price") or "").strip()

    latest_status = str(top.get("raw_summary") or "").strip()
    latest_status = latest_status.replace("\n", " ")
    if len(latest_status) > 160:
        latest_status = latest_status[:157] + "..."

    why = "明星交易员/高关注地址" if _actor_priority_bonus(actor) >= 800 else ""
    if not why and liq:
        why = "清算风险明显"
    if not why and amt > 0:
        why = "金额较大"
    if not why:
        why = "连续调仓/值得观察"

    comment_angle = str(top.get("comment_angle") or "").strip()
    if not comment_angle:
        comment_angle = "把它当成“仓位风向/风险压力测试”，而不是喊单。"

    return {
        "actor_label": actor,
        "asset": asset,
        "actions": actions,
        "amount_usd": f"{amt:,.0f}" if amt > 0 else "",
        "pnl_usd": f"{pnl:,.0f}" if pnl != 0 else "",
        "liquidation_price": liq,
        "latest_status": latest_status,
        "why_selected": why,
        "comment_angle": comment_angle,
        "source_urls": source_urls[:8],
        "_score": max(_score_event(top), max(_score_event(e) for e in events_sorted)),
    }


def _build_card_bullets(selected_items: list[dict[str, Any]], limit: int = 3) -> list[str]:
    bullets: list[str] = []
    for it in selected_items[:limit]:
        actor = str(it.get("actor_label") or "").strip()
        asset = str(it.get("asset") or "").strip().upper()
        actions = it.get("actions") if isinstance(it.get("actions"), list) else []
        key = ""
        if actions:
            key = str(actions[0]).strip()
            if "：" in key:
                key = key.split("：", 1)[-1].strip()
        num = ""
        if it.get("amount_usd"):
            num = "$" + str(it.get("amount_usd"))
        line = "｜".join([x for x in [actor, asset, key, num] if x])
        bullets.append(line[:64])
    return bullets


def _render_md(payload: dict[str, Any]) -> str:
    items = payload.get("selected_items") if isinstance(payload.get("selected_items"), list) else []
    out: list[str] = []
    out.append("# 今天巨鲸在干嘛\n\n")
    out.append(f"- date: {payload.get('date')}\n")
    out.append(f"- generated_at: {_utc_now_iso()}\n")
    out.append(f"- items: {len(items)}\n")

    if not items:
        out.append("\n## no_candidate\n")
        out.append("过去 24 小时没有足够的 whale_digest 候选（或数据不足），本期不生成图卡。\n")
        return "".join(out)

    out.append("\n## Selected\n")
    for i, it in enumerate(items, start=1):
        out.append("\n---\n")
        out.append(f"## {i}. {it.get('actor_label')} {it.get('asset')}\n")
        out.append(f"- why_selected: {it.get('why_selected')}\n")
        out.append(f"- liquidation_price: {it.get('liquidation_price')}\n")
        out.append(f"- amount_usd: {it.get('amount_usd')}\n")
        out.append(f"- pnl_usd: {it.get('pnl_usd')}\n")
        out.append(f"- latest_status: {it.get('latest_status')}\n")
        out.append("\n### actions\n")
        for a in (it.get("actions") or [])[:6]:
            out.append(f"- {a}\n")
        out.append("\n### source_urls\n")
        for u in (it.get("source_urls") or [])[:8]:
            out.append(f"- {u}\n")
        out.append("\n### comment_angle\n")
        out.append(str(it.get("comment_angle") or "").strip() + "\n")

    out.append("\n## Draft\n")
    out.append("\n### main_post_draft\n")
    out.append(payload.get("main_post_draft") or "")
    out.append("\n\n### first_comment_draft\n")
    out.append(payload.get("first_comment_draft") or "")

    out.append("\n\n## Card Copy\n")
    out.append(f"- card_title: {payload.get('card_title')}\n")
    out.append(f"- card_subtitle: {payload.get('card_subtitle')}\n")
    out.append("\n### card_bullets\n")
    for b in (payload.get("card_bullets") or [])[:6]:
        out.append(f"- {b}\n")

    out.append("\n## Risk Note\n")
    out.append(payload.get("risk_note") or "")
    out.append("\n")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="Max events scanned from events.jsonl")
    ap.add_argument("--max-items", type=int, default=5, help="Max selected whales (3-5 recommended)")
    ap.add_argument("--min-items", type=int, default=3, help="Min items required to render card")
    ap.add_argument("--hours", type=int, default=24, help="Best-effort time window filter if events have timestamps")
    args = ap.parse_args()

    rows = _read_jsonl(EVENTS_JSONL)
    whales = [e for e in rows if str(e.get("cluster_queue") or "").strip() == "whale_digest"]
    whales = whales[: max(0, int(args.limit or 0))] if args.limit else whales
    if int(args.hours or 0) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=int(args.hours))
        filtered: list[dict[str, Any]] = []
        for e in whales:
            dt = _event_time_utc(e)
            if dt is None:
                filtered.append(e)
            else:
                if dt >= cutoff:
                    filtered.append(e)
        whales = filtered

    groups: dict[str, list[dict[str, Any]]] = {}
    for e in whales:
        key = _actor_key(e)
        groups.setdefault(key, []).append(e)

    merged: list[dict[str, Any]] = []
    for _, evs in groups.items():
        if not evs:
            continue
        merged.append(_merge_group(evs))

    merged.sort(key=lambda x: int(x.get("_score") or 0), reverse=True)

    selected_items = merged[: max(0, int(args.max_items or 0))] if args.max_items else merged[:5]
    selected_items = [dict({k: v for k, v in it.items() if not k.startswith("_")}) for it in selected_items]

    lines: list[str] = []
    for i, it in enumerate(selected_items[:5], start=1):
        who = str(it.get("actor_label") or "某巨鲸").strip()
        asset = str(it.get("asset") or "").strip().upper()
        key = ""
        acts = it.get("actions") if isinstance(it.get("actions"), list) else []
        if acts:
            key = str(acts[0]).strip()
            if "：" in key:
                key = key.split("：", 1)[-1].strip()
        hint = ""
        if it.get("liquidation_price"):
            hint = f"（清算价 {it.get('liquidation_price')}）"
        elif it.get("amount_usd"):
            hint = f"（约 ${it.get('amount_usd')}）"
        lines.append(f"{i}. {who}{('｜' + asset) if asset else ''}：{key}{hint}".strip())

    main_post = ""
    if selected_items:
        main_post = (
            "今天巨鲸在干嘛？\n\n"
            "链上今天最有意思的，不是价格怎么跳，而是谁在用真金白银下注。\n\n"
            + "\n".join(lines[:5])
            + "\n\n"
            + "一句总评：把这些动作当成“风险与情绪的温度计”，重点看后续是否持续、是否出现清算压力扩散。"
        )

    first_comment = ""
    if selected_items:
        first_comment = (
            "观察口径：不做跟单建议。优先看“是否连续调仓/是否触发清算价附近的压力/是否出现提款或交易所风险叙事”。"
        )

    payload = {
        "column_name": "今天巨鲸在干嘛",
        "date": _utc_today(),
        "selected_items": selected_items,
        "main_post_draft": main_post,
        "first_comment_draft": first_comment,
        "card_title": "今天巨鲸在干嘛",
        "card_subtitle": "3 个最值得看的链上动作",
        "card_bullets": _build_card_bullets(selected_items, limit=3),
        "risk_note": "仅作信息观察，不构成投资建议；链上/仓位数据可能延迟或不完整，引用前需再次核验来源锚点。",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_render_md(payload), encoding="utf-8")

    if len(selected_items) >= int(args.min_items or 0):
        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = render_template_card(
            out_dir=CARDS_DIR,
            event_cluster_id="daily_whale_digest",
            template_name="daily_whale_digest_card",
            brief={"card_title": payload["card_title"], "card_subtitle": payload["card_subtitle"], "card_bullets": payload["card_bullets"]},
        )
        try:
            if OUT_CARD.exists():
                OUT_CARD.unlink()
            tmp.rename(OUT_CARD)
        except OSError:
            OUT_CARD.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")

    print(
        f"[build_daily_whale_digest] ok whales={len(whales)} groups={len(groups)} selected={len(selected_items)} "
        f"out_json={OUT_JSON} out_md={OUT_MD} out_card={OUT_CARD if OUT_CARD.exists() else '(skipped)'}"
    )


if __name__ == "__main__":
    main()

