from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _cost_usd_estimate(*, size: str, quality: str) -> float:
    sz = (size or "").strip().lower()
    q = (quality or "").strip().lower()
    table: dict[tuple[str, str], float] = {
        ("1024x1536", "low"): 0.016,
        ("1024x1536", "medium"): 0.063,
        ("1024x1536", "high"): 0.25,
    }
    return float(table.get((sz, q), 0.0))


def _openai_image_generate(
    *,
    api_key: str,
    prompt: str,
    model: str,
    size: str,
    quality: str,
    n: int,
) -> dict[str, Any]:
    url = "https://api.openai.com/v1/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": int(max(1, n)),
        "response_format": "b64_json",
    }
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def main() -> None:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--prompt-file", default="")
    ap.add_argument("--provider", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--size", default="")
    ap.add_argument("--quality", default="")
    ap.add_argument("--n", type=int, default=0)
    args = ap.parse_args()

    provider = (args.provider or os.getenv("IMAGE_PROVIDER") or "mock").strip()
    model = (args.model or os.getenv("IMAGE_MODEL") or "gpt-image-1").strip()
    size = (args.size or os.getenv("IMAGE_SIZE") or "1024x1536").strip()
    quality = (args.quality or os.getenv("IMAGE_QUALITY") or "medium").strip()
    n = int(args.n or int(os.getenv("IMAGE_N") or "1"))

    if provider not in {"mock", "openai_image"}:
        raise SystemExit("provider must be mock or openai_image")

    if (args.run_dir or "").strip():
        run_dir = Path(str(args.run_dir)).expanduser()
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
        prompt_file = run_dir / "ready_to_generate_prompt.md"
    elif (args.prompt_file or "").strip():
        prompt_file = Path(str(args.prompt_file)).expanduser()
        if not prompt_file.is_absolute():
            prompt_file = ROOT / prompt_file
        run_dir = prompt_file.parent
    else:
        raise SystemExit("must provide --run-dir or --prompt-file")

    if not prompt_file.exists():
        raise SystemExit(f"prompt file not found: {prompt_file}")
    if not run_dir.exists():
        raise SystemExit(f"run dir not found: {run_dir}")

    out_dir = run_dir / "generated_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_text = _read_text(prompt_file).strip()
    created_at = _utc_now_iso()

    req_obj = {
        "provider": provider,
        "model": model,
        "size": size,
        "quality": quality,
        "n": int(max(1, n)),
        "prompt_file": str(prompt_file),
        "output_dir": str(out_dir),
        "created_at": created_at,
        "dry_run": provider == "mock",
        "prompt_text": prompt_text,
    }
    _write_json(out_dir / "image_generation_request.json", req_obj)

    if provider == "mock":
        lines: list[str] = []
        lines.append("# Image Generation Mock Report\n")
        lines.append(f"- created_at: {created_at}\n")
        lines.append(f"- provider: {provider}\n")
        lines.append(f"- model: {model}\n")
        lines.append(f"- size: {size}\n")
        lines.append(f"- quality: {quality}\n")
        lines.append(f"- n: {int(max(1, n))}\n")
        lines.append(f"- prompt_file: {str(prompt_file)}\n")
        lines.append(f"- output_dir: {str(out_dir)}\n")
        lines.append("\n## Notes\n")
        lines.append("- mock mode: 未调用 OpenAI API；未生成真实图片。\n")
        (out_dir / "image_generation_mock_report.md").write_text("".join(lines), encoding="utf-8")
        print(f"[image2_generate_from_prompt] mock ok run_dir={run_dir}")
        return

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("missing OPENAI_API_KEY for provider=openai_image")

    resp = _openai_image_generate(api_key=api_key, prompt=prompt_text, model=model, size=size, quality=quality, n=n)
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, list) or not data:
        raise SystemExit("openai_image response missing data")

    written: list[str] = []
    for idx, it in enumerate(data, start=1):
        if not isinstance(it, dict):
            continue
        b64 = str(it.get("b64_json") or "").strip()
        if not b64:
            continue
        img_bytes = base64.b64decode(b64)
        out_path = out_dir / f"image_{idx:03d}.png"
        out_path.write_bytes(img_bytes)

        meta = {
            "provider": "openai_image",
            "model": model,
            "size": size,
            "quality": quality,
            "prompt_file": str(prompt_file),
            "output_image": str(out_path),
            "created_at": created_at,
            "estimated_cost_usd": _cost_usd_estimate(size=size, quality=quality),
            "dry_run": False,
        }
        _write_json(out_dir / f"image_{idx:03d}_meta.json", meta)
        written.append(str(out_path))

        if len(written) >= int(max(1, n)):
            break

    report_lines: list[str] = []
    report_lines.append("# Image Generation Report\n")
    report_lines.append(f"- created_at: {created_at}\n")
    report_lines.append("- provider: openai_image\n")
    report_lines.append(f"- model: {model}\n")
    report_lines.append(f"- size: {size}\n")
    report_lines.append(f"- quality: {quality}\n")
    report_lines.append(f"- n: {int(max(1, n))}\n")
    report_lines.append(f"- prompt_file: {str(prompt_file)}\n")
    report_lines.append(f"- output_dir: {str(out_dir)}\n")
    report_lines.append(f"- images_written: {len(written)}\n")
    report_lines.append("\n## Outputs\n")
    for p in written[:20]:
        report_lines.append(f"- {p}\n")
    (out_dir / "image_generation_report.md").write_text("".join(report_lines), encoding="utf-8")

    print(f"[image2_generate_from_prompt] openai_image ok run_dir={run_dir} images_written={len(written)}")


if __name__ == "__main__":
    main()
