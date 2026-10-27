# Investor Financial Intelligence — Statement & Note Explorer (MISA)

> **This branch** (`claude/dreamy-wozniak-xb5mjr`) holds a standalone app built for the
> Ministry of Investment of Saudi Arabia (MISA) opportunity. The FTA dashboards on `main`
> (`landing.html`, `executive.html`, `entity.html`) are untouched; the app reuses their
> glass design system, re-themed to Saudi green and gold with the Ministry lockup.

Upload any company's audited annual financial statements (PDF). The server rebuilds the
primary statements with **every note reference as a live link**, splits and indexes the
notes, curates each note (summary, key figures, sub-sections, flags), computes KPIs and
charts, and writes an analyst brief and a twelve-area **investor lens** — each finding
citing the notes that support it. Saudi Ceramic FY2024 ships as a **sample filing** so a
fresh deployment shows what the output looks like (Aramco FY2024 is bundled too, for
`SAMPLES=ceramic,aramco`, and its PDF sits in `filings/` for a live upload); remove the
sample from the UI or start without it with `SEED_SAMPLES=0`.

## Pages

| Page | What it does |
|---|---|
| `index.html` | Landing page: drop a PDF to start |
| `upload.html` | Upload a statement (optional name, ticker, sector), watch the pipeline build it, manage your uploads and the samples |
| `portfolio.html` | All filings side by side: KPIs, open items, lens heat map; quick drop zone |
| `company.html?c=<id>` | One filing: overview · statements with note chips · note explorer · cross-reference map · investor lens |

## Two modes

| | Full ingestion (`ANTHROPIC_API_KEY` set) | Extraction-only (no key) |
|---|---|---|
| Statements | Transcribed by Claude from the statement pages (text + the PDF pages themselves), every line with its note reference | Parsed from the text layer by a deterministic heuristic |
| Notes | Split by heading, then curated: summary, key figures, sub-sections, cross-references, tags, investor relevance, flag | Split by heading; raw text and auto-detected cross-references only |
| Company & auditor | Entity facts, opinion type, key audit matters, other-matter / going-concern paragraphs (scanned auditor pages are read visually) | Name from the upload form / cover page |
| Analysis | KPIs and ratios computed in code from model-mapped rows; analyst brief; 12-area investor lens; segment and geography charts | KPIs and ratios from label matching |

Both modes build the same cross-reference index (statement line ⟷ note, sub-note aware),
so the explorer works either way. Opened without the server (file system or a static host),
the pages fall back to the pre-built demo bundles in `frontend/data/`.

## Run locally

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env        # add ANTHROPIC_API_KEY for full ingestion (optional)
uvicorn main:app --reload      # http://localhost:8000
```

Requires `pdftotext`, `pdfseparate` and `pdfunite` (poppler-utils) on the PATH and Python 3.11+.

## Deploy on Railway

1. Railway → **New Project → Deploy from GitHub repo** → this repo.
2. Service **Settings → Source → branch** = `claude/dreamy-wozniak-xb5mjr`
   (the root `Dockerfile` and the `/api/health` health check are picked up automatically).
3. **Variables**:

   | Variable | Required | Notes |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | for full ingestion | without it the server runs in extraction-only mode |
   | `MODEL` | no | default `claude-opus-5-5` (statements, auditor facts, brief, lens) |
   | `MODEL_NOTES` | no | default = `MODEL`; `claude-sonnet-5-5` makes note curation faster and cheaper |
   | `LLM_EFFORT` | no | `low` · `medium` (default) · `high` · `xhigh` · `max` |
   | `STORAGE_DIR` | no | default `/app/storage` |
   | `SAMPLES` | no | sample filings loaded at start: `ceramic` (default), `aramco`, `ceramic,aramco` or `all` |
   | `SEED_SAMPLES` | no | default `1`; `0` starts without any sample filing |

4. Settings → Networking → **Generate Domain**.
5. Optional but recommended: Settings → **Volumes** → mount a volume at `/app/storage` so
   uploaded filings survive redeploys (the sample filings are re-created at every start
   unless you removed them in the UI or set `SEED_SAMPLES=0`).

## API

| Method | Path | |
|---|---|---|
| `GET` | `/api/health` | mode (`full` / `extraction-only`), model, filing / sample / upload counts, upload cap |
| `GET` | `/api/filings` | registry: ready filings (summary) and filings in progress (stages, log) |
| `POST` | `/api/filings` | multipart: `file` (PDF), optional `name`, `ticker`, `sector` → `{id}`; the pipeline runs in the background |
| `GET` | `/api/filings/{id}` | the full bundle once ready, otherwise the processing status |
| `GET` | `/api/filings/{id}/status` | pipeline stages and log (polled by the UI) |
| `POST` | `/api/filings/{id}/rerun` | re-run the pipeline on the stored PDF |
| `DELETE` | `/api/filings/{id}` | remove a filing (a removed sample stays removed across restarts) |
| `DELETE` | `/api/samples` | remove the sample filings |
| `POST` | `/api/samples/restore` | put the sample filings back |
| `GET` | `/filings/{id}.pdf` | the source PDF (the UI deep-links to pages) |

## How ingestion works (`backend/pipeline/`)

1. **extract** — `pdftotext -layout` per page; page furniture (repeated headers/footers,
   page numbers, side-bar strips) removed statistically.
2. **segment** — the auditor's report, each primary statement and the notes section are
   located by title; notes are split on numbered headings in any of the common styles
   (`24. Revenue`, `16 - Borrowings`, `10.Trade`, `Note 7`), requiring numbers to increase by
   one so footnotes and "continued" headers are not mistaken for notes.
3. **statements** — the statement pages are sent to the model as a PDF document plus their
   text layer and transcribed line by line into the row schema (label, note reference,
   values per column, indent, total flags). Heuristic parse as fallback.
4. **company** — entity facts and the auditor's report (opinion, KAMs with their note
   references, other-matter, going-concern), from the cover, contents, auditor and first
   statement pages.
5. **notes** — curated in batches (6 notes per call, 3 calls in parallel) under a strict
   JSON schema; every figure must come from the note text.
6. **analysis** — the model maps statement rows to concepts (revenue, net result, totals,
   cash flows, borrowings…); KPIs, ratios and the balance/cash-flow charts are then computed
   in code; the model writes the brief, the twelve-area lens and segment series.
7. **build** — the cross-reference index: every `Note x` on a statement line (sub-notes such
   as `35(a)` or `16.1` included) becomes a back-link on that note; key audit matters and
   lens findings are recorded as mentions.

Model calls use structured outputs (JSON schema), adaptive thinking with `LLM_EFFORT`, prompt
caching on the system prompt, and the server-side refusal fallback. A typical 60-page filing
takes 2–5 minutes in full mode and well under a minute in extraction-only mode.

## Branding

Saudi green with gold accents (tokens at the top of `frontend/assets/theme.css`). The
Ministry lockup (national emblem + "وزارة الاستثمار / Ministry of Investment") is drawn
inline in `frontend/assets/app.js`. To use the official artwork set, before `FSX.nav()` runs:

```js
FSX.LOGO_IMG = 'assets/misa-logo.svg';
```

## Sample filings

Saudi Ceramic FY2024 (and Aramco FY2024 with `SAMPLES=ceramic,aramco`) are examples, not
fixtures: the app works on any filing you upload. They are copied into storage at start (`SEED_SAMPLES=1`), can be removed
with **Remove samples** on the upload or filings page (`DELETE /api/samples`; a removed
sample stays removed across restarts) and put back with **Restore samples**
(`POST /api/samples/restore`). `pipeline/curated/` holds their hand-reviewed statements and
note overlays; `python3 pipeline/build_data.py` rebuilds `backend/seed/*.bundle.json` and
`frontend/data/*.js` (static fallback).

## Repository layout

```
frontend/   index.html · upload.html · portfolio.html · company.html · assets/ (theme, runtime) · data/ (static samples)
backend/    main.py (FastAPI) · store.py · llm.py · config.py · pipeline/ (extract, statements, curate, analysis, build, run) · seed/
filings/    the two sample PDFs
pipeline/   curated inputs and the seed builder
Dockerfile · railway.json · .env.example
landing.html · executive.html · entity.html   the FTA dashboards from main (unchanged)
```

Known limits: fully scanned filings get statements and auditor facts (read visually) but
no note index unless the notes have a text layer; filings that number notes in an unusual
way may need a new heading pattern in `extract.py`.
