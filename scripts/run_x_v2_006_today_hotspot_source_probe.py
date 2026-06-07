from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from adapters.import_integration_api import fetch_pool


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _latest_observed(items: list[dict[str, Any]]) -> str:
    latest: datetime | None = None
    for it in items:
        if not isinstance(it, dict):
            continue
        for k in ["published_at", "received_at", "observed_at", "created_at", "ts", "time"]:
            dt = _parse_dt(str(it.get(k) or ""))
            if dt is None:
                continue
            if latest is None or dt > latest:
                latest = dt
    return latest.replace(microsecond=0).isoformat() if latest else ""


def _filter_last_24h(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = _utc_now() - timedelta(hours=24)
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        dt = None
        for k in ["published_at", "received_at", "observed_at", "created_at", "ts", "time"]:
            dt = _parse_dt(str(it.get(k) or ""))
            if dt is not None:
                break
        if dt is None:
            continue
        if dt >= cutoff:
            out.append(it)
    return out


def _probe_integration(pool: str) -> dict[str, Any]:
    name = f"integration_{pool}"
    try:
        items = fetch_pool(pool=pool, limit=30)
        if not isinstance(items, list):
            items = []
        items_24h = _filter_last_24h([x for x in items if isinstance(x, dict)])
        return {
            "source_name": name,
            "reachable": True,
            "fetched_count": len(items_24h),
            "latest_observed_at": _latest_observed(items_24h),
            "error_or_blocked_reason": "",
            "selected_source_mode": "integration_published_real" if pool == "published" else "integration_ready_real",
        }
    except Exception as e:
        return {
            "source_name": name,
            "reachable": False,
            "fetched_count": 0,
            "latest_observed_at": "",
            "error_or_blocked_reason": str(e),
            "selected_source_mode": "integration_published_real" if pool == "published" else "integration_ready_real",
        }


def _http_get_json(url: str, timeout_s: int = 6) -> Any:
    req = urllib.request.Request(url=url, method="GET", headers={"User-Agent": "x_automation_v2"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    return json.loads(body)


def _probe_server_streams(url: str) -> dict[str, Any]:
    try:
        data = _http_get_json(url)
        items = []
        if isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            if isinstance(data.get("items"), list):
                items = [x for x in data["items"] if isinstance(x, dict)]
            elif isinstance(data.get("data"), list):
                items = [x for x in data["data"] if isinstance(x, dict)]
        items_24h = _filter_last_24h(items)
        return {
            "source_name": url,
            "reachable": True,
            "fetched_count": len(items_24h),
            "latest_observed_at": _latest_observed(items_24h),
            "error_or_blocked_reason": "",
            "selected_source_mode": "server_streams_real",
        }
    except Exception as e:
        return {
            "source_name": url,
            "reachable": False,
            "fetched_count": 0,
            "latest_observed_at": "",
            "error_or_blocked_reason": str(e),
            "selected_source_mode": "server_streams_real",
        }


def _probe_article_export(root: Path) -> dict[str, Any]:
    candidates = [
        root / "local_only" / "article_hotspot_export_real.jsonl",
        root / "local_only" / "article_hotspot_export.jsonl",
        root / "data" / "article_hotspot_export_real.jsonl",
        root / "data" / "article_hotspot_export.jsonl",
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        return {
            "source_name": "article_hotspot_export",
            "reachable": False,
            "fetched_count": 0,
            "latest_observed_at": "",
            "error_or_blocked_reason": "no_readable_export_found",
            "selected_source_mode": "article_hotspot_export_real",
        }
    p0 = existing[0]
    try:
        n = 0
        latest: str = ""
        cutoff = _utc_now() - timedelta(hours=24)
        with p0.open("r", encoding="utf-8") as f:
            for line in f:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                dt = _parse_dt(str(obj.get("observed_at") or obj.get("published_at") or obj.get("created_at") or ""))
                if dt is None or dt < cutoff:
                    continue
                n += 1
                iso = dt.replace(microsecond=0).isoformat()
                if not latest or iso > latest:
                    latest = iso
        return {
            "source_name": str(p0),
            "reachable": True,
            "fetched_count": n,
            "latest_observed_at": latest,
            "error_or_blocked_reason": "",
            "selected_source_mode": "article_hotspot_export_real",
        }
    except Exception as e:
        return {
            "source_name": str(p0),
            "reachable": False,
            "fetched_count": 0,
            "latest_observed_at": "",
            "error_or_blocked_reason": str(e),
            "selected_source_mode": "article_hotspot_export_real",
        }


def main() -> None:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    probes: list[dict[str, Any]] = []
    probes.append(_probe_integration("published"))
    probes.append(_probe_integration("ready"))

    stream_urls = [
        "http://127.0.0.1:8804/api/server-streams/news/latest",
        "http://127.0.0.1:8804/api/server-streams/flash/latest",
        "http://127.0.0.1:8804/api/server-streams/tg/latest",
    ]
    for u in stream_urls:
        probes.append(_probe_server_streams(u))

    probes.append(_probe_article_export(root))

    selected = None
    for p in probes:
        if p.get("reachable") is True and int(p.get("fetched_count") or 0) > 0:
            selected = p
            break
    if selected is None:
        selected = {
            "source_name": "",
            "reachable": False,
            "fetched_count": 0,
            "latest_observed_at": "",
            "error_or_blocked_reason": "BLOCKED_NO_REAL_SOURCE",
            "selected_source_mode": "blocked_no_real_source",
        }

    out = {
        "task_id": "x_v2_006_today_real_hotspot_dryrun",
        "generated_at_utc": _utc_now_iso(),
        "probes": probes,
        "selected_source": {
            "source_name": selected.get("source_name"),
            "selected_source_mode": selected.get("selected_source_mode"),
            "reachable": selected.get("reachable"),
            "fetched_count": selected.get("fetched_count"),
            "latest_observed_at": selected.get("latest_observed_at"),
            "blocked_reason": selected.get("error_or_blocked_reason") if selected.get("reachable") is not True else "",
        },
        "safety": {"x_api_connected": False, "x_published": False},
    }
    _write_json(reports_dir / "x_v2_006_today_source_probe_report.json", out)

    md: list[str] = []
    md.append("# X v2-006 Today Hotspot Source Probe Report\n\n")
    md.append(f"- generated_at_utc: {out.get('generated_at_utc')}\n\n")
    md.append("## Selected\n\n")
    sel = out["selected_source"]
    md.append(f"- source_name: {sel.get('source_name')}\n")
    md.append(f"- selected_source_mode: {sel.get('selected_source_mode')}\n")
    md.append(f"- reachable: {str(sel.get('reachable')).lower()}\n")
    md.append(f"- fetched_count: {sel.get('fetched_count')}\n")
    md.append(f"- latest_observed_at: {sel.get('latest_observed_at')}\n")
    if sel.get("blocked_reason"):
        md.append(f"- error_or_blocked_reason: {sel.get('blocked_reason')}\n")

    md.append("\n## Probes\n\n")
    for p in probes:
        md.append("---\n")
        md.append(f"- source_name: {p.get('source_name')}\n")
        md.append(f"- reachable: {str(p.get('reachable')).lower()}\n")
        md.append(f"- fetched_count: {p.get('fetched_count')}\n")
        md.append(f"- latest_observed_at: {p.get('latest_observed_at')}\n")
        if p.get("error_or_blocked_reason"):
            md.append(f"- error_or_blocked_reason: {p.get('error_or_blocked_reason')}\n")
        md.append(f"- selected_source_mode: {p.get('selected_source_mode')}\n")
    (reports_dir / "x_v2_006_today_source_probe_report.md").write_text("".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()

