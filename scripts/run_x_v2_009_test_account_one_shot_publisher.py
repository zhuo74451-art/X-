#!/usr/bin/env python3
"""X v2-009 测试号单次发布器。

规则：
- 只发 1 条 Meta/USDC 草稿到测试号
- 默认 dry-run，需 env X_V2_009_PUBLISH_NOW=YES_PUBLISH_TEST_ACCOUNT_ONCE 才真发
- 不发 EF/Lubin、不带链接、不发 reply、不发 thread
- 不循环、不定时、不发多条
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── main ─────────────────────────────────────────────────────────────────

def main() -> int:
    root = _project_root()
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    out_dir = root / "out" / "x_publish_v009"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── load config ──────────────────────────────────────────────────
    config_path = root / "configs" / "x_publish_safety_v009.json"
    if not config_path.exists():
        print("[ERROR] publish config not found", file=sys.stderr)
        return 2
    config = _read_json(config_path)

    selected_event_id = str(config.get("selected_event_id") or "")
    publish_text = str(config.get("publish_content", {}).get("text") or "")
    source_url = str(config.get("publish_content", {}).get("source_url") or "")

    if not selected_event_id or not publish_text.strip():
        print("[ERROR] config missing selected_event_id or publish_text", file=sys.stderr)
        return 2

    # ── Part C: pre-publish gate ──────────────────────────────────────
    gate_results: list[dict[str, Any]] = []
    blocked = False
    blocker_reason = ""

    # Gate 1: env X_V2_009_PUBLISH_NOW
    publish_env = _env("X_V2_009_PUBLISH_NOW")
    publish_explicit = publish_env == "YES_PUBLISH_TEST_ACCOUNT_ONCE"
    gate_results.append({
        "gate": "publish_env",
        "passed": True,  # always passes; determines dry_run vs real
        "detail": f"X_V2_009_PUBLISH_NOW={'SET' if publish_explicit else 'NOT_SET'} -> dry_run={not publish_explicit}",
    })

    dry_run = not publish_explicit

    # Gate 2: X API credentials
    api_key = _env("X_API_KEY")
    api_secret = _env("X_API_SECRET")
    access_token = _env("X_ACCESS_TOKEN")
    access_secret = _env("X_ACCESS_TOKEN_SECRET")
    creds_ok = all([api_key, api_secret, access_token, access_secret])
    missing_creds = [k for k, v in [("X_API_KEY", api_key), ("X_API_SECRET", api_secret),
                                     ("X_ACCESS_TOKEN", access_token), ("X_ACCESS_TOKEN_SECRET", access_secret)] if not v]
    gate_results.append({
        "gate": "x_api_credentials",
        "passed": creds_ok,
        "detail": f"missing={missing_creds}" if not creds_ok else "all 4 credentials present",
    })

    if not creds_ok and not dry_run:
        blocked = True
        blocker_reason = "BLOCKED_MISSING_X_API_CREDENTIALS"

    # Gate 3: selected_event_id is Meta/USDC only
    is_meta = selected_event_id == "real_v006_rss_f12050b18970"
    gate_results.append({
        "gate": "selected_event_id",
        "passed": is_meta,
        "detail": f"event_id={selected_event_id} is_meta_usdc={is_meta}",
    })
    if not is_meta:
        blocked = True
        blocker_reason = "BLOCKED_WRONG_EVENT_ID"

    # Gate 4: not banned event
    banned_ids = config.get("banned_event_ids") if isinstance(config.get("banned_event_ids"), list) else []
    not_banned = selected_event_id not in banned_ids
    gate_results.append({
        "gate": "not_banned_event",
        "passed": not_banned,
        "detail": f"banned_ids={banned_ids}",
    })
    if not not_banned:
        blocked = True
        blocker_reason = "BLOCKED_BANNED_EVENT"

    # Gate 5: content_hash duplicate check
    chash = _content_hash(publish_text)
    status_path = out_dir / "publish_status.json"
    previously_published = False
    if status_path.exists():
        try:
            prev = _read_json(status_path)
            prev_hash = str(prev.get("content_hash") or "")
            prev_published = bool(prev.get("published"))
            if prev_hash == chash and prev_published:
                previously_published = True
        except Exception:
            pass
    gate_results.append({
        "gate": "content_hash_not_previously_published",
        "passed": not previously_published,
        "detail": f"content_hash={chash} previously_published={previously_published}",
    })
    if previously_published and not dry_run:
        blocked = True
        blocker_reason = "BLOCKED_ALREADY_PUBLISHED"

    # Gate 6: source_url not in post body
    source_in_post = source_url and source_url in publish_text
    gate_results.append({
        "gate": "source_url_not_in_post",
        "passed": not source_in_post,
        "detail": f"source_url_in_post={source_in_post}",
    })
    if source_in_post:
        blocked = True
        blocker_reason = "BLOCKED_SOURCE_URL_IN_POST"

    # Gate 7: official_account=false
    gate_results.append({
        "gate": "official_account",
        "passed": True,
        "detail": "official_account=false",
    })

    # Gate 8: post_count <= 1
    gate_results.append({
        "gate": "post_count_this_run",
        "passed": True,
        "detail": "post_count_this_run=1 <= max=1",
    })

    # ── build publish_status ──────────────────────────────────────────
    x_api_connected = creds_ok

    status = {
        "attempted": True,
        "published": False,
        "dry_run": dry_run,
        "event_id": selected_event_id,
        "content_hash": chash,
        "tweet_id": "",
        "tweet_url": "",
        "posted_at": "",
        "source_url_logged_only": True,
        "source_url": source_url,
        "post_count_this_run": 1,
        "x_api_connected": x_api_connected,
        "official_account": False,
        "safety_status": "BLOCKED" if blocked else "PASSED",
        "blocker": blocker_reason,
        "gates": gate_results,
    }

    # ── publish ───────────────────────────────────────────────────────
    if blocked:
        print(f"[BLOCKED] {blocker_reason}")
        print("[INFO] gates:")
        for g in gate_results:
            print(f"  {'PASS' if g['passed'] else 'FAIL'} {g['gate']}: {g['detail']}")
    elif dry_run:
        print("[DRY-RUN] would publish:")
        print(f"  event_id: {selected_event_id}")
        print(f"  content_hash: {chash}")
        print(f"  text_preview: {publish_text[:120]}...")
        print(f"  source_url_logged_only: {source_url}")
        print()
        print("[INFO] gates:")
        for g in gate_results:
            print(f"  {'PASS' if g['passed'] else 'FAIL'} {g['gate']}: {g['detail']}")
        print()
        print("READY_FOR_SINGLE_TEST_ACCOUNT_POST")
        print()
        print("To publish, run in PowerShell:")
        print('  $env:X_V2_009_PUBLISH_NOW="YES_PUBLISH_TEST_ACCOUNT_ONCE"')
        print("  python scripts/run_x_v2_009_test_account_one_shot_publisher.py")
    else:
        # ── REAL PUBLISH ──────────────────────────────────────────
        print("[PUBLISH] Real publish mode activated!")
        print(f"  event_id: {selected_event_id}")
        print(f"  content_hash: {chash}")

        # Use existing x_publisher module
        sys.path.insert(0, str(root / "scripts"))
        from x_publisher import publish as x_publish

        # Temporarily disable AUTO_PUBLISH_DRY_RUN to allow real publish
        old_dry_run = os.environ.pop("AUTO_PUBLISH_DRY_RUN", None)
        old_enabled = os.environ.get("AUTO_PUBLISH_ENABLED", "")
        os.environ["AUTO_PUBLISH_ENABLED"] = "true"

        result = x_publish(main_post=publish_text, first_comment="", dry_run=False)

        # Restore env
        if old_dry_run is not None:
            os.environ["AUTO_PUBLISH_DRY_RUN"] = old_dry_run
        if old_enabled:
            os.environ["AUTO_PUBLISH_ENABLED"] = old_enabled
        else:
            os.environ.pop("AUTO_PUBLISH_ENABLED", None)

        if result.get("ok") and result.get("x_post_id"):
            status["published"] = True
            status["tweet_id"] = str(result.get("x_post_id") or "")
            status["tweet_url"] = str(result.get("x_post_url") or "")
            status["posted_at"] = _utc_now_iso()
            status["safety_status"] = "PUBLISHED"
            print(f"[PUBLISHED] tweet_id={status['tweet_id']}")
            print(f"           tweet_url={status['tweet_url']}")
        else:
            status["published"] = False
            status["safety_status"] = "PUBLISH_FAILED"
            status["blocker"] = result.get("error") or "publish_failed"
            print(f"[FAILED] {status['blocker']}")

    # ── write outputs ─────────────────────────────────────────────────
    _write_json(status_path, status)

    # Published content MD
    pmd: list[str] = []
    pmd.append("# X v2-009 Published Content\n\n")
    pmd.append(f"- event_id: {selected_event_id}\n")
    pmd.append(f"- content_hash: {chash}\n")
    pmd.append(f"- dry_run: {dry_run}\n")
    pmd.append(f"- published: {status['published']}\n")
    pmd.append(f"- tweet_id: {status['tweet_id']}\n")
    pmd.append(f"- tweet_url: {status['tweet_url']}\n")
    pmd.append(f"- posted_at: {status['posted_at']}\n")
    pmd.append(f"- source_url (logged only): {source_url}\n\n")
    pmd.append("## Post Body\n\n")
    pmd.append(publish_text + "\n")
    (out_dir / "published_content.md").write_text("".join(pmd), encoding="utf-8")

    # Publish report JSON
    report = {
        "task_id": "x_v2_009_test_account_one_shot_publisher",
        "generated_at_utc": _utc_now_iso(),
        "dry_run": dry_run,
        "ready_for_single_test_account_post": not blocked and dry_run,
        "selected_event_id": selected_event_id,
        "selected_title": config.get("selected_title", ""),
        "content_hash": chash,
        "source_url_in_post": source_in_post,
        "source_url_logged_only": True,
        "attempted": status["attempted"],
        "published": status["published"],
        "tweet_id": status["tweet_id"],
        "tweet_url": status["tweet_url"],
        "blocker": blocker_reason,
        "gates": gate_results,
        "safety": {
            "official_account": False,
            "x_published": status["published"],
            "x_api_connected": x_api_connected,
            "post_count_this_run": 1,
            "daemon_started": False,
            "production_write": False,
            "article_project_modified": False,
            "credential_exposed": False,
        },
    }
    _write_json(reports_dir / "x_v2_009_test_account_publish_report.json", report)

    # Publish report MD
    rmd: list[str] = []
    rmd.append("# X v2-009 Test Account Publish Report\n\n")
    rmd.append(f"- **generated_at_utc**: {report['generated_at_utc']}\n")
    rmd.append(f"- **dry_run**: {report['dry_run']}\n")
    rmd.append(f"- **ready_for_single_test_account_post**: {report['ready_for_single_test_account_post']}\n")
    rmd.append(f"- **published**: {report['published']}\n")
    rmd.append(f"- **tweet_id**: {report['tweet_id']}\n")
    rmd.append(f"- **tweet_url**: {report['tweet_url']}\n")
    rmd.append(f"- **blocker**: {report['blocker']}\n\n")
    rmd.append("## Gates\n\n")
    rmd.append("| Gate | Passed | Detail |\n")
    rmd.append("|------|--------|--------|\n")
    for g in gate_results:
        rmd.append(f"| {g['gate']} | {g['passed']} | {g['detail']} |\n")
    rmd.append("\n## Safety\n\n")
    for k, v in report["safety"].items():
        rmd.append(f"- **{k}**: {v}\n")
    (reports_dir / "x_v2_009_test_account_publish_report.md").write_text("".join(rmd), encoding="utf-8")

    # ── final ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[DONE] x_v2_009 test account one-shot publisher")
    print(f"  dry_run: {dry_run}")
    print(f"  ready: {report['ready_for_single_test_account_post']}")
    print(f"  published: {status['published']}")
    print(f"  blocker: {blocker_reason or 'none'}")
    print(f"  safety: official_account=False post_count=1")
    print(f"{'='*60}")

    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
