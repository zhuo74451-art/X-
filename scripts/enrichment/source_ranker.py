from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import re


@dataclass(frozen=True)
class RegistryEntry:
    name: str
    domain: str
    tier: str
    source_score: int
    use_case: str
    notes: str


def _load_registry(registry_path: Path) -> list[RegistryEntry]:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    out: list[RegistryEntry] = []
    for s in data.get("sources") or []:
        out.append(
            RegistryEntry(
                name=str(s.get("name") or ""),
                domain=str(s.get("domain") or "").lower(),
                tier=str(s.get("tier") or "P2"),
                source_score=int(s.get("source_score") or 0),
                use_case=str(s.get("use_case") or ""),
                notes=str(s.get("notes") or ""),
            )
        )
    return out


def _domain_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _match_registry(domain: str, registry: list[RegistryEntry]) -> RegistryEntry | None:
    d = (domain or "").lower()
    if not d:
        return None
    for e in registry:
        if not e.domain:
            continue
        if d == e.domain or d.endswith("." + e.domain):
            return e
    return None


def _infer_from_source_names(source_names: list[str], registry: list[RegistryEntry]) -> list[RegistryEntry]:
    out: list[RegistryEntry] = []
    for n in source_names:
        nn = (n or "").lower()
        nn = nn.split("news:")[-1]
        nn = nn.split("tg:")[-1]
        nn = nn.replace("-", "").replace("_", "")
        for e in registry:
            key = e.name.lower().replace("-", "").replace("_", "")
            if key and key in nn:
                out.append(e)
    return out


def _title_fingerprint(domain: str, title: str) -> str:
    d = (domain or "").lower()
    t = (title or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", t)
    return f"{d}|{t[:80]}"


def _dedup_inputs(items: list[dict[str, Any]], max_per_domain: int = 2) -> list[dict[str, Any]]:
    url_seen: set[str] = set()
    fp_seen: set[str] = set()
    domain_count: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for r in items:
        url = str(r.get("url") or "").strip()
        title = str(r.get("title") or "").strip()
        domain = str(r.get("domain") or _domain_from_url(url) or "").lower().strip()
        if url:
            ukey = url.lower()
            if ukey in url_seen:
                continue
            url_seen.add(ukey)
        fp = _title_fingerprint(domain, title)
        if fp in fp_seen:
            continue
        fp_seen.add(fp)
        if domain:
            c = domain_count.get(domain, 0)
            if c >= max_per_domain:
                continue
            domain_count[domain] = c + 1
        out.append(r)
    return out


def rank_sources(
    search_results: list[dict[str, Any]],
    source_names: list[str],
    registry_path: Path,
) -> dict[str, Any]:
    registry = _load_registry(registry_path)

    flat_results: list[dict[str, Any]] = []
    for r in search_results:
        if isinstance(r, dict) and isinstance(r.get("results"), list):
            for it in r.get("results") or []:
                if isinstance(it, dict):
                    flat_results.append(it)
        elif isinstance(r, dict):
            flat_results.append(r)
    flat_results = _dedup_inputs(flat_results, max_per_domain=2)

    enriched: list[dict[str, Any]] = []
    for r in flat_results:
        url = str(r.get("url") or "")
        title = str(r.get("title") or "")
        snippet = str(r.get("snippet") or "")
        domain = str(r.get("domain") or _domain_from_url(url) or "").lower()
        source_name = str(r.get("source_name") or "")
        published_at = str(r.get("published_at") or "")
        reg = _match_registry(domain, registry)
        tier = "unknown"
        base_score = 40
        if reg is not None:
            tier = reg.tier
        if tier == "P0":
            base_score = 95
        elif tier == "P1":
            base_score = 80
        elif tier == "P2":
            base_score = 55
        else:
            base_score = 45 if domain else 35

        score = base_score
        if reg is not None:
            score = max(score, int(reg.source_score))

        why = []
        if tier != "unknown":
            why.append(f"registry_tier={tier}")
        if domain:
            why.append(f"domain={domain}")
        if source_name:
            why.append(f"hint={source_name}")
        enriched.append(
            {
                "url": url,
                "title": title,
                "snippet": snippet,
                "domain": domain,
                "published_at": published_at,
                "source_name": (reg.name if reg is not None else (source_name or domain or "unknown")),
                "tier": tier,
                "source_score": int(score),
                "why_selected": ", ".join(why).strip(),
            }
        )

    if not enriched and source_names:
        inferred = _infer_from_source_names(source_names, registry)
        for e in inferred[:3]:
            enriched.append(
                {
                    "url": "",
                    "title": "",
                    "snippet": "",
                    "domain": e.domain,
                    "tier": e.tier,
                    "source_score": e.source_score,
                    "source_name": e.name,
                    "why_selected": f"inferred_from_source_names tier={e.tier}",
                }
            )

    tier_order = {"P0": 0, "P1": 1, "P2": 2, "unknown": 3}
    enriched.sort(
        key=lambda x: (tier_order.get(str(x.get("tier") or "unknown"), 9), -int(x.get("source_score") or 0))
    )

    best_sources = enriched[:5]

    tiers = [str(s.get("tier") or "P2") for s in best_sources]
    has_p0 = any(t == "P0" for t in tiers)
    p1_count = sum(1 for t in tiers if t == "P1")
    only_p2_or_unknown = bool(best_sources) and all(t in ("P2", "unknown") for t in tiers)

    domains = [str(s.get("domain") or "") for s in best_sources]
    only_secondary = all(
        (("t.me" in d) or ("jin10.com" in d) or (not d)) for d in domains
    ) and bool(best_sources)

    if has_p0:
        source_risk = "low"
        source_risk_reason = "存在 P0 来源（官方/监管/权威媒体等）"
    elif p1_count >= 2:
        source_risk = "low"
        source_risk_reason = "存在多个 P1 来源可互相印证"
    elif only_secondary:
        source_risk = "medium"
        source_risk_reason = "仅有二手聚合源（tg/jin10 等），需要回溯一手来源"
    elif only_p2_or_unknown:
        source_risk = "medium"
        source_risk_reason = "来源层级偏低（P2/unknown），需要补一手来源"
    else:
        source_risk = "medium"
        source_risk_reason = "来源不足以直接升级，建议继续补一手来源与关键事实"

    if not best_sources:
        source_risk = "high"
        source_risk_reason = "未获得可用搜索结果/来源线索"

    source_summary = " / ".join(
        [f'{s.get("tier")}:{s.get("source_name") or s.get("domain")}' for s in best_sources[:3]]
    ).strip()

    return {
        "best_sources": best_sources,
        "ranked_results": enriched,
        "source_risk": source_risk,
        "source_risk_reason": source_risk_reason,
        "source_summary": source_summary,
    }

