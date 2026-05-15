from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any


def _parse_dt(s: str) -> datetime | None:
    ss = (s or "").strip()
    if not ss:
        return None
    try:
        return datetime.fromisoformat(ss.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(ss, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _event_time(item: dict[str, Any]) -> datetime:
    for k in ("received_at", "published_at"):
        dt = _parse_dt(str(item.get(k) or ""))
        if dt is not None:
            return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _norm_text(s: str) -> str:
    t = (s or "").lower()
    t = t.replace("（", "(").replace("）", ")")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _fingerprint(item: dict[str, Any]) -> str:
    return _norm_text(str(item.get("event_fingerprint") or ""))


def _title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("short_title") or "").strip()


def _text(item: dict[str, Any]) -> str:
    return _norm_text((_title(item) + "\n" + str(item.get("raw_text") or "")).strip())


def _match_any(text: str, keywords: list[str]) -> bool:
    t = text or ""
    return any(k in t for k in keywords if k)


CLUSTER_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "claude_recover_btc",
        ["claude", "btc", "5枚", "找回", "钱包", "seed phrase", "wallet.dat"],
    ),
    (
        "boe_stablecoin",
        ["英国央行", "英格兰银行", "bank of england", "稳定币", "stablecoin", "放宽", "缩减监管"],
    ),
    (
        "hormuz_energy",
        ["霍尔木兹", "伊朗", "油轮", "原油", "能源", "航运", "海峡"],
    ),
    (
        "kyiv_explosion",
        ["基辅", "爆炸", "俄罗斯", "乌克兰", "防空警报"],
    ),
    (
        "openai_microsoft_musk_trial",
        ["openai", "微软", "马斯克", "庭审", "法官", "结案陈词", "1000亿", "一千亿"],
    ),
]


def _pattern_key(text: str) -> str | None:
    t = text or ""
    for key, kws in CLUSTER_PATTERNS:
        if _match_any(t, kws):
            hits = sum(1 for k in kws if k and k in t)
            if hits >= 2:
                return key
    return None


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


def _tokenize_keywords(text: str) -> set[str]:
    t = text or ""
    keywords = [
        "马斯克",
        "特朗普",
        "openai",
        "微软",
        "a16z",
        "claude",
        "btc",
        "以太坊",
        "eth",
        "hype",
        "hyperliquid",
        "binance",
        "币安",
        "sec",
        "美联储",
        "etf",
        "稳定币",
        "stablecoin",
        "bank of england",
        "英国央行",
        "伊朗",
        "霍尔木兹",
        "原油",
        "能源",
        "基辅",
        "乌克兰",
        "俄罗斯",
        "法院",
        "法官",
        "庭审",
        "黑客",
        "清算",
        "巨鲸",
        "交易所",
        "提现",
        "支付",
        "空投",
        "钱包",
        "seed phrase",
        "wallet.dat",
        "1000亿",
        "一千亿",
        "pendle",
        "tvl",
        "rwa",
    ]
    out: set[str] = set()
    for k in keywords:
        if k.lower() in t:
            out.add(k.lower())
    return out


@dataclass
class EventCluster:
    event_cluster_id: str
    cluster_title: str
    items: list[dict[str, Any]]
    item_count: int
    source_names: list[str]
    best_source_item_id: str
    hot_signal_item_ids: list[str]
    topic_priority: str
    audience_reach_score: int
    cluster_reason: str


def cluster_hot_inputs(hot_inputs: list[dict[str, Any]]) -> list[EventCluster]:
    items = sorted(hot_inputs, key=_event_time)
    clusters: list[dict[str, Any]] = []

    for it in items:
        ts = _event_time(it)
        text = _text(it)
        fp = _fingerprint(it)
        pk = _pattern_key(text)
        kw = _tokenize_keywords(text)

        best_idx: int | None = None
        best_score = 0.0
        for idx, c in enumerate(clusters):
            if ts - c["latest_ts"] > timedelta(hours=6):
                continue

            score = 0.0
            if pk and c.get("pattern_key") == pk:
                score = 1.0
            elif fp and c.get("fingerprint") and _similar(fp, str(c.get("fingerprint") or "")) >= 0.88:
                score = 0.95
            else:
                inter = len(kw & c["keywords"])
                if inter >= 2:
                    score = 0.6 + min(0.3, inter * 0.05)
                elif inter == 1 and (fp and c.get("fingerprint")):
                    score = 0.55

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is None or best_score < 0.6:
            clusters.append(
                {
                    "items": [it],
                    "latest_ts": ts,
                    "earliest_ts": ts,
                    "fingerprint": fp,
                    "pattern_key": pk,
                    "keywords": set(kw),
                }
            )
        else:
            c = clusters[best_idx]
            c["items"].append(it)
            c["latest_ts"] = max(c["latest_ts"], ts)
            c["earliest_ts"] = min(c["earliest_ts"], ts)
            if not c.get("fingerprint") and fp:
                c["fingerprint"] = fp
            c["pattern_key"] = c.get("pattern_key") or pk
            c["keywords"] |= kw

    out: list[EventCluster] = []
    for c in clusters:
        its = c["items"]
        ids = [str(x.get("input_id") or "").strip() for x in its if str(x.get("input_id") or "").strip()]
        seed = "|".join(sorted(ids)) + "|" + c["earliest_ts"].isoformat()
        cid = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

        source_names = sorted({str(x.get("source_name") or "").strip() for x in its if str(x.get("source_name") or "").strip()})
        title = _title(its[0]) if its else ""
        out.append(
            EventCluster(
                event_cluster_id=cid,
                cluster_title=title,
                items=its,
                item_count=len(its),
                source_names=source_names,
                best_source_item_id="",
                hot_signal_item_ids=[],
                topic_priority="P2",
                audience_reach_score=0,
                cluster_reason="规则聚类：相同实体/关键词/6小时窗口",
            )
        )

    return out

