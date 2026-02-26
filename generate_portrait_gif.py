#!/usr/bin/env python3
"""
generate_portrait_gif.py
────────────────────────
Generates an animated GIF that transitions from your real photo
to the stylized pixel-grid portrait graphic.

The animation has 3 phases:
  1. Hold on original photo (8 frames)
  2. Transition: photo gradually pixelates and gets colorized (16 frames)
  3. Hold on pixel graphic (8 frames)
  Then loops back.

Usage:
    python generate_portrait_gif.py
    python generate_portrait_gif.py --photo assets/img/profile.jpg
    python generate_portrait_gif.py --style indigo --cols 60
    python generate_portrait_gif.py --speed fast   # fast / normal / slow

Output:
    assets/img/portrait.gif  (drop-in replacement for portrait.svg in HTML)
"""

import argparse
import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
    import numpy as np
except ImportError:
    print("Install dependencies: pip install pillow numpy")
    raise

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent
DEFAULT_IN  = ROOT / "assets" / "img" / "pr2_copy.jpeg"
DEFAULT_OUT = ROOT / "assets" / "img" / "portrait.gif"

# ── Palettes (same as generate_portrait.py) ────────────────────────────────────
PALETTES = {
    "indigo": {
        "tones": ["#1a1535", "#5b3fa0", "#9b7fd4", "#e8e0f5"],
        "bg":    "#f9f7ff",
    },
    "warm": {
        "tones": ["#1c1812", "#b85c38", "#e8a87c", "#f5e8d8"],
        "bg":    "#f7f3ec",
    },
    "mono": {
        "tones": ["#111111", "#555555", "#aaaaaa", "#eeeeee"],
        "bg":    "#fafafa",
    },
    "ocean": {
        "tones": ["#0d2137", "#1a5f7a", "#4fa3c2", "#d6eef8"],
        "bg":    "#f0f8ff",
    },
}

SPEEDS = {
    "fast":   {"hold": 6,  "transition": 12, "frame_ms": 60},
    "normal": {"hold": 10, "transition": 18, "frame_ms": 80},
    "slow":   {"hold": 14, "transition": 24, "frame_ms": 100},
}


def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def load_and_crop(path: Path, target_w: int, target_h: int) -> Image.Image:
    """Load photo, centre-crop to target ratio, resize."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    ratio = target_w / target_h
    if w / h > ratio:
        new_w = int(h * ratio)
        img = img.crop(((w - new_w) // 2, 0, (w + new_w) // 2, h))
    else:
        new_h = int(w / ratio)
        img = img.crop((0, (h - new_h) // 2, w, (h + new_h) // 2))
    return img.resize((target_w, target_h), Image.LANCZOS)


def build_pixel_image(photo: Image.Image, palette: dict,
                      cell_cols: int, cell_size: int, gap: int) -> Image.Image:
    """
    Render the posterized pixel-grid version as a PIL Image
    (same look as the SVG but as raster).
    """
    cell_rows = int(cell_cols * (photo.height / photo.width))
    thumb = photo.resize((cell_cols, cell_rows), Image.LANCZOS).convert("L")
    thumb = ImageEnhance.Contrast(thumb).enhance(1.6)
    thumb = ImageOps.autocontrast(thumb, cutoff=3)

    arr = np.array(thumb, dtype=np.float32) / 255.0
    tone = np.zeros_like(arr, dtype=np.uint8)
    tone[arr >= 0.25] = 1
    tone[arr >= 0.55] = 2
    tone[arr >= 0.80] = 3

    colors = [hex_to_rgb(c) for c in palette["tones"]]
    bg     = hex_to_rgb(palette["bg"])

    out_w = cell_cols * (cell_size + gap)
    out_h = cell_rows  * (cell_size + gap)
    img = Image.new("RGB", (out_w, out_h), bg)
    draw = ImageDraw.Draw(img)

    for r in range(cell_rows):
        for c in range(cell_cols):
            color = colors[tone[r, c]]
            x = c * (cell_size + gap)
            y = r * (cell_size + gap)
            draw.rectangle([x, y, x + cell_size - 1, y + cell_size - 1], fill=color)

    return img


def blend(img_a: Image.Image, img_b: Image.Image, t: float) -> Image.Image:
    """Linear crossfade between two same-size images. t=0→a, t=1→b."""
    return Image.blend(img_a, img_b, t)


def pixelate_step(photo: Image.Image, t: float, cell_cols: int) -> Image.Image:
    """
    Progressive pixelation effect. t=0→crisp original, t=1→blocky.
    Uses shrink+grow to create real pixel blocks.
    """
    # Interpolate between full-res and very low res
    min_res = max(cell_cols, 20)
    res = int(photo.width - (photo.width - min_res) * t)
    res = max(res, min_res)
    small = photo.resize((res, int(res * photo.height / photo.width)), Image.BILINEAR)
    blocky = small.resize(photo.size, Image.NEAREST)
    return blocky


def easing(t: float) -> float:
    """Smooth ease-in-out (cubic)."""
    return t * t * (3 - 2 * t)


def generate_gif(
    photo_path: Path,
    out_path: Path,
    style: str = "indigo",
    cell_cols: int = 70,
    cell_size: int = 7,
    gap: int = 1,
    speed: str = "normal",
):
    timing = SPEEDS[speed]
    palette = PALETTES[style]
    colors_rgb = [hex_to_rgb(c) for c in palette["tones"]]
    bg_rgb = hex_to_rgb(palette["bg"])

    print(f"\n  Generating portrait GIF")
    print(f"  ├─ Photo:  {photo_path}")
    print(f"  ├─ Style:  {style}  Speed: {speed}")
    print(f"  └─ Output: {out_path}\n")

    # ── Build pixel version ────────────────────────────────────────────────────
    print("  Building pixel graphic…")
    cell_rows = int(cell_cols * 1.3)
    out_w = cell_cols * (cell_size + gap)
    out_h = cell_rows  * (cell_size + gap)

    photo_orig = load_and_crop(photo_path, out_w, out_h)
    pixel_img  = build_pixel_image(photo_orig, palette, cell_cols, cell_size, gap)

    # ── Apply subtle contrast boost to photo for better look ──────────────────
    photo_display = ImageEnhance.Contrast(photo_orig).enhance(1.15)
    photo_display = ImageEnhance.Brightness(photo_display).enhance(1.05)

    # ── Build frames ───────────────────────────────────────────────────────────
    print("  Rendering frames…")
    frames = []
    durations = []
    ms = timing["frame_ms"]

    n_hold       = timing["hold"]
    n_transition = timing["transition"]

    # Phase 1: hold on photo
    for _ in range(n_hold):
        frames.append(photo_display.copy())
        durations.append(ms)

    # Phase 2: transition photo → pixel
    for i in range(n_transition):
        t = easing(i / (n_transition - 1))

        # Pixelation increases
        pixelated = pixelate_step(photo_display, t * 0.85, cell_cols)

        # Crossfade to colorized pixel grid
        blended = blend(pixelated, pixel_img, t)

        frames.append(blended)
        durations.append(ms)

    # Phase 3: hold on pixel graphic
    for _ in range(n_hold):
        frames.append(pixel_img.copy())
        durations.append(ms)

    # Phase 4: transition pixel → photo (reverse)
    for i in range(n_transition):
        t = easing(i / (n_transition - 1))
        pixelated = pixelate_step(photo_display, (1 - t) * 0.85, cell_cols)
        blended = blend(pixel_img, pixelated, t)
        frames.append(blended)
        durations.append(ms)

    # ── Save GIF ───────────────────────────────────────────────────────────────
    print(f"  Saving {len(frames)} frames → {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to palette mode for smaller file size
    palette_frames = []
    for f in frames:
        palette_frames.append(f.convert("P", palette=Image.ADAPTIVE, colors=128))

    palette_frames[0].save(
        out_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_kb = out_path.stat().st_size / 1024
    print(f"  ✓  Done → {out_path}  ({size_kb:.0f} KB)\n")
    print("  Next steps:")
    print("  1. In your HTML, replace:")
    print('       <img src="assets/img/portrait.svg" ...>')
    print("     with:")
    print('       <img src="assets/img/portrait.gif" ...>')
    print("  2. Run: python build.py\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo",  default=str(DEFAULT_IN))
    ap.add_argument("--out",    default=str(DEFAULT_OUT))
    ap.add_argument("--style",  default="indigo", choices=list(PALETTES))
    ap.add_argument("--cols",   type=int, default=70)
    ap.add_argument("--cell",   type=int, default=7)
    ap.add_argument("--gap",    type=int, default=1)
    ap.add_argument("--speed",  default="normal", choices=list(SPEEDS))
    args = ap.parse_args()

    generate_gif(
        photo_path=Path(args.photo),
        out_path=Path(args.out),
        style=args.style,
        cell_cols=args.cols,
        cell_size=args.cell,
        gap=args.gap,
        speed=args.speed,
    )


if __name__ == "__main__":
    main()