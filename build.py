#!/usr/bin/env python3
"""
build.py — Portfolio site generator
Inspired by al-folio's data-driven approach.

Usage:
    python build.py              # builds to output/index.html
    python build.py --watch      # rebuilds on file changes
    python build.py --serve      # builds + launches local dev server

Photo tip:
    Drop your photo at assets/img/profile.jpg
    High-contrast photos with a plain background work best for the GoL effect.
    The build script will auto-enhance contrast so the pixel portrait is crisp.
"""

import argparse
import http.server
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ── Paths ──────────────────────────────────────────────────
ROOT       = Path(__file__).parent
DATA_DIR   = ROOT / "data"
TMPL_DIR   = ROOT / "templates"
OUT_DIR    = ROOT / "output"
ASSETS_DIR = ROOT / "assets"


# ── Photo preprocessing ────────────────────────────────────

def preprocess_photo(src: Path, dst: Path):
    """
    Convert photo to high-contrast grayscale optimised for the GoL pixel effect.
    Requires Pillow (pip install pillow). If not installed, copies raw file.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except ImportError:
        print("  ℹ  Pillow not installed — skipping photo enhancement.")
        print("     pip install pillow  for best GoL portrait results.")
        shutil.copy2(src, dst)
        return

    img = Image.open(src).convert("RGB")

    # ── 1. Crop to portrait aspect (centre crop)
    w, h = img.size
    target_ratio = 3 / 4
    if w / h > target_ratio:               # too wide
        new_w = int(h * target_ratio)
        img = img.crop(((w - new_w) // 2, 0, (w + new_w) // 2, h))
    elif w / h < target_ratio:             # too tall
        new_h = int(w / target_ratio)
        img = img.crop((0, (h - new_h) // 2, w, (h + new_h) // 2))

    # ── 2. Resize — keep detail but cap at 800px tall (faster sampling)
    img = img.resize((600, 800), Image.LANCZOS)

    # ── 3. Grayscale
    img = img.convert("L")

    # ── 4. Boost contrast so dark areas are clearly dark
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = ImageEnhance.Brightness(img).enhance(1.05)

    # ── 5. Slight sharpen to preserve edges at cell resolution
    img = img.filter(ImageFilter.SHARPEN)

    # ── 6. Auto-level (stretch histogram to 0–255)
    img = ImageOps.autocontrast(img, cutoff=2)

    # ── 7. Save as optimised JPEG
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=88, optimize=True)
    print(f"  ✓  Photo processed → {dst.relative_to(ROOT)}")


def prepare_assets():
    """Copy assets/ to output/assets/, processing the profile photo if present."""
    if not ASSETS_DIR.exists():
        return

    out_assets = OUT_DIR / "assets"
    out_assets.mkdir(parents=True, exist_ok=True)

    for src in ASSETS_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel  = src.relative_to(ASSETS_DIR)
        dst  = out_assets / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Special handling: preprocess the profile photo
        if rel == Path("img/profile.jpg") or rel == Path("img/profile.png"):
            preprocess_photo(src, dst.with_suffix(".jpg"))
        else:
            shutil.copy2(src, dst)


# ── Data loading ───────────────────────────────────────────

def load_data() -> dict:
    """Load all YAML data files from data/."""
    data = {}
    for yml_file in DATA_DIR.glob("*.yml"):
        key = yml_file.stem
        with open(yml_file, encoding="utf-8") as f:
            data[key] = yaml.safe_load(f)
    return data


# ── Build ──────────────────────────────────────────────────

def build(verbose: bool = True) -> Path:
    """Render the Jinja2 template with loaded data and write output."""
    OUT_DIR.mkdir(exist_ok=True)

    data = load_data()
    required = {"profile", "publications", "experience", "research"}
    missing = required - set(data.keys())
    if missing:
        print(f"  ✗  Missing data files: {missing}", file=sys.stderr)
        sys.exit(1)# REPLACE everything from env = Environment(...) to return out_path WITH:

    env = Environment(
        loader=FileSystemLoader(str(TMPL_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    now = datetime.now()
    ctx = dict(
        **data,
        build_year=now.year,
        build_time=now.strftime("%B %Y"),
        portrait_exists=(ASSETS_DIR / "img" / "portrait.svg").exists(),
        cv_pdf_exists=(ASSETS_DIR / "pdf" / "cv.pdf").exists(),
    )

    out_path = OUT_DIR / "index.html"
    out_path.write_text(env.get_template("index.html.jinja").render(**ctx), encoding="utf-8")
    if verbose:
        print(f"  ✓  Built → {out_path}  ({out_path.stat().st_size/1024:.1f} KB)")

    cv_path = OUT_DIR / "cv.html"
    cv_path.write_text(env.get_template("cv.html.jinja").render(**ctx), encoding="utf-8")
    if verbose:
        print(f"  ✓  Built → {cv_path}  ({cv_path.stat().st_size/1024:.1f} KB)")

    prepare_assets()

    if not ctx["cv_pdf_exists"] and verbose:
        print(f"  ℹ  No PDF found — drop your CV at assets/pdf/cv.pdf to enable download")

    return out_path

# ── Watch mode ─────────────────────────────────────────────

def get_mtimes() -> dict:
    watch_paths = (
        list(DATA_DIR.glob("*.yml"))
        + list(TMPL_DIR.glob("*"))
        + list(ASSETS_DIR.rglob("*")) if ASSETS_DIR.exists() else []
    )
    return {p: p.stat().st_mtime for p in watch_paths if p.is_file()}


def watch():
    print("  Watching for changes… (Ctrl+C to stop)\n")
    mtimes = get_mtimes()
    while True:
        time.sleep(0.8)
        current = get_mtimes()
        changed = [p for p, t in current.items() if mtimes.get(p) != t]
        if changed:
            for p in changed:
                print(f"  ↻  Changed: {p.relative_to(ROOT)}")
            try:
                build(verbose=True)
            except Exception as e:
                print(f"  ✗  Build error: {e}")
            mtimes = get_mtimes()


# ── Dev server ─────────────────────────────────────────────

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def log_request(self, *args): pass

# ADD this new function above serve()
def find_free_port(start: int = 8000, attempts: int = 20) -> int:
    import socket
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise OSError(f"No free port found in range {start}–{start + attempts}")


def serve(port: int = 8000):
    os.chdir(OUT_DIR)
    port = find_free_port(port)
    server = http.server.HTTPServer(("", port), QuietHandler)
    
    print(f"  🌐  Serving at http://localhost:{port}")
    server.serve_forever()



# ── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Portfolio site builder")
    parser.add_argument("--watch",  action="store_true", help="Rebuild on file changes")
    parser.add_argument("--serve",  action="store_true", help="Run local dev server")
    parser.add_argument("--port",   type=int, default=8000, help="Dev server port")
    args = parser.parse_args()

    print(f"\n{'─'*48}")
    print(f"  Portfolio Builder")
    print(f"{'─'*48}")

    build()

    if args.serve:
        t = threading.Thread(target=serve, args=(args.port,), daemon=True)
        t.start()

    if args.watch or args.serve:
        try:
            watch()
        except KeyboardInterrupt:
            print("\n  Stopped.")
    else:
        print(f"  Done. Open output/index.html in your browser.\n")


if __name__ == "__main__":
    main()

