# Portfolio Generator

A Python-based static site generator inspired by [al-folio](https://github.com/alshedivat/al-folio).
Edit YAML data files — the build script handles the rest.

## Structure

```
portfolio/
├── build.py                  # Main build script
├── requirements.txt
├── data/
│   ├── profile.yml           # Name, bio, links, education, skills
│   ├── publications.yml      # Papers, workshops, preprints
│   ├── research.yml          # Research direction cards
│   └── experience.yml        # Positions, awards, conferences
├── templates/
│   └── index.html.jinja      # Jinja2 HTML template
├── assets/                   # Static files (images, PDFs, etc.)
│   └── pdf/
│       └── cv.pdf            # Drop your CV PDF here
└── output/
    └── index.html            # ← Generated site (deploy this)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Build once
python build.py

# 3. Build + watch for changes + local server
python build.py --serve --watch

# 4. Open http://localhost:8000
```

## Updating Content

Everything lives in `data/`. You never need to touch HTML or Python.

### Add a publication → `data/publications.yml`
```yaml
- title: "My New Paper"
  authors:
    - Vatsala Nema
    - Collaborator Name
  venue: "NeurIPS 2025"
  year: 2025
  status: published        # published | oral | workshop | preprint | inprep
  badge: Paper
  url: "https://arxiv.org/abs/..."
```

### Add a research direction → `data/research.yml`
```yaml
- title: "New Direction"
  desc: >
    Description of the research area.
```

### Add a position → `data/experience.yml`
```yaml
positions:
  - role: Postdoctoral Fellow
    org: "Lab Name · University"
    location: "City, Country"
    date: "2026 –"
    detail: >
      What you worked on.
```

### Update personal info → `data/profile.yml`
Change name, institution, advisor, bio paragraphs, contact links, etc.

## Photo portrait (Game of Life pixel effect)

Drop your photo at `assets/img/profile.jpg` before building.

```
assets/
└── img/
    └── profile.jpg   ← your photo goes here
```

The build script (with Pillow installed) auto-enhances it for best results:
- Centre-crops to portrait ratio
- Boosts contrast so cell thresholding is crisp
- Sharpens edges that would otherwise blur at cell resolution

**Best photo tips:**
- Plain or blurred background (face will stand out more)
- Good lighting / strong shadows on face
- Avoid very pale/low-contrast images

The JS engine then:
1. Samples the processed photo at cell resolution
2. Dark pixels → alive cells (seeded at page load)
3. Runs Conway's GoL normally
4. Every ~55 generations, re-injects the photo seed so your portrait stays visible but is always evolving



```bash
# Build the site
python build.py

# Copy output/index.html (and assets/) to your GitHub Pages repo root
cp output/index.html ../YourUsername.github.io/index.html
cp -r output/assets  ../YourUsername.github.io/
```

Or configure GitHub Actions to run `build.py` on push automatically.
