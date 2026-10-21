# Investor Financial Intelligence — Statement & Note Explorer (MISA demo)

> **This branch** (`claude/dreamy-wozniak-xb5mjr`) holds a standalone demo built for the
> Ministry of Investment of Saudi Arabia (MISA) opportunity. The FTA dashboards on `main`
> (`landing.html`, `executive.html`, `entity.html`) are untouched; the new app reuses their
> design system (dark gold-waves landing, glass/gold dashboard pages).

The demo ingests a listed company's audited annual financial statements (PDF), rebuilds the
primary statements with their **note references as live links**, indexes every note to the
consolidated financial statements, and presents an investment-authority view of the filing:
summary KPIs, an analyst brief, the auditor's opinion and key audit matters, flagged
disclosures, and a reviewer "lens" organised the way a MISA analyst would read a company.

Two real FY2024 filings from the Saudi Exchange are loaded:

| Filing | Ticker | Notes | What it shows off |
|---|---|---|---|
| Saudi Aramco — consolidated financial statements 2024 | 2222 | 40 | Scale, Government relationship, guarantees, 100+ subsidiaries |
| Saudi Ceramic Company — consolidated financial statements 2024 | 2040 | 35 | Losses, impairments, covenant breach, fire, restated comparatives, predecessor auditor's qualified opinion |

## Pages

| Page | What it does |
|---|---|
| `index.html` | Landing page (dark gold-waves design) |
| `portfolio.html` | Filings portfolio: KPIs across filings, comparison table, flags, ingestion pipeline |
| `company.html?c=aramco` | Statement explorer for one filing — five sub-views: |
| &nbsp;&nbsp;`#overview` | KPIs, analyst brief, charts, auditor card, flagged notes |
| &nbsp;&nbsp;`#statements/<id>` | The primary statements; every **Note** reference is a chip that opens the note in a side drawer |
| &nbsp;&nbsp;`#notes/<n>` | Note index with search; full note view with key figures, sub-sections, back-links and the extracted source text |
| &nbsp;&nbsp;`#map` | Cross-reference map: statement lines ⟷ notes, interactive |
| &nbsp;&nbsp;`#lens` | Investor lens: 12 review areas with status, finding and the supporting notes |

### How the note linking works

1. `pipeline/extract_notes.py` runs `pdftotext -layout`, strips page furniture, and splits the
   notes section by its numbered headings (requiring note numbers to increase by one, which
   separates real headings from footnotes and "continued" headers). It records each note's
   text, PDF page, printed page, sub-headings and the other notes it cites.
2. `pipeline/curated/<id>.company.json` holds the primary statements exactly as printed —
   each line with its note reference (`"24"`, `"5,6"`, `"35(a)"`, `"16.1"`, `"5-E,5-F"`), plus
   metadata, auditor's report, KPIs, chart series, the investor lens and the brief.
3. `pipeline/curated/<id>.notes.json` is the reviewed overlay per note: plain-English summary,
   key figures, sub-sections, cross-references, tags, investor relevance and a flag.
4. `pipeline/build_data.py` merges the three, parses every note reference (including
   sub-note ids such as `(a)` or `16.1`), writes the back-links (`referencedBy`,
   `mentionedIn`) onto each note and emits `data/<id>.js` and `data/registry.js`.
5. In the browser, `assets/app.js` renders the chips, the drawer (summary → key figures →
   sub-sections → "referenced from" → "refers to" → source text, with the cited sub-section
   highlighted) and the cross-reference map. A note cited by another note is itself a link,
   so Note 2 → Note 7 → Note 33 chains can be followed without leaving the page.

## Branding

The palette is Saudi green with gold accents (tokens at the top of `assets/theme.css`;
change `--g600`, `--gold` and `--nav-grad` to retheme). The Ministry lockup in the nav
(national emblem + "وزارة الاستثمار / Ministry of Investment") is drawn inline in
`assets/app.js` so the demo has no external image dependency. To use the official
artwork instead, drop the file in `assets/` and set, before `FSX.nav()` runs:

```js
FSX.LOGO_IMG = 'assets/misa-logo.svg';   // or .png — replaces the inline lockup everywhere
```

## Run locally

Everything is static — no build step, no API key, no CDN dependency for charts.

```bash
# any static server works; python is enough
python3 -m http.server 8000
# open http://localhost:8000/index.html
```

Opening `index.html` directly from the file system also works.

## Deploy on Railway

The repo root carries a `Dockerfile` (nginx serving the static files) and a `railway.json`.

1. Railway → **New Project → Deploy from GitHub repo** → this repo.
2. Service **Settings → Source → branch** = `claude/dreamy-wozniak-xb5mjr`
   (the Dockerfile and the `/index.html` health check are picked up automatically).
3. Settings → Networking → **Generate Domain**. No environment variables are needed;
   nginx listens on the `PORT` Railway injects.

Any other static host works too (GitHub Pages from this branch, Netlify, S3): there is
no build step and no server-side code.

## Re-run the pipeline

```bash
python3 pipeline/extract_notes.py filings/aramco-2222-fy2024.pdf \
    --id aramco --style aramco --page-offset 3 --first-page 17 --out pipeline/out/aramco.notes.raw.json
python3 pipeline/extract_notes.py filings/saudi-ceramic-2040-fy2024.pdf \
    --id ceramic --style ceramic --page-offset 8 --first-page 14 --out pipeline/out/ceramic.notes.raw.json
python3 pipeline/build_data.py
```

Requires `pdftotext` (poppler-utils) and Python 3.10+.

### Adding another filing

1. Drop the PDF in `filings/`, run `extract_notes.py` (add a heading `style` if the filing
   numbers its notes differently).
2. Transcribe the primary statements into `pipeline/curated/<id>.company.json` with note
   references, and write (or generate) the note overlay `pipeline/curated/<id>.notes.json`.
3. `python3 pipeline/build_data.py` — the new filing appears in the portfolio automatically.

## Repository layout

```
index.html  portfolio.html  company.html     the app
assets/theme.css  assets/app.js              design system + runtime (no dependencies)
data/aramco.js  data/ceramic.js  data/registry.js   generated bundles (do not edit by hand)
filings/*.pdf                                the source filings (deep-linked by page from the UI)
pipeline/extract_notes.py  build_data.py     the ingestion pipeline
pipeline/curated/                            reviewed inputs (statements, notes overlay, schema)
pipeline/out/                                raw extraction output
landing.html  executive.html  entity.html    the FTA dashboards from main (unchanged)
```
