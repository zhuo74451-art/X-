from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from web_search_adapter import run_search


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_filename(s: str) -> str:
    t = (s or "").strip()
    t = re.sub(r"[^a-zA-Z0-9_\-]+", "_", t)
    return t.strip("_") or "item"

MOJIBAKE_MARKERS = [
    "\ufffd",
    "鍗",
    "鍔",
    "鐗",
    "鐡",
    "钀",
    "涔",
    "鏋",
    "缇",
]


def _has_mojibake(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if any(m in t for m in MOJIBAKE_MARKERS):
        return True
    return False


def _clean_for_query(s: str) -> str:
    t = (s or "").strip()
    t = re.sub(r"[\u0000-\u001f]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _domain_from_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _tier_for_domain(domain: str) -> str:
    d = (domain or "").lower().strip()
    if not d:
        return "unknown"
    p0 = [
        "sec.gov",
        ".gov",
        "court",
        "etherscan.io",
        "arbiscan.io",
        "polygonscan.com",
        "bscscan.com",
        "solscan.io",
        "blockaid.io",
        "certik.com",
        "slowmist.com",
        "chainalysis.com",
    ]
    if any(x in d for x in p0):
        return "P0"
    p1 = [
        "reuters.com",
        "bloomberg.com",
        "wsj.com",
        "apnews.com",
        "ft.com",
        "cnbc.com",
        "coindesk.com",
        "theblock.co",
    ]
    if any(x in d for x in p1):
        return "P1"
    p2 = [
        "cointelegraph.com",
        "decrypt.co",
        "messari.io",
        "jin10.com",
        "odaily.news",
    ]
    if any(x in d for x in p2):
        return "P2"
    if "t.me" in d or "telegram" in d:
        return "P3"
    return "unknown"


def _provider_key_env(provider: str) -> str:
    p = (provider or "").strip().lower()
    if p == "tavily":
        return "TAVILY_API_KEY"
    if p == "brave":
        return "BRAVE_SEARCH_API_KEY"
    if p == "serpapi":
        return "SERPAPI_API_KEY"
    return ""


def _extract_keywords(text: str) -> list[str]:
    t = (text or "").strip()
    out: list[str] = []
    if not t:
        return out

    known = [
        "blockaid",
        "peckshield",
        "certik",
        "slowmist",
        "exploit",
        "attack",
        "bridge",
        "ethereum",
        "verus",
        "tornado cash",
        "matrixport",
        "hyperliquid",
        "arkham",
        "bitcoin office",
        "el salvador",
        "萨尔瓦多",
        "bitcoin",
        "btc",
        "eth",
        "forsage",
        "doj",
        "justice.gov",
        "美联储",
        "fed",
        "cpi",
        "sec",
        "etf",
        "stablecoin",
        "中美",
        "出口管制",
        "芯片",
        "h200",
        "制裁",
        "引渡",
        "指控",
        "被盗",
        "攻击",
        "漏洞",
        "桥",
    ]
    tl = t.lower()
    for k in known:
        if k.lower() in tl:
            out.append(k)

    m = re.findall(r"\$[A-Za-z]{2,10}", t)
    for x in m[:6]:
        if x not in out:
            out.append(x)

    return out[:12]


def _detect_event_type(text: str) -> str:
    t = (text or "").lower()
    if any(x in t for x in ["blockaid", "bridge", "exploit", "attack", "hacked", "被盗", "攻击", "漏洞", "verus"]):
        return "security_attack"
    if any(x in t for x in ["forsage", "extradit", "wire fraud", "justice.gov", "doj", "引渡", "电信欺诈", "起诉", "指控"]):
        return "legal_case"
    if any(x in t for x in ["matrixport", "hyperliquid", "arkham", "lookonchain", "0x", "地址", "钱包", "wallet"]):
        return "onchain_position"
    if any(x in t for x in ["萨尔瓦多", "el salvador", "bitcoin office", "持有", "增持", "holdings"]):
        if any(x in t for x in ["btc", "bitcoin", "比特币"]):
            return "country_btc_reserve"
    return "generic"


def _extract_amount_tokens(text: str) -> list[str]:
    t = (text or "").lower()
    nums = re.findall(r"\b\d{4,}\b", t)
    return nums[:4]


def _extract_entities(text: str, event_type: str) -> list[str]:
    t = (text or "")
    tl = t.lower()
    out: list[str] = []

    def add(x: str) -> None:
        if x and x not in out:
            out.append(x)

    if "萨尔瓦多" in t or "el salvador" in tl:
        add("El Salvador")
    if any(x in tl for x in ["bitcoin office", "bitcoin.gob.sv", "bitcoin.gob"]):
        add("Bitcoin Office")
    if any(x in tl for x in ["btc", "bitcoin", "比特币"]):
        add("BTC")
    if any(x in tl for x in ["eth", "ethereum", "以太坊"]):
        add("ETH")
    if "matrixport" in tl:
        add("Matrixport")
    if "hyperliquid" in tl:
        add("Hyperliquid")
    if "arkham" in tl:
        add("Arkham")
    if "blockaid" in tl:
        add("Blockaid")
    if "verus" in tl:
        add("Verus")
    if "forsage" in tl:
        add("Forsage")
    if "justice.gov" in tl or "doj" in tl:
        add("DOJ")

    m = re.findall(r"\$[A-Za-z]{2,10}", t)
    for x in m[:4]:
        add(x.upper())

    if event_type == "generic":
        for k in _extract_keywords(t):
            if k and k not in out:
                add(k)
    return out[:10]


MEDIA_WORDS = {"reuters", "coindesk", "theblock", "bloomberg", "wsj", "cnbc", "ap"}


def _is_numeric_orphan_query(q: str) -> bool:
    t = (q or "").strip().lower()
    if not t:
        return True
    toks = [x for x in re.split(r"[\s/|,]+", t) if x]
    toks = [x for x in toks if x not in MEDIA_WORDS and x not in {"official", "source", "link", "statement", "report", "filing"}]
    if not toks:
        return True
    non_num = [x for x in toks if re.search(r"[a-z\u4e00-\u9fff]", x)]
    if non_num:
        return False
    return True


def _build_queries_by_type(title: str, summary: str) -> list[str]:
    base = _clean_for_query(title)
    ctx = _clean_for_query(summary)
    text = (base + "\n" + ctx).strip()
    et = _detect_event_type(text)
    tl = text.lower()

    queries: list[str] = []
    if et == "country_btc_reserve" and any(x in tl for x in ["萨尔瓦多", "el salvador"]):
        nums = re.findall(r"\b\d{3,6}\b", tl)
        n = nums[0] if nums else ""
        if n:
            queries = [
                f"El Salvador holds {n} BTC Bitcoin Office",
                f"El Salvador Bitcoin holdings {n} BTC",
                "site:bitcoin.gob.sv El Salvador Bitcoin holdings",
                f"site:x.com Bitcoin Office El Salvador {n} BTC",
            ]
        else:
            queries = [
                "El Salvador Bitcoin holdings Bitcoin Office",
                "site:bitcoin.gob.sv El Salvador Bitcoin holdings",
                "site:x.com Bitcoin Office El Salvador BTC",
            ]
    elif et == "onchain_position" and "matrixport" in tl:
        queries = [
            "Matrixport related address ETH long position unrealized loss",
            "Matrixport ETH long position Hyperliquid",
            "Matrixport ETH wallet long position liquidation",
            "site:arkhamintelligence.com Matrixport ETH address",
            "site:x.com Matrixport ETH long address",
        ]
    elif et == "security_attack":
        queries = [
            "Blockaid Verus Ethereum bridge 11.58 million attack",
            "Verus Ethereum bridge exploit Blockaid",
            "Blockaid official X Verus bridge attack",
            "Verus Ethereum bridge attack on-chain transaction",
        ]
    elif et == "legal_case":
        queries = [
            "Ukrainian woman Forsage extradited US wire fraud charges",
            "Forsage Ukraine woman extradited DOJ wire fraud",
            "site:justice.gov Forsage extradited wire fraud Ukraine",
            "site:sec.gov Forsage charges Ukraine",
        ]
    else:
        ents = _extract_entities(text, et)
        k = " ".join(ents[:6]).strip()
        if k:
            queries = [
                f"{k} source",
                f"{k} Reuters",
                f"{k} CoinDesk",
            ]
        else:
            queries = [base] if base else []

    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        qq = _clean_for_query(q)
        if not qq:
            continue
        key = qq.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(qq)
    return out[:5]


def _build_queries_2p1(title: str, summary: str) -> tuple[list[str], str]:
    qs = _build_queries_by_type(title, summary)
    general = qs[:2] if qs else []

    text = ((title or "") + "\n" + (summary or "")).lower()
    if any(x in text for x in ["blockaid", "exploit", "attack", "bridge", "verus", "被盗", "攻击"]):
        targeted = "site:blockaid.io Verus Ethereum bridge attack"
    elif any(x in text for x in ["萨尔瓦多", "el salvador", "bitcoin office"]):
        targeted = "site:bitcoin.gob.sv El Salvador Bitcoin holdings"
    elif "matrixport" in text:
        targeted = "site:arkhamintelligence.com Matrixport ETH address"
    elif "forsage" in text:
        targeted = "site:justice.gov Forsage extradited wire fraud"
    else:
        targeted = f"site:reuters.com {_clean_for_query(title)}".strip()

    targeted = re.sub(r"\s+", " ", targeted).strip()
    return general, targeted


def _x_handle_from_url(url: str) -> str:
    try:
        p = urlparse(url)
    except Exception:
        return ""
    if (p.netloc or "").lower().endswith("x.com"):
        path = (p.path or "").strip("/")
        if not path:
            return ""
        head = path.split("/")[0].strip()
        if head.lower() in {"search", "i"}:
            return ""
        return head.lower()
    return ""


def _allowed_x_handles(entities: list[str]) -> set[str]:
    e = {x.lower() for x in (entities or [])}
    allow: set[str] = set()
    if "blockaid" in e:
        allow |= {"blockaid_", "blockaid"}
    if "bitcoin office" in e or "el salvador" in e:
        allow |= {"bitcoinofficesv", "bitcoinoffice", "bitcoin"}
    if "arkham" in e:
        allow |= {"arkham"}
    return allow


def _tier_for_url(domain: str, url: str, entities: list[str]) -> str:
    d = (domain or "").lower().strip()
    u = (url or "").strip()
    if d == "x.com":
        if "/search" in u or "x.com/search" in u:
            return "P3"
        h = _x_handle_from_url(u)
        if h and h in _allowed_x_handles(entities):
            return "P0"
        return "P3"
    return _tier_for_domain(d)


def _entity_match_score(*, title: str, snippet: str, url: str, entities: list[str], amounts: list[str]) -> int:
    t = (title or "").lower()
    s = (snippet or "").lower()
    u = (url or "").lower()
    blob = f"{t}\n{s}\n{u}"
    score = 0
    for ent in entities or []:
        e = ent.lower().strip()
        if not e:
            continue
        if e in blob:
            score += 1
    for a in amounts or []:
        aa = str(a).strip().lower()
        if aa and aa in blob:
            score += 1
    return score


def _is_relevant_candidate(*, ems: int, entities: list[str], title: str, snippet: str, url: str) -> tuple[bool, str]:
    if ems >= 2:
        return True, ""
    blob = f"{(title or '')}\n{(snippet or '')}\n{(url or '')}".lower()
    has_asset = any(x.lower() in blob for x in ["btc", "bitcoin", "eth", "ethereum", "usdt", "usdc", "sol"])
    if ems >= 1 and has_asset:
        return True, ""
    if not entities:
        return False, "missing_entities"
    return False, "insufficient_entity_match"


@dataclass
class Candidate:
    title: str
    url: str
    snippet: str
    reason: str


def _mock_candidates(title: str, summary: str) -> list[Candidate]:
    text = ((title or "") + "\n" + (summary or "")).lower()
    out: list[Candidate] = []

    def add(t: str, u: str, s: str, r: str) -> None:
        out.append(Candidate(title=t, url=u, snippet=s, reason=r))

    if any(x in text for x in ["blockaid", "exploit", "attack", "bridge", "被盗", "攻击"]):
        add("Blockaid (mock) - Security Notice", "https://blockaid.io/security/verus-ethereum-bridge", "mock: security notice page", "security vendor official site (mock)")
        add("Blockaid X (mock)", "https://x.com/Blockaid_", "mock: official account post", "official X account (mock)")
        add("Etherscan (mock) - attacker address", "https://etherscan.io/address/0x0000000000000000000000000000000000000000", "mock: on-chain address page", "on-chain explorer anchor (mock)")
        add("The Block (mock) - Coverage", "https://www.theblock.co/post/mock-verus-bridge-attack", "mock: media coverage", "tier-1 crypto media (mock)")
        add("CoinDesk (mock) - Coverage", "https://www.coindesk.com/mock-verus-bridge-attack", "mock: media coverage", "tier-1 crypto media (mock)")
    elif any(x in text for x in ["美联储", "fed", "利率", "cpi", "pce", "非农", "通胀"]):
        add("Federal Reserve (mock) - Statement", "https://www.federalreserve.gov/monetarypolicy/mock-statement.htm", "mock: official release", "official institution (mock)")
        add("Reuters (mock) - Coverage", "https://www.reuters.com/world/us/mock-fed-policy", "mock: mainstream coverage", "tier-1 mainstream media (mock)")
        add("WSJ (mock) - Coverage", "https://www.wsj.com/mock-fed-policy", "mock: mainstream coverage", "tier-1 mainstream media (mock)")
        add("CNBC (mock) - Coverage", "https://www.cnbc.com/mock-fed-policy", "mock: mainstream coverage", "tier-1 mainstream media (mock)")
    elif any(x in text for x in ["引渡", "指控", "法院", "起诉", "庭审", "法官"]):
        add("US DOJ (mock) - Press Release", "https://www.justice.gov/usao/mock-press-release", "mock: gov press release", "government/justice department (mock)")
        add("Court Listener (mock) - Docket", "https://www.courtlistener.com/docket/mock", "mock: court docket page", "court filing index (mock)")
        add("Reuters (mock) - Coverage", "https://www.reuters.com/world/us/mock-extradition-case", "mock: mainstream coverage", "tier-1 mainstream media (mock)")
    else:
        add("Reuters (mock) - Coverage", "https://www.reuters.com/markets/mock", "mock: mainstream coverage", "tier-1 mainstream media (mock)")
        add("CoinDesk (mock) - Coverage", "https://www.coindesk.com/mock", "mock: crypto coverage", "tier-1 crypto media (mock)")
        add("The Block (mock) - Coverage", "https://www.theblock.co/post/mock", "mock: crypto coverage", "tier-1 crypto media (mock)")

    return out[:7]


def _build_cost_estimate(*, provider: str, model_runtime: str, queries: list[str]) -> dict[str, Any]:
    calls = min(3, len(queries))
    est_usd = 0.0
    if provider != "mock":
        est_usd = round(calls * 0.01, 4)
    return {
        "search_calls": calls if provider != "mock" else 0,
        "input_tokens_est": 800 if model_runtime != "mock" else 0,
        "output_tokens_est": 400 if model_runtime != "mock" else 0,
        "estimated_usd": est_usd,
    }


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"clusters": {}, "queries": {}}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {"clusters": {}, "queries": {}}
    except json.JSONDecodeError:
        return {"clusters": {}, "queries": {}}


def _save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_ok(ts: str, ttl_hours: int = 24) -> bool:
    s = (ts or "").strip()
    if not s:
        return False
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - dt.astimezone(timezone.utc) <= timedelta(hours=ttl_hours)


def _load_query_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_query_cache(path: Path, cache: dict[str, Any]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _query_cache_key(provider: str, query: str) -> str:
    return f"{(provider or '').strip().lower()}|{(query or '').strip().lower()}"


def _search_with_cache(
    *,
    provider: str,
    query: str,
    max_results: int,
    query_cache: dict[str, Any],
    now_iso: str,
    ttl_hours: int = 24,
) -> tuple[dict[str, Any], bool]:
    key = _query_cache_key(provider, query)
    prev = query_cache.get(key)
    if isinstance(prev, dict) and _cache_ok(str(prev.get("cached_at") or ""), ttl_hours=ttl_hours):
        pack = {"provider": provider, "query": query, "results": prev.get("results") or []}
        return pack, True

    pack = run_search(query=query, provider=provider, max_results=max_results, seed_urls=None)
    results = pack.get("results") if isinstance(pack.get("results"), list) else []
    query_cache[key] = {"query": query, "provider": provider, "results": results, "cached_at": now_iso}
    return pack, False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--provider", default="")
    ap.add_argument("--max-items", type=int, default=20)
    ap.add_argument("--max-searches-per-item", type=int, default=3)
    ap.add_argument("--max-total-searches", type=int, default=100)
    ap.add_argument("--force", action="store_true", default=False)
    args = ap.parse_args()

    provider = (args.provider or os.getenv("SEARCH_PROVIDER") or "mock").strip().lower()
    model_runtime = (os.getenv("MODEL_RUNTIME") or "mock").strip()

    if provider == "anthropic_web_search":
        print("anthropic_web_search is reserved for future version; use tavily/brave/serpapi/mock.")
        raise SystemExit(2)
    if provider not in {"mock", "tavily", "brave", "serpapi"}:
        print(f"[source_research_auto_search] unknown provider={provider}. Use tavily/brave/serpapi/mock.")
        raise SystemExit(2)

    real_search_enabled = provider != "mock"
    if real_search_enabled:
        key_env = _provider_key_env(provider)
        if not key_env:
            print(f"[source_research_auto_search] provider={provider} missing key mapping")
            raise SystemExit(2)
        if not (os.getenv(key_env) or "").strip():
            print(f"[source_research_auto_search] missing {key_env} for provider={provider}")
            raise SystemExit(2)

    if model_runtime != "mock":
        print(f"[source_research_auto_search] model_runtime={model_runtime} is disabled in v0.1 (no model calls). Set MODEL_RUNTIME=mock.")
        raise SystemExit(2)

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = _project_root() / run_dir
    if not run_dir.exists():
        raise SystemExit(2)

    events_path = run_dir / "events.jsonl"
    events = _read_jsonl(events_path)

    source_research_events: list[dict[str, Any]] = []
    for e in events:
        q = str(e.get("selected_queue") or e.get("cluster_queue") or "").strip()
        if q == "source_research":
            source_research_events.append(e)

    out_dir = run_dir / "source_packs"
    _ensure_dir(out_dir)
    cache_path = out_dir / "_cache.json"
    cache = _load_cache(cache_path)
    if not isinstance(cache.get("clusters"), dict):
        cache["clusters"] = {}
    if not isinstance(cache.get("queries"), dict):
        cache["queries"] = {}

    query_cache_path = out_dir / "_query_cache.json"
    query_cache = _load_query_cache(query_cache_path)

    rows: list[dict[str, Any]] = []
    processed = 0
    total_search_calls_used = 0
    stopped_by_budget = False
    for e in source_research_events:
        if processed >= max(0, int(args.max_items)):
            break
        if total_search_calls_used >= max(0, int(args.max_total_searches)):
            stopped_by_budget = True
            break

        cluster_id = str(e.get("event_cluster_id") or "").strip()
        title = str(e.get("cluster_title") or "").strip()
        summary = str(e.get("raw_summary") or "").strip()
        if not cluster_id:
            continue

        prev = cache["clusters"].get(cluster_id) if isinstance(cache.get("clusters"), dict) else None
        if (not args.force) and isinstance(prev, dict) and _cache_ok(str(prev.get("checked_at") or "")):
            rows.append(
                {
                    "event_cluster_id": cluster_id,
                    "title": title,
                    "status": "cached",
                    "pack_path": str(out_dir / f"{cluster_id}.json"),
                }
            )
            continue

        now = _utc_now_iso()
        text_for_detect = _clean_for_query(title + "\n" + summary)
        query_quality = "ok"
        if _has_mojibake(title) or _has_mojibake(summary):
            query_quality = "bad_encoding"

        general_qs, targeted_q = _build_queries_2p1(title, summary)
        max_searches_per_item = max(0, int(args.max_searches_per_item))

        search_calls_used = 0
        raw_search_packs: list[dict[str, Any]] = []
        results_flat: list[dict[str, Any]] = []

        entities = _extract_entities(text_for_detect, _detect_event_type(text_for_detect))
        amounts = _extract_amount_tokens(text_for_detect)

        queries_all = _build_queries_by_type(title, summary)
        queries_all = [q for q in queries_all if not _is_numeric_orphan_query(q)]
        queries = queries_all[:5]

        skipped_bad_query_count = 0
        valid_query_count = 0
        if query_quality != "ok":
            skipped_bad_query_count = len(queries)
            valid_query_count = 0
        else:
            valid_query_count = len(queries)

        if provider != "mock" and query_quality == "ok" and queries:
            for qq in list(general_qs)[:2]:
                if search_calls_used >= max_searches_per_item:
                    break
                if total_search_calls_used >= max(0, int(args.max_total_searches)):
                    stopped_by_budget = True
                    break
                if _is_numeric_orphan_query(qq) or _has_mojibake(qq):
                    skipped_bad_query_count += 1
                    continue
                pack, from_cache = _search_with_cache(
                    provider=provider,
                    query=qq,
                    max_results=6,
                    query_cache=query_cache,
                    now_iso=now,
                    ttl_hours=24,
                )
                raw_search_packs.append({"query": qq, "provider": provider, "from_cache": from_cache, "results": pack.get("results") or []})
                if not from_cache:
                    search_calls_used += 1
                    total_search_calls_used += 1
                for r in pack.get("results") or []:
                    if isinstance(r, dict):
                        results_flat.append(r)
        elif provider != "mock" and query_quality != "ok":
            raw_search_packs.append({"query": "", "provider": provider, "from_cache": True, "results": [], "skipped": "bad_encoding"})

        candidates = _mock_candidates(title, summary) if provider == "mock" else []
        candidate_sources: list[dict[str, Any]] = []
        if provider == "mock":
            for idx, c in enumerate(candidates, start=1):
                dom = _domain_from_url(c.url)
                tier = _tier_for_url(dom, c.url, entities)
                ms = 60
                if tier == "P0":
                    ms = 85
                elif tier == "P1":
                    ms = 75
                elif tier == "P2":
                    ms = 60
                elif tier == "P3":
                    ms = 45
                candidate_sources.append(
                    {
                        "title": c.title,
                        "url": c.url,
                        "domain": dom,
                        "published_at": "",
                        "snippet": c.snippet,
                        "source_tier": tier,
                        "match_score": ms,
                        "reason": c.reason,
                        "is_real_search_result": False,
                        "raw_rank": idx,
                        "provider": "mock",
                        "entity_match_score": _entity_match_score(
                            title=c.title, snippet=c.snippet, url=c.url, entities=entities, amounts=amounts
                        ),
                        "is_irrelevant": False,
                        "irrelevant_reason": "",
                    }
                )
        else:
            for idx, r in enumerate(results_flat, start=1):
                url = str(r.get("url") or "").strip()
                dom = str(r.get("domain") or _domain_from_url(url) or "").strip()
                tier = _tier_for_url(dom, url, entities)
                ms = 55
                if tier == "P0":
                    ms = 80
                elif tier == "P1":
                    ms = 72
                elif tier == "P2":
                    ms = 58
                elif tier == "P3":
                    ms = 45
                candidate_sources.append(
                    {
                        "title": str(r.get("title") or "").strip(),
                        "url": url,
                        "domain": dom,
                        "published_at": str(r.get("published_at") or "").strip(),
                        "snippet": str(r.get("snippet") or "").strip(),
                        "source_tier": tier,
                        "match_score": ms,
                        "reason": "real_search_result",
                        "is_real_search_result": True,
                        "raw_rank": idx,
                        "provider": provider,
                        "entity_match_score": 0,
                        "is_irrelevant": False,
                        "irrelevant_reason": "",
                    }
                )

            def _tier_rank(tt: str) -> int:
                return {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "unknown": 4}.get(str(tt or ""), 4)

            for x in candidate_sources:
                if not isinstance(x, dict):
                    continue
                ems = _entity_match_score(
                    title=str(x.get("title") or ""),
                    snippet=str(x.get("snippet") or ""),
                    url=str(x.get("url") or ""),
                    entities=entities,
                    amounts=amounts,
                )
                ok, reason = _is_relevant_candidate(
                    ems=ems,
                    entities=entities,
                    title=str(x.get("title") or ""),
                    snippet=str(x.get("snippet") or ""),
                    url=str(x.get("url") or ""),
                )
                x["entity_match_score"] = int(ems)
                x["is_irrelevant"] = not ok
                x["irrelevant_reason"] = "" if ok else reason

            relevant = [x for x in candidate_sources if isinstance(x, dict) and not bool(x.get("is_irrelevant"))]
            relevant.sort(key=lambda z: (_tier_rank(str(z.get("source_tier") or "")), -int(z.get("entity_match_score") or 0), int(z.get("raw_rank") or 9999)))
            has_p0p1 = any(str(x.get("source_tier") or "") in {"P0", "P1"} for x in relevant)

            if (not stopped_by_budget) and (not has_p0p1) and (search_calls_used < max_searches_per_item) and targeted_q:
                if total_search_calls_used < max(0, int(args.max_total_searches)):
                    if _is_numeric_orphan_query(targeted_q) or _has_mojibake(targeted_q):
                        skipped_bad_query_count += 1
                    else:
                        pack, from_cache = _search_with_cache(
                            provider=provider,
                            query=targeted_q,
                            max_results=6,
                            query_cache=query_cache,
                            now_iso=now,
                            ttl_hours=24,
                        )
                        raw_search_packs.append(
                            {"query": targeted_q, "provider": provider, "from_cache": from_cache, "results": pack.get("results") or []}
                        )
                        if not from_cache:
                            search_calls_used += 1
                            total_search_calls_used += 1
                        for r in pack.get("results") or []:
                            if isinstance(r, dict):
                                url = str(r.get("url") or "").strip()
                                dom = str(r.get("domain") or _domain_from_url(url) or "").strip()
                                tier = _tier_for_url(dom, url, entities)
                                ms = 55
                                if tier == "P0":
                                    ms = 80
                                elif tier == "P1":
                                    ms = 72
                                elif tier == "P2":
                                    ms = 58
                                elif tier == "P3":
                                    ms = 45
                                candidate_sources.append(
                                    {
                                        "title": str(r.get("title") or "").strip(),
                                        "url": url,
                                        "domain": dom,
                                        "published_at": str(r.get("published_at") or "").strip(),
                                        "snippet": str(r.get("snippet") or "").strip(),
                                        "source_tier": tier,
                                        "match_score": ms,
                                        "reason": "real_search_result_targeted",
                                        "is_real_search_result": True,
                                        "raw_rank": len(candidate_sources) + 1,
                                        "provider": provider,
                                        "entity_match_score": 0,
                                        "is_irrelevant": False,
                                        "irrelevant_reason": "",
                                    }
                                )
                else:
                    stopped_by_budget = True

        if provider == "mock":
            for x in candidate_sources:
                if not isinstance(x, dict):
                    continue
                ems = _entity_match_score(
                    title=str(x.get("title") or ""),
                    snippet=str(x.get("snippet") or ""),
                    url=str(x.get("url") or ""),
                    entities=entities,
                    amounts=amounts,
                )
                ok, reason = _is_relevant_candidate(
                    ems=ems,
                    entities=entities,
                    title=str(x.get("title") or ""),
                    snippet=str(x.get("snippet") or ""),
                    url=str(x.get("url") or ""),
                )
                x["entity_match_score"] = int(ems)
                x["is_irrelevant"] = not ok
                x["irrelevant_reason"] = "" if ok else reason

        def _tier_rank2(tt: str) -> int:
            return {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "unknown": 4}.get(str(tt or ""), 4)

        relevant2 = [x for x in candidate_sources if isinstance(x, dict) and not bool(x.get("is_irrelevant"))]
        relevant2.sort(key=lambda z: (_tier_rank2(str(z.get("source_tier") or "")), -int(z.get("entity_match_score") or 0), int(z.get("raw_rank") or 9999)))
        irrelevant_candidate_count = sum(1 for x in candidate_sources if isinstance(x, dict) and bool(x.get("is_irrelevant")))
        top3 = relevant2[:3]
        top3_relevant_count = len(top3)
        top3_primary_source_found = any(str(x.get("source_tier") or "") in {"P0", "P1"} for x in top3)

        best = ""
        best_tier = ""
        for x in relevant2:
            if str(x.get("source_tier") or "") in {"P0", "P1"} and str(x.get("url") or "").strip():
                best = str(x.get("url") or "").strip()
                best_tier = str(x.get("source_tier") or "").strip()
                break

        if provider == "mock":
            verification_status = "mocked"
            why = "mock-only: 未真实联网检索与交叉印证；本结果仅用于校验流程与字段，不可作为发布依据。"
        else:
            if query_quality != "ok":
                verification_status = "not_found"
                why = "skipped real search due to query_quality=bad_encoding"
            else:
                verification_status = "partial" if relevant2 else "not_found"
                why = "real search found candidate sources; manual/Claude verification required"

        pack = {
            "event_title": title,
            "cluster_id": cluster_id,
            "selected_queue": "source_research",
            "search_queries": queries,
            "candidate_sources": candidate_sources,
            "best_source_url": best,
            "best_source_tier": best_tier,
            "verification_status": verification_status,
            "can_promote_to_queue_review": False,
            "why": why,
            "checked_at": now,
            "search_provider": provider,
            "model_runtime": model_runtime,
            "cost_estimate": _build_cost_estimate(provider=provider, model_runtime=model_runtime, queries=queries),
            "real_search_enabled": bool(real_search_enabled),
            "search_calls_used": int(search_calls_used),
            "budget_stopped": bool(stopped_by_budget),
            "query_quality": query_quality,
            "valid_query_count": int(valid_query_count),
            "skipped_bad_query_count": int(skipped_bad_query_count),
            "irrelevant_candidate_count": int(irrelevant_candidate_count),
            "top3_relevant_count": int(top3_relevant_count),
            "top3_primary_source_found": bool(top3_primary_source_found),
        }

        out_path = out_dir / f"{cluster_id}.json"
        out_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        cache["clusters"][cluster_id] = {"checked_at": now, "pack_path": str(out_path)}
        processed += 1
        rows.append({"event_cluster_id": cluster_id, "title": title, "status": "generated", "pack_path": str(out_path)})

    _save_cache(cache_path, cache)
    _save_query_cache(query_cache_path, query_cache)

    report_lines: list[str] = []
    report_lines.append("# Source Research Auto Search Report\n")
    report_lines.append(f"- checked_at_utc: {_utc_now_iso()}\n")
    report_lines.append(f"- run_dir: {str(run_dir)}\n")
    report_lines.append(f"- provider: {provider}\n")
    report_lines.append(f"- model_runtime: {model_runtime}\n")
    report_lines.append(f"- real_search_enabled: {str(bool(real_search_enabled)).lower()}\n")
    report_lines.append(f"- budget_stopped: {str(bool(stopped_by_budget)).lower()}\n")
    report_lines.append(f"- total_search_calls_used: {int(total_search_calls_used)}\n")
    report_lines.append(f"- source_research_events: {len(source_research_events)}\n")
    report_lines.append(f"- generated_packs: {sum(1 for x in rows if x.get('status') == 'generated')}\n")
    report_lines.append(f"- cached_packs: {sum(1 for x in rows if x.get('status') == 'cached')}\n")
    report_lines.append("\n## Items\n")
    if not rows:
        report_lines.append("- (empty)\n")
    else:
        for i, r in enumerate(rows, start=1):
            report_lines.append("\n---\n")
            report_lines.append(f"## Event {i}\n")
            report_lines.append(f"- event_cluster_id: {r.get('event_cluster_id')}\n")
            report_lines.append(f"- title: {r.get('title')}\n")
            report_lines.append(f"- status: {r.get('status')}\n")
            report_lines.append(f"- pack_path: {r.get('pack_path')}\n")
            if str(r.get("status")) == "generated":
                try:
                    p = json.loads(Path(str(r.get("pack_path"))).read_text(encoding="utf-8"))
                except Exception:
                    p = {}
                if isinstance(p, dict):
                    qs = p.get("search_queries") if isinstance(p.get("search_queries"), list) else []
                    cs = p.get("candidate_sources") if isinstance(p.get("candidate_sources"), list) else []
                    report_lines.append("\n### search_quality\n")
                    report_lines.append(f"- query_quality: {p.get('query_quality')}\n")
                    report_lines.append(f"- valid_query_count: {p.get('valid_query_count')}\n")
                    report_lines.append(f"- skipped_bad_query_count: {p.get('skipped_bad_query_count')}\n")
                    report_lines.append(f"- irrelevant_candidate_count: {p.get('irrelevant_candidate_count')}\n")
                    report_lines.append(f"- top3_relevant_count: {p.get('top3_relevant_count')}\n")
                    report_lines.append(f"- top3_primary_source_found: {str(bool(p.get('top3_primary_source_found'))).lower()}\n")
                    report_lines.append("\n### search_queries\n")
                    for q in qs[:6]:
                        report_lines.append(f"- {str(q)}\n")
                    report_lines.append("\n### candidate_sources (top 5)\n")
                    for x in cs[:5]:
                        if isinstance(x, dict):
                            report_lines.append(
                                f"- [{x.get('source_tier')}] {x.get('domain')} | ems={x.get('entity_match_score')} | irrelevant={str(bool(x.get('is_irrelevant'))).lower()} | {x.get('title')} | {x.get('url')}\n"
                            )
                    report_lines.append(f"\n- verification_status: {p.get('verification_status')}\n")
                    report_lines.append(f"- can_promote_to_queue_review: {str(bool(p.get('can_promote_to_queue_review'))).lower()}\n")

    (run_dir / "source_research_auto_search_report.md").write_text("".join(report_lines), encoding="utf-8")
    print(
        "[source_research_auto_search] ok"
        f" run_dir={run_dir}"
        f" source_research_events={len(source_research_events)}"
        f" generated={sum(1 for x in rows if x.get('status') == 'generated')}"
        f" cached={sum(1 for x in rows if x.get('status') == 'cached')}"
        f" out_dir={out_dir}"
    )


if __name__ == "__main__":
    main()
