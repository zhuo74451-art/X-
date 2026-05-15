from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_sources_cfg() -> dict[str, Any]:
    p = _project_root() / "configs" / "integration_sources.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _build_url(base_url: str, path: str, params: dict[str, Any] | None) -> str:
    base_url = (base_url or "").rstrip("/")
    path = (path or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    url = base_url + path
    if params:
        q = {k: v for k, v in params.items() if v is not None and str(v).strip() != ""}
        if q:
            url = url + "?" + urllib.parse.urlencode(q, doseq=True)
    return url


def _http_get_json(url: str, timeout_s: int = 20) -> Any:
    req = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"http error: {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"url error: {e.reason}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError("invalid json response") from e


def _pick_delivery_payload(item: dict[str, Any]) -> dict[str, Any]:
    dp = item.get("delivery_payload")
    return dp if isinstance(dp, dict) else {}


def normalize_to_hot_input(item: dict[str, Any]) -> dict[str, Any]:
    dp = _pick_delivery_payload(item)

    title = (dp.get("title") or item.get("zh_title") or "").strip()
    short_title = (dp.get("short_title") or item.get("zh_short_title") or "").strip()
    raw_text = (dp.get("body") or item.get("zh_body") or "").strip()

    source_url = (item.get("canonical_url") or item.get("article_url") or "").strip()

    return {
        "input_id": str(item.get("tweet_id") or "").strip(),
        "source_platform": "integration_api",
        "source_name": str(item.get("source") or "").strip(),
        "source_type": "internal_newsflash",
        "content_type": str(item.get("content_type") or "").strip(),
        "title": title,
        "short_title": short_title,
        "raw_text": raw_text,
        "source_url": source_url,
        "raw_title": str(item.get("raw_title") or "").strip(),
        "raw_author": str(item.get("raw_author") or "").strip(),
        "received_at": str(item.get("received_at") or "").strip(),
        "published_at": str(item.get("published_at") or "").strip(),
        "event_fingerprint": str(item.get("event_fingerprint") or "").strip(),
        "pipeline_stage": str(item.get("pipeline_stage") or "").strip(),
        "category": str(item.get("hermes_category") or "").strip(),
    }


def fetch_pool(
    *,
    pool: str,
    source_key: str = "coinmeta_newsflash_local",
    limit: int | None = None,
    offset: int | None = None,
    since: str | None = None,
    source: str | None = None,
    content_type: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    cfg = _load_sources_cfg().get(source_key) or {}
    if not cfg.get("enabled", False):
        return []

    base_url = str(cfg.get("base_url") or "").strip()
    if pool == "ready":
        path = str(cfg.get("ready_path") or "").strip()
    elif pool == "published":
        path = str(cfg.get("published_path") or "").strip()
    else:
        raise ValueError("pool must be ready or published")

    params: dict[str, Any] = {
        "limit": limit if limit is not None else cfg.get("default_limit"),
        "offset": offset,
        "since": since,
        "source": source,
        "content_type": content_type,
        "q": q,
    }
    url = _build_url(base_url, path, params)
    data = _http_get_json(url)

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    out: list[dict[str, Any]] = []
    for x in items:
        if isinstance(x, dict):
            out.append(x)
    return out


def fetch_item(*, tweet_id: str, source_key: str = "coinmeta_newsflash_local") -> dict[str, Any]:
    cfg = _load_sources_cfg().get(source_key) or {}
    if not cfg.get("enabled", False):
        return {}

    base_url = str(cfg.get("base_url") or "").strip()
    item_path = str(cfg.get("item_path") or "").strip()
    path = item_path.format(tweet_id=urllib.parse.quote(str(tweet_id)))
    url = _build_url(base_url, path, None)
    data = _http_get_json(url)
    return data if isinstance(data, dict) else {}

