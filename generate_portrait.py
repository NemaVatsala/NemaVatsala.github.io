#!/usr/bin/env python3
"""
generate_portrait.py
────────────────────
Converts your photo into a stylized SVG portrait for the portfolio hero.

The output is a clean, flat-graphic SVG — similar to the illustrated portrait
style used on sites like soniamurthy.com. It uses a duotone + posterize
technique: your photo is reduced to 4 tonal layers, each mapped to a
palette color, then output as vector-ready SVG rectangles at a resolution
that reads as illustrative rather than photographic.

Usage:
    python generate_portrait.py
    python generate_portrait.py --photo assets/img/profile.jpg
    python generate_portrait.py --photo assets/img/profile.jpg --style warm
    python generate_portrait.py --preview        # opens SVG in browser after

Styles (--style):
    indigo   — deep indigo + mauve + sage  [default, matches new site palette]
    warm     — terracotta + amber + cream
    mono     — ink + dust (monochrome)
    ocean    — navy + teal + sky

Output:
    assets/img/portrait.svg   (use this in your HTML)
"""

import argparse
import math
import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    import numpy as np
except ImportError:
    print("Install dependencies first: pip install pillow numpy")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent
DEFAULT_IN  = ROOT / "assets" / "img" / "Pr2_copy.jpeg"
DEFAULT_OUT = ROOT / "assets" / "img" / "portrait.svg"

# ── Colour palettes ────────────────────────────────────────────────────────────
# Each palette has 4 tones: [darkest → lightest]
# + a background colour and accent colour for decorative elements
PALETTES = {
    "indigo": {
        "tones":  ["#1a1535", "#5b3fa0", "#9b7fd4", "#e8e0f5"],
        "bg":     "#f9f7ff",
        "accent": "#7c5cbf",
        "spark":  "#f2c94c",
    },
    "warm": {
        "tones":  ["#1c1812", "#b85c38", "#e8a87c", "#f5e8d8"],
        "bg":     "#f7f3ec",
        "accent": "#b85c38",
        "spark":  "#f2c94c",
    },
    "mono": {
        "tones":  ["#111111", "#555555", "#aaaaaa", "#eeeeee"],
        "bg":     "#fafafa",
        "accent": "#333333",
        "spark":  "#888888",
    },
    "ocean": {
        "tones":  ["#0d2137", "#1a5f7a", "#4fa3c2", "#d6eef8"],
        "bg":     "#f0f8ff",
        "accent": "#1a5f7a",
        "spark":  "#f2c94c",
    },
}

# ── SVG helpers ────────────────────────────────────────────────────────────────

def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def sparkle_svg(cx, cy, size, color, rotate=0) -> str:
    """Four-pointed sparkle shape."""
    s = size / 2
    t = s * 0.25
    pts = (
        f"M{cx},{cy - s} C{cx + t},{cy - t} {cx + t},{cy - t} {cx + s},{cy} "
        f"C{cx + t},{cy + t} {cx + t},{cy + t} {cx},{cy + s} "
        f"C{cx - t},{cy + t} {cx - t},{cy + t} {cx - s},{cy} "
        f"C{cx - t},{cy - t} {cx - t},{cy - t} {cx},{cy - s} Z"
    )
    return f'<path d="{pts}" fill="{color}" transform="rotate({rotate},{cx},{cy})" opacity="0.85"/>'


def circle_cluster(cx, cy, r, color, n=6) -> str:
    """Small cluster of filled circles."""
    parts = []
    for i in range(n):
        angle = (i / n) * 2 * math.pi
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.35:.1f}" fill="{color}" opacity="0.6"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r * 0.35:.1f}" fill="{color}" opacity="0.6"/>')
    return "\n".join(parts)


def wavy_line(x1, y1, x2, y2, color, amp=8, freq=4) -> str:
    """Wavy decorative line."""
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx*dx + dy*dy)
    steps = int(freq * 2)
    pts = [f"M{x1:.1f},{y1:.1f}"]
    for i in range(steps):
        t = (i + 1) / steps
        mx = x1 + dx * t
        my = y1 + dy * t
        perp_x = -dy / length * amp * (1 if i % 2 == 0 else -1)
        perp_y =  dx / length * amp * (1 if i % 2 == 0 else -1)
        pts.append(f"Q{mx + perp_x:.1f},{my + perp_y:.1f} {x2 * t + x1 * (1-t):.1f},{y2 * t + y1 * (1-t):.1f}")
    return f'<path d="{" ".join(pts)}" stroke="{color}" stroke-width="2" fill="none" opacity="0.5"/>'


def dot_grid(x, y, w, h, color, spacing=10, dot_r=1.5) -> str:
    """Decorative dot grid region."""
    parts = []
    xi = x
    while xi <= x + w:
        yi = y
        while yi <= y + h:
            parts.append(f'<circle cx="{xi:.0f}" cy="{yi:.0f}" r="{dot_r}" fill="{color}" opacity="0.35"/>')
            yi += spacing
        xi += spacing
    return "\n".join(parts)


# ── Core portrait generation ───────────────────────────────────────────────────

def process_photo(path: Path, cell_cols: int = 80, cell_rows: int = 104) -> np.ndarray:
    """
    Load + process photo into a 2D array of tone indices (0–3).
    Returns shape (cell_rows, cell_cols) with values in {0,1,2,3}.
    """
    img = Image.open(path).convert("RGB")

    # Centre-crop to portrait ratio
    w, h = img.size
    target_ratio = cell_cols / cell_rows
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        img = img.crop(((w - new_w) // 2, 0, (w + new_w) // 2, h))
    else:
        new_h = int(w / target_ratio)
        img = img.crop((0, (h - new_h) // 2, w, (h + new_h) // 2))

    # Resize to cell grid
    img = img.resize((cell_cols, cell_rows), Image.LANCZOS)

    # Convert to grayscale + enhance contrast
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.6)
    img = ImageOps.autocontrast(img, cutoff=3)
    img = img.filter(ImageFilter.SMOOTH)

    # Posterize to 4 tones
    arr = np.array(img, dtype=np.float32) / 255.0
    # Quantise to 0,1,2,3
    tone = np.zeros_like(arr, dtype=np.uint8)
    tone[arr >= 0.25] = 1
    tone[arr >= 0.55] = 2
    tone[arr >= 0.80] = 3

    return tone


def build_portrait_svg(
    tone_grid: np.ndarray,
    palette: dict,
    cell_size: int = 7,
    gap: int = 1,
    round_px: int = 1,
) -> str:
    """
    Render tone grid as SVG rectangles + decorative elements.
    """
    rows, cols = tone_grid.shape
    colors = palette["tones"]
    bg     = palette["bg"]
    accent = palette["accent"]
    spark  = palette["spark"]

    w = cols * (cell_size + gap)
    h = rows * (cell_size + gap)

    # Extra canvas space for decorative elements floating outside portrait
    pad_x, pad_y = 80, 80
    total_w = w + pad_x * 2
    total_h = h + pad_y * 2
    ox = pad_x   # portrait origin x
    oy = pad_y   # portrait origin y

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" '
        f'width="{total_w}" height="{total_h}">',
        f'<!-- Generated by generate_portrait.py -->',
        '<defs>',
        '  <style>',
        '    .portrait-cell { shape-rendering: crispEdges; }',
        '    @keyframes float {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-8px); }} }}',
        '    @keyframes spin  {{ from {{ transform: rotate(0deg); }}  to {{ transform: rotate(360deg); }} }}',
        '    .spark {{ animation: float 3s ease-in-out infinite; transform-origin: center; }}',
        '    .spark2 {{ animation: float 4.5s ease-in-out infinite 1s; transform-origin: center; }}',
        '  </style>',
        '</defs>',
        # Background
        f'<rect width="{total_w}" height="{total_h}" fill="{bg}"/>',
    ]

    # ── Portrait cells ──────────────────────────────────────────────────────
    lines.append('<!-- portrait cells -->')
    lines.append('<g class="portrait">')
    for r in range(rows):
        for c in range(cols):
            tone = tone_grid[r, c]
            color = colors[tone]
            x = ox + c * (cell_size + gap)
            y = oy + r * (cell_size + gap)
            lines.append(
                f'<rect class="portrait-cell" x="{x}" y="{y}" '
                f'width="{cell_size}" height="{cell_size}" '
                f'rx="{round_px}" fill="{color}"/>'
            )
    lines.append('</g>')

    # ── Decorative elements ─────────────────────────────────────────────────
    lines.append('<!-- decorative elements -->')

    # Dot grid — top left corner
    lines.append(dot_grid(10, 10, 55, 55, accent, spacing=9, dot_r=1.8))

    # Dot grid — bottom right corner
    lines.append(dot_grid(total_w - 65, total_h - 65, 55, 55, accent, spacing=9, dot_r=1.8))

    # Large sparkle — top right
    lines.append(f'<g class="spark">')
    lines.append(sparkle_svg(total_w - 30, 40, 36, spark, rotate=15))
    lines.append('</g>')

    # Medium sparkle — top left of portrait
    lines.append(f'<g class="spark2">')
    lines.append(sparkle_svg(ox - 25, oy + 60, 22, spark, rotate=0))
    lines.append('</g>')

    # Small sparkle cluster — bottom right of portrait
    lines.append(f'<g class="spark">')
    lines.append(sparkle_svg(ox + w + 30, oy + h - 40, 16, spark, rotate=30))
    lines.append(sparkle_svg(ox + w + 50, oy + h - 20, 10, spark, rotate=10))
    lines.append('</g>')

    # Circle cluster — left mid
    lines.append(circle_cluster(ox - 40, oy + h // 2, 14, accent, n=6))

    # Circle cluster — right top
    lines.append(circle_cluster(ox + w + 45, oy + 80, 10, colors[1], n=5))

    # Wavy lines — below portrait
    lines.append(wavy_line(ox, oy + h + 20, ox + w, oy + h + 20, accent, amp=6, freq=5))
    lines.append(wavy_line(ox + 20, oy + h + 34, ox + w - 20, oy + h + 34, colors[1], amp=5, freq=4))

    # Small dots scattered
    scatter = [
        (ox - 55, oy + 20, 3),
        (ox - 45, oy + 35, 2),
        (ox + w + 55, oy + h - 80, 3),
        (ox + w + 40, oy + h - 65, 2),
        (ox + 15, oy - 45, 3),
        (ox + w - 15, oy - 30, 2),
    ]
    for sx, sy, sr in scatter:
        lines.append(f'<circle cx="{sx}" cy="{sy}" r="{sr}" fill="{accent}" opacity="0.5"/>')

    # Small sparkles scattered
    small_sparks = [
        (ox + w // 4, oy - 35, 12, 0),
        (ox + w * 3 // 4, oy - 20, 8, 20),
        (ox - 50, oy + h * 2 // 3, 10, 45),
        (ox + w + 55, oy + h // 3, 14, 10),
    ]
    for sx, sy, ss, sr in small_sparks:
        lines.append(f'<g class="spark2">')
        lines.append(sparkle_svg(sx, sy, ss, spark, rotate=sr))
        lines.append('</g>')

    lines.append('</svg>')
    return "\n".join(lines)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate stylized SVG portrait from photo")
    ap.add_argument("--photo",   default=str(DEFAULT_IN),  help="Input photo path")
    ap.add_argument("--out",     default=str(DEFAULT_OUT), help="Output SVG path")
    ap.add_argument("--style",   default="indigo",         choices=list(PALETTES),
                    help="Colour palette style")
    ap.add_argument("--cols",    type=int, default=80,     help="Grid columns (detail level)")
    ap.add_argument("--cell",    type=int, default=7,      help="Cell size in px")
    ap.add_argument("--gap",     type=int, default=1,      help="Gap between cells in px")
    ap.add_argument("--preview", action="store_true",      help="Open SVG in browser after")
    args = ap.parse_args()

    photo_path = Path(args.photo)
    out_path   = Path(args.out)

    if not photo_path.exists():
        print(f"✗  Photo not found: {photo_path}")
        print(f"   Drop your photo at assets/img/profile.jpg and re-run.")
        sys.exit(1)

    palette  = PALETTES[args.style]
    # Maintain ~4:3 portrait ratio from cols
    cell_rows = int(args.cols * 1.3)

    print(f"\n  Generating portrait SVG")
    print(f"  ├─ Photo:   {photo_path}")
    print(f"  ├─ Style:   {args.style}")
    print(f"  ├─ Grid:    {args.cols} × {cell_rows} cells")
    print(f"  └─ Output:  {out_path}\n")

    # Process photo
    print("  Processing photo…")
    tone_grid = process_photo(photo_path, cell_cols=args.cols, cell_rows=cell_rows)

    # Build SVG
    print("  Rendering SVG…")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    svg = build_portrait_svg(tone_grid, palette, cell_size=args.cell, gap=args.gap)
    out_path.write_text(svg, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"  ✓  Done → {out_path}  ({size_kb:.0f} KB)\n")

    if args.preview:
        webbrowser.open(out_path.resolve().as_uri())
        print("  Opened in browser.")

    print("  Next steps:")
    print(f"  1. Check the SVG: open {out_path} in your browser")
    print(f"  2. Run: python build.py --serve  to see it on the site")
    print(f"  3. Tweak --style, --cols, --cell, --gap to adjust the look\n")


if __name__ == "__main__":
    main()
