from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = (line or "").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def _render_review_md(event: dict[str, Any], x_pack: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# X Review Packet v002\n\n")
    lines.append(f"- generated_at_utc: {_utc_now_iso()}\n")
    lines.append(f"- event_id: {str(x_pack.get('event_id') or '').strip()}\n")
    lines.append(f"- title: {str(x_pack.get('title') or '').strip()}\n")
    lines.append(f"- publish_status: {str(x_pack.get('publish_status') or '').strip()}\n")
    lines.append(f"- content_generation_mode: {str(x_pack.get('content_generation_mode') or '').strip()}\n")

    lines.append("\n## Summary\n\n")
    lines.append(_clip(str(event.get("summary") or ""), 1200) + "\n")

    assets = event.get("asset_symbols") if isinstance(event.get("asset_symbols"), list) else []
    if assets:
        lines.append("\n## Assets\n\n")
        for a in assets[:30]:
            lines.append(f"- {str(a)}\n")

    lines.append("\n## Sources\n\n")
    sp = event.get("source_pack") if isinstance(event.get("source_pack"), list) else []
    if not sp:
        lines.append("- (empty)\n")
    else:
        for x in sp[:10]:
            if not isinstance(x, dict):
                continue
            t = str(x.get("title") or "").strip()
            u = str(x.get("url") or "").strip()
            st = str(x.get("source_type") or "").strip()
            lines.append(f"- [{st}] {t} | {u}\n")

    fp = event.get("fact_pack") if isinstance(event.get("fact_pack"), dict) else {}
    confirmed = fp.get("confirmed") if isinstance(fp.get("confirmed"), list) else []
    uncertain = fp.get("uncertain") if isinstance(fp.get("uncertain"), list) else []
    should_not_claim = fp.get("should_not_claim") if isinstance(fp.get("should_not_claim"), list) else []

    lines.append("\n## Fact Pack\n\n")
    lines.append("### confirmed\n")
    if confirmed:
        for x in confirmed[:20]:
            lines.append(f"- {str(x)}\n")
    else:
        lines.append("- (empty)\n")
    lines.append("\n### uncertain\n")
    if uncertain:
        for x in uncertain[:20]:
            lines.append(f"- {str(x)}\n")
    else:
        lines.append("- (empty)\n")
    lines.append("\n### should_not_claim\n")
    if should_not_claim:
        for x in should_not_claim[:20]:
            lines.append(f"- {str(x)}\n")
    else:
        lines.append("- (empty)\n")

    rf = x_pack.get("risk_flags") if isinstance(x_pack.get("risk_flags"), list) else []
    lines.append("\n## Risk Flags\n\n")
    if rf:
        for x in rf[:30]:
            lines.append(f"- {str(x)}\n")
    else:
        lines.append("- (empty)\n")

    lines.append("\n## X Content Pack Skeleton\n\n")
    lines.append("- official_post: draft/style/max_chars\n")
    lines.append("- personal_post: draft/style/max_chars\n")
    lines.append("- reply_angle: draft/target_type\n")
    lines.append("- quote_angle: draft/angle\n")
    lines.append("- thread_outline: list[str]\n")
    lines.append("- image_prompt: string\n")
    return "".join(lines)


def build_x_content_pack(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("input_id") or "").strip()
    title = str(event.get("title") or "").strip()
    risk_flags = event.get("risk_flags") if isinstance(event.get("risk_flags"), list) else []

    return {
        "content_generation_mode": "template_skeleton_no_ai",
        "event_id": event_id,
        "title": title,
        "official_post": {"draft": "", "style": "official_stable", "max_chars": 280},
        "personal_post": {"draft": "", "style": "human_opinion", "max_chars": 280},
        "reply_angle": {"draft": "", "target_type": "kol_or_hot_thread"},
        "quote_angle": {"draft": "", "angle": ""},
        "thread_outline": [""],
        "image_prompt": "",
        "risk_flags": [str(x) for x in risk_flags if isinstance(x, str)],
        "ai_reviewer_required": True,
        "publish_status": "blocked_until_ai_review",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="out/shared_event_import/events.jsonl")
    ap.add_argument("--out-dir", default="out/x_review_pack_v002")
    args = ap.parse_args()

    root = _project_root()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = root / input_path

    out_root = Path(args.out_dir)
    if not out_root.is_absolute():
        out_root = root / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    events = _read_jsonl(input_path)
    written = 0

    for ev in events:
        event_id = str(ev.get("input_id") or "").strip()
        if not event_id:
            continue
        out_dir = out_root / event_id
        out_dir.mkdir(parents=True, exist_ok=True)

        x_pack = build_x_content_pack(ev)
        status = {
            "event_id": event_id,
            "generated_at_utc": _utc_now_iso(),
            "publish_status": "blocked_until_ai_review",
            "stage": "review_packet_built",
        }

        _write_json(out_dir / "event.json", ev)
        _write_json(out_dir / "x_content_pack.json", x_pack)
        _write_json(out_dir / "status.json", status)
        (out_dir / "x_review_packet.md").write_text(_render_review_md(ev, x_pack), encoding="utf-8")
        written += 1

    index = {
        "task_id": "x_v2_002_shared_event_pack_adapter",
        "generated_at_utc": _utc_now_iso(),
        "input_path": str(input_path),
        "out_dir": str(out_root),
        "events": written,
        "content_generation_mode": "template_skeleton_no_ai",
        "paid_model_called": False,
        "x_published": False,
    }
    _write_json(out_root / "index.json", index)


if __name__ == "__main__":
    main()

