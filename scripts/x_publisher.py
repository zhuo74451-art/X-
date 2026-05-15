from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


TWITTER_API_BASE = "https://api.twitter.com/2/tweets"


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _percent_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="~")


def _oauth_nonce() -> str:
    raw = f"{time.time_ns()}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _oauth_sign(method: str, url: str, params: dict[str, str], consumer_secret: str, token_secret: str) -> str:
    items = sorted((k, v) for k, v in params.items())
    param_str = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in items)
    base = "&".join([method.upper(), _percent_encode(url), _percent_encode(param_str)])
    key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}".encode("utf-8")
    sig = hmac.new(key, base.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(sig).decode("utf-8")


def _oauth_header(method: str, url: str, *, consumer_key: str, consumer_secret: str, token: str, token_secret: str) -> str:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _oauth_nonce(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    params["oauth_signature"] = _oauth_sign(method, url, params, consumer_secret, token_secret)
    header = ", ".join(f'{k}="{_percent_encode(v)}"' for k, v in params.items())
    return "OAuth " + header


def publish(
    *,
    main_post: str,
    first_comment: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    if dry_run or _env("AUTO_PUBLISH_DRY_RUN", "true").lower() == "true":
        return {
            "ok": True,
            "dry_run": True,
            "would_publish": True,
            "error": "",
            "x_post_id": "",
            "x_post_url": "",
            "note": "dry-run only",
            "preview": {
                "main_post": main_post,
                "first_comment": first_comment,
            },
        }

    enabled = _env("AUTO_PUBLISH_ENABLED", "false").lower() == "true"
    if not enabled:
        return {
            "ok": True,
            "dry_run": False,
            "would_publish": False,
            "error": "",
            "x_post_id": "",
            "x_post_url": "",
            "note": "AUTO_PUBLISH_ENABLED=false",
        }

    api_key = _env("X_API_KEY")
    api_secret = _env("X_API_SECRET")
    access_token = _env("X_ACCESS_TOKEN")
    access_secret = _env("X_ACCESS_TOKEN_SECRET")
    missing = [k for k, v in [("X_API_KEY", api_key), ("X_API_SECRET", api_secret), ("X_ACCESS_TOKEN", access_token), ("X_ACCESS_TOKEN_SECRET", access_secret)] if not v]
    if missing:
        return {
            "ok": False,
            "dry_run": False,
            "would_publish": False,
            "error": "missing env: " + ",".join(missing),
            "x_post_id": "",
            "x_post_url": "",
        }

    def _post_tweet(payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        auth = _oauth_header(
            "POST",
            TWITTER_API_BASE,
            consumer_key=api_key,
            consumer_secret=api_secret,
            token=access_token,
            token_secret=access_secret,
        )
        req = urllib.request.Request(
            TWITTER_API_BASE,
            data=body,
            method="POST",
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
            j = json.loads(raw)
            return True, j if isinstance(j, dict) else None, ""
        except urllib.error.HTTPError as e:
            try:
                txt = e.read().decode("utf-8")
            except Exception:
                txt = ""
            return False, None, f"http_error:{getattr(e, 'code', '')} {txt[:200]}"
        except Exception as e:
            return False, None, f"error:{e}"

    ok1, j1, err1 = _post_tweet({"text": main_post})
    if not ok1 or not j1 or "data" not in j1 or "id" not in j1["data"]:
        return {
            "ok": False,
            "dry_run": False,
            "would_publish": False,
            "error": err1 or "post_main_failed",
            "x_post_id": "",
            "x_post_url": "",
        }

    post_id = str(j1["data"]["id"])
    post_url = f"https://x.com/i/web/status/{post_id}"

    if first_comment.strip():
        _post_tweet({"text": first_comment.strip(), "reply": {"in_reply_to_tweet_id": post_id}})

    return {
        "ok": True,
        "dry_run": False,
        "would_publish": True,
        "error": "",
        "x_post_id": post_id,
        "x_post_url": post_url,
    }

