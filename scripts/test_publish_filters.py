from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _backup_paths(paths: list[Path]) -> dict[Path, str | None]:
    snap: dict[Path, str | None] = {}
    for p in paths:
        snap[p] = _read_text(p) if p.exists() else None
    return snap


def _restore_paths(snap: dict[Path, str | None]) -> None:
    for p, content in snap.items():
        if content is None:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            continue
        _write_text(p, content)


def _run(args: list[str], *, cwd: Path) -> str:
    out = subprocess.check_output(args, cwd=str(cwd), text=True, encoding="utf-8", errors="replace")
    return out


def _parse_items_count(stdout: str) -> int:
    m = re.search(r"items=(\d+)", stdout)
    if not m:
        raise AssertionError("missing items= in output:\n" + stdout)
    return int(m.group(1))


def _append_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> None:
    root = _project_root()
    out_dir = root / "out"
    raw_dir = out_dir / "generated_posts" / "raw_json"
    latest_run = out_dir / "generated_posts" / "latest_run_id.txt"
    events_path = out_dir / "hot_engine_queues" / "events.jsonl"
    dryrun_log = out_dir / "publish_logs" / "dryrun_posts.jsonl"

    raw_dir.mkdir(parents=True, exist_ok=True)

    to_backup = [latest_run, events_path, dryrun_log]
    snap = _backup_paths(to_backup)
    raw_files = list(raw_dir.glob("*.json"))
    raw_snap = {p: _read_text(p) for p in raw_files}

    try:
        for fp in raw_files:
            fp.unlink()

        now = datetime.now(timezone.utc)
        gen_at = now.replace(microsecond=0).isoformat()

        eid_q = "evt_pf_q_001"
        eid_w = "evt_pf_w_001"

        _write_text(
            events_path,
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_cluster_id": eid_q,
                            "cluster_queue": "queue_review",
                            "cluster_title": "Queue review event",
                            "risk_level": "low",
                            "best_source_url": "https://example.com/source",
                            "source_names": ["coindesk"],
                            "source_urls": ["https://example.com/source"],
                            "total_score": 90,
                            "rule_reason": "test",
                            "item_count": 1,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "event_cluster_id": eid_w,
                            "cluster_queue": "whale_digest",
                            "cluster_title": "Whale digest event",
                            "risk_level": "low",
                            "best_source_url": "https://example.com/source2",
                            "source_names": ["coindesk"],
                            "source_urls": ["https://example.com/source2"],
                            "total_score": 80,
                            "rule_reason": "test",
                            "item_count": 1,
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
        )

        run_a = "20260514_090000_abcd01"
        _write_text(latest_run, run_a)
        _write_text(dryrun_log, "")
        _write_text(
            raw_dir / f"{eid_q}_queue_review_coinmeta_hot_post.json",
            json.dumps(
                {
                    "run_id": run_a,
                    "generated_at": gen_at,
                    "queue": "queue_review",
                    "event_cluster_id": eid_q,
                    "skill_name": "coinmeta_hot_post",
                    "prompt_version": "v0.1",
                    "source_urls": ["https://example.com/source"],
                    "risk_level": "low",
                    "generated_json": {"main_post": "Simple post.", "first_comment": "Simple comment."},
                    "raw_output_path": "",
                    "ok": True,
                    "error": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        out = _run(
            [
                sys.executable,
                str(root / "scripts" / "publish_from_generated.py"),
                "--dry-run",
                "--queue",
                "queue_review",
                "--latest-run",
            ],
            cwd=root,
        )
        assert _parse_items_count(out) == 1, out

        log_txt = _read_text(dryrun_log)
        assert '"run_id":' in log_txt, "dryrun_posts.jsonl missing run_id"

        run_b = "20260514_090000_abcd02"
        _write_text(latest_run, run_b)
        out = _run(
            [
                sys.executable,
                str(root / "scripts" / "publish_from_generated.py"),
                "--dry-run",
                "--queue",
                "whale_digest",
                "--latest-run",
            ],
            cwd=root,
        )
        assert _parse_items_count(out) == 0, out

        run_c = "20260514_090000_abcd03"
        _write_text(latest_run, run_c)
        gen_at2 = (now + timedelta(seconds=1)).replace(microsecond=0).isoformat()
        _write_text(
            raw_dir / f"{eid_q}_queue_review_coinmeta_hot_post_run_c.json",
            json.dumps(
                {
                    "run_id": run_c,
                    "generated_at": gen_at2,
                    "queue": "queue_review",
                    "event_cluster_id": eid_q,
                    "skill_name": "coinmeta_hot_post",
                    "prompt_version": "v0.1",
                    "source_urls": ["https://example.com/source"],
                    "risk_level": "low",
                    "generated_json": {"main_post": "Simple post 2.", "first_comment": "Simple comment 2."},
                    "raw_output_path": "",
                    "ok": True,
                    "error": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        _write_text(
            raw_dir / f"{eid_w}_whale_digest_coinmeta_whale_digest_run_c.json",
            json.dumps(
                {
                    "run_id": run_c,
                    "generated_at": gen_at2,
                    "queue": "whale_digest",
                    "event_cluster_id": eid_w,
                    "skill_name": "coinmeta_whale_digest",
                    "prompt_version": "v0.1",
                    "source_urls": ["https://example.com/source2"],
                    "risk_level": "low",
                    "generated_json": {"main_post": "Whale post.", "first_comment": ""},
                    "raw_output_path": "",
                    "ok": True,
                    "error": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        out = _run(
            [
                sys.executable,
                str(root / "scripts" / "publish_from_generated.py"),
                "--dry-run",
                "--queue",
                "whale_digest",
                "--run-id",
                run_c,
            ],
            cwd=root,
        )
        assert _parse_items_count(out) == 1, out

        print("[test_publish_filters] OK")
    finally:
        for fp, content in raw_snap.items():
            _write_text(fp, content)
        current_raw = set(raw_dir.glob("*.json"))
        for fp in current_raw:
            if fp not in raw_snap:
                try:
                    fp.unlink()
                except FileNotFoundError:
                    pass
        _restore_paths(snap)


if __name__ == "__main__":
    main()

