from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def _domain_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _norm_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urllib.parse.urlparse(u)
        scheme = p.scheme.lower() or "https"
        netloc = (p.netloc or "").lower()
        path = p.path or ""
        q = p.query or ""
        return urllib.parse.urlunparse((scheme, netloc, path, "", q, ""))
    except Exception:
        return u


def _title_fingerprint(domain: str, title: str) -> str:
    d = (domain or "").lower()
    t = (title or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", t)
    return f"{d}|{t[:80]}"


def _dedup_and_cap(
    results: list[dict[str, Any]],
    max_per_domain: int = 2,
) -> list[dict[str, Any]]:
    url_seen: set[str] = set()
    fp_seen: set[str] = set()
    domain_count: dict[str, int] = {}

    kept: list[dict[str, Any]] = []
    for r in results:
        url = _norm_url(str(r.get("url") or ""))
        title = str(r.get("title") or "").strip()
        domain = str(r.get("domain") or _domain_from_url(url) or "").strip().lower()
        if not url and not title:
            continue

        if url and url in url_seen:
            continue
        fp = _title_fingerprint(domain, title)
        if fp in fp_seen:
            continue
        if domain:
            c = domain_count.get(domain, 0)
            if c >= max_per_domain:
                continue
            domain_count[domain] = c + 1

        url_seen.add(url)
        fp_seen.add(fp)

        rr = dict(r)
        rr["url"] = url
        rr["domain"] = domain
        kept.append(rr)

    return kept


def _mock_search(query: str, seed_urls: list[str] | None = None) -> dict[str, Any]:
    seed_urls = seed_urls or []
    results: list[dict[str, Any]] = []
    for u in seed_urls[:8]:
        results.append(
            {
                "title": "",
                "url": u,
                "domain": _domain_from_url(u),
                "snippet": "",
                "published_at": "",
                "source_name": "",
                "raw": {},
            }
        )
    if not results:
        results.append(
            {
                "title": "",
                "url": "",
                "domain": "",
                "snippet": "",
                "published_at": "",
                "source_name": "",
                "raw": {},
            }
        )
    return {"provider": "mock", "query": query, "results": results}


def _http_json(req: urllib.request.Request, timeout_s: int = 12) -> Any:
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read().decode("utf-8", errors="replace")
        return json.loads(data)


def _tavily_search(query: str, api_key: str, max_results: int) -> dict[str, Any]:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
        "max_results": int(max_results),
    }
    req = urllib.request.Request(
        url="https://api.tavily.com/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = _http_json(req)
    results: list[dict[str, Any]] = []
    for r in data.get("results") or []:
        url = str(r.get("url") or "")
        results.append(
            {
                "title": str(r.get("title") or ""),
                "url": url,
                "domain": _domain_from_url(url),
                "snippet": str(r.get("content") or ""),
                "published_at": str(r.get("published_date") or ""),
                "source_name": "",
                "raw": r,
            }
        )
    return {"provider": "tavily", "query": query, "results": results}


def _brave_search(query: str, api_key: str, max_results: int) -> dict[str, Any]:
    q = urllib.parse.quote(query)
    url = f"https://api.search.brave.com/res/v1/web/search?q={q}&count={int(max_results)}"
    req = urllib.request.Request(url=url, headers={"X-Subscription-Token": api_key}, method="GET")
    data = _http_json(req)
    results: list[dict[str, Any]] = []
    web = data.get("web") or {}
    for r in (web.get("results") or [])[: int(max_results)]:
        url0 = str(r.get("url") or "")
        results.append(
            {
                "title": str(r.get("title") or ""),
                "url": url0,
                "domain": _domain_from_url(url0),
                "snippet": str(r.get("description") or ""),
                "published_at": str(r.get("age") or ""),
                "source_name": "",
                "raw": r,
            }
        )
    return {"provider": "brave", "query": query, "results": results}


def _serpapi_search(query: str, api_key: str, max_results: int) -> dict[str, Any]:
    q = urllib.parse.quote(query)
    url = f"https://serpapi.com/search.json?engine=google&q={q}&api_key={urllib.parse.quote(api_key)}&num={int(max_results)}"
    req = urllib.request.Request(url=url, method="GET")
    data = _http_json(req)
    results: list[dict[str, Any]] = []
    for r in (data.get("organic_results") or [])[: int(max_results)]:
        url0 = str(r.get("link") or "")
        results.append(
            {
                "title": str(r.get("title") or ""),
                "url": url0,
                "domain": _domain_from_url(url0),
                "snippet": str(r.get("snippet") or ""),
                "published_at": "",
                "source_name": "",
                "raw": r,
            }
        )
    return {"provider": "serpapi", "query": query, "results": results}


def run_search(
    query: str,
    provider: str,
    max_results: int,
    seed_urls: list[str] | None = None,
) -> dict[str, Any]:
    p = (provider or "mock").strip().lower()
    query = (query or "").strip()
    max_results = max(1, int(max_results))

    if p in ("", "mock"):
        return _mock_search(query, seed_urls=seed_urls)

    key_map = {
        "tavily": ("TAVILY_API_KEY", _tavily_search),
        "brave": ("BRAVE_SEARCH_API_KEY", _brave_search),
        "serpapi": ("SERPAPI_API_KEY", _serpapi_search),
    }
    if p not in key_map:
        print(f"[web_search_adapter] unknown provider={p}, fallback to mock")
        return _mock_search(query, seed_urls=seed_urls)

    key_env, fn = key_map[p]
    api_key = _env(key_env)
    if not api_key:
        print(f"[web_search_adapter] missing {key_env}, fallback to mock (provider={p})")
        return _mock_search(query, seed_urls=seed_urls)

    try:
        pack = fn(query=query, api_key=api_key, max_results=max_results)
        pack["provider"] = p
        pack["query"] = query
        pack["results"] = (pack.get("results") or [])[:max_results]
        return pack
    except Exception as e:
        print(f"[web_search_adapter] provider={p} failed: {type(e).__name__}, fallback to mock")
        return _mock_search(query, seed_urls=seed_urls)


def run_multi_search(
    queries: list[dict[str, str]],
    provider: str,
    max_results_per_query: int = 5,
    seed_urls: list[str] | None = None,
) -> dict[str, Any]:
    seed_urls = seed_urls or []
    packs: list[dict[str, Any]] = []
    for q in queries:
        qq = str(q.get("query") or "").strip()
        if not qq:
            continue
        packs.append(run_search(qq, provider=provider, max_results=max_results_per_query, seed_urls=seed_urls))

    flat: list[dict[str, Any]] = []
    for p in packs:
        for r in p.get("results") or []:
            rr = dict(r)
            rr["query"] = p.get("query") or ""
            rr["provider"] = p.get("provider") or provider
            flat.append(rr)

    flat = _dedup_and_cap(flat, max_per_domain=2)

    url_kept = set([str(r.get("url") or "") for r in flat if str(r.get("url") or "")])
    trimmed_packs: list[dict[str, Any]] = []
    for p in packs:
        kept = []
        for r in p.get("results") or []:
            u = _norm_url(str(r.get("url") or ""))
            if u and u not in url_kept:
                continue
            rr = dict(r)
            rr["url"] = u
            rr["domain"] = str(rr.get("domain") or _domain_from_url(u) or "").lower()
            kept.append(rr)
        trimmed_packs.append({"provider": p.get("provider") or provider, "query": p.get("query") or "", "results": kept})

    return {"provider": provider, "generated_at": _utc_now_iso(), "query_packs": trimmed_packs, "flat_results": flat}

