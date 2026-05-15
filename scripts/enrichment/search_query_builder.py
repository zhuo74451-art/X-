from __future__ import annotations

import re
from typing import Any


_STOPWORDS = {
    "据",
    "消息",
    "表示",
    "宣布",
    "称",
    "将",
    "已",
    "今日",
    "今天",
    "过去",
    "小时",
    "分钟",
    "美国",
    "参议院",
    "法院",
    "SEC",
    "CFTC",
}


def _extract_entities(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []

    ents: list[str] = []
    for m in re.findall(r"[A-Z][A-Za-z0-9&\.\-]{1,30}", t):
        if m.upper() in _STOPWORDS:
            continue
        ents.append(m)

    for m in re.findall(r"[\u4e00-\u9fff]{2,8}", t):
        if m in _STOPWORDS:
            continue
        ents.append(m)

    seen: set[str] = set()
    out: list[str] = []
    for e in ents:
        if e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out[:6]


def build_search_queries(event_cluster: dict[str, Any], max_queries: int = 5) -> dict[str, Any]:
    event_id = str(event_cluster.get("event_cluster_id") or "")
    title = str(event_cluster.get("cluster_title") or "").strip()
    entities = _extract_entities(title)

    queries: list[dict[str, str]] = []
    if title:
        queries.append({"type": "exact_title_query", "query": title})

    if entities:
        queries.append({"type": "entity_query", "query": " ".join(entities[:4])})

    queries.append(
        {
            "type": "source_query",
            "query": f'{title} (Reuters OR Bloomberg OR CoinDesk OR The Block OR Cointelegraph OR official)',
        }
        if title
        else {"type": "source_query", "query": "Reuters OR Bloomberg OR official OR CoinDesk OR The Block"}
    )

    queries.append(
        {
            "type": "timeline_query",
            "query": f'{title} last 72 hours timeline',
        }
        if title
        else {"type": "timeline_query", "query": "last 72 hours timeline"}
    )

    queries.append(
        {
            "type": "original_source_query",
            "query": f'{title} original report OR press release OR filing',
        }
        if title
        else {"type": "original_source_query", "query": "original report OR press release OR filing"}
    )

    dedup: list[dict[str, str]] = []
    seen_q: set[str] = set()
    for q in queries:
        qq = q["query"].strip()
        if not qq or qq in seen_q:
            continue
        seen_q.add(qq)
        dedup.append(q)
        if len(dedup) >= max_queries:
            break

    return {"event_cluster_id": event_id, "queries": dedup}

