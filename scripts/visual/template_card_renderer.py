from __future__ import annotations

from pathlib import Path
from typing import Any


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _take_str_list(x: Any, limit: int) -> list[str]:
    if not isinstance(x, list):
        return []
    out: list[str] = []
    for it in x:
        s = str(it).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _render_svg(*, title: str, subtitle: str, bullets: list[str], template_name: str) -> str:
    w = 1080
    h = 1350
    pad = 72
    bg = "#0B1220"
    card = "#111A2E"
    if template_name in {"whale_digest_card", "daily_whale_digest_card"}:
        accent = "#22C55E"
    elif template_name in {"market_move_card"}:
        accent = "#60A5FA"
    else:
        accent = "#A78BFA"
    text_main = "#E5E7EB"
    text_muted = "#9CA3AF"

    y = pad + 24
    lines: list[str] = []

    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">')
    lines.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>')
    lines.append(f'<rect x="{pad}" y="{pad}" width="{w - pad*2}" height="{h - pad*2}" rx="36" fill="{card}"/>')
    lines.append(f'<rect x="{pad}" y="{pad}" width="{w - pad*2}" height="12" rx="6" fill="{accent}"/>')

    lines.append(
        f'<text x="{pad + 48}" y="{y + 48}" fill="{text_main}" font-size="56" font-family="Arial, Helvetica, sans-serif" font-weight="700">{_esc(title)}</text>'
    )
    y += 96
    if subtitle:
        lines.append(
            f'<text x="{pad + 48}" y="{y + 28}" fill="{text_muted}" font-size="30" font-family="Arial, Helvetica, sans-serif">{_esc(subtitle)}</text>'
        )
        y += 64

    lines.append(f'<line x1="{pad + 48}" y1="{y}" x2="{w - pad - 48}" y2="{y}" stroke="#24314F" stroke-width="2"/>')
    y += 40

    max_bullets = bullets[:6]
    for b in max_bullets:
        lines.append(
            f'<text x="{pad + 72}" y="{y}" fill="{text_main}" font-size="34" font-family="Arial, Helvetica, sans-serif">• {_esc(b)}</text>'
        )
        y += 56

    footer = "CoinMeta / 币界网"
    lines.append(
        f'<text x="{w - pad - 48}" y="{h - pad - 48}" fill="{text_muted}" font-size="28" font-family="Arial, Helvetica, sans-serif" text-anchor="end">{_esc(footer)}</text>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


def render_template_card(
    *,
    out_dir: Path,
    event_cluster_id: str,
    template_name: str,
    brief: dict[str, Any],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    title = str(brief.get("card_title") or "").strip()
    subtitle = str(brief.get("card_subtitle") or "").strip()
    bullets = _take_str_list(brief.get("card_bullets"), limit=6)

    if not title:
        title = "图卡"
    svg = _render_svg(title=title, subtitle=subtitle, bullets=bullets, template_name=template_name)
    out_path = out_dir / f"{event_cluster_id}_{template_name}.svg"
    out_path.write_text(svg, encoding="utf-8")
    return out_path

