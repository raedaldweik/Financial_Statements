# Financial Crime Complaint Analyzer — Agentic AI Demo

> **This branch** (`claude/police-fraud-demo-jfc7w3`) contains a standalone demo app.
> The dashboards on `main` are untouched; this app reuses their exact design
> system (gold-waves landing, glass/gold dashboard pages) with all logos and
> customer references removed.

A demo for police financial investigation units showing how an **agentic AI
engine fuses many evidence sources** — the complaint conversation **as
screenshot images**, one or more **bank/financial statement PDFs**, automatic
OSINT collection and the unit's own complaint history — into one investigation
report and action plan.

**The storyline:** a victim pays an Instagram watch shop AED 18,500, is
squeezed for a fake AED 2,750 "customs deposit", gets ghosted, and files a
complaint with 3 WhatsApp screenshots and her bank statement. On **Run AI
Analysis**, six AI agents work the case live on screen — and the
complaint-history cross-reference reveals it's the **fourth strike of one
serial fraud network** (same IBAN, same phone, same script — combined losses
AED 67,200). The report closes with a step-2 hand-off: the consolidated
network case continues in SAS Visual Investigator (not part of this demo).

## Pages (same structure as the dashboards on `main`)

| Page | Design | What happens |
|---|---|---|
| `index.html` | Dark gold-waves landing | Entry + "Run the Sample Case" |
| `intake.html` | Light glass dashboard | Complaint form, screenshot & statement uploads, OSINT/history cards |
| `analysis.html` | Light glass dashboard | The six agents streaming live (SSE): tool calls + findings memos |
| `report.html` | Light glass dashboard | KPI strip, ✦ case brief, key findings, linked prior complaints table, losses chart, timeline, financial flow, entities, actions, Q&A assistant |

## The six agents

1. 📋 **Intake & Triage** — classifies the complaint, briefs the specialists
2. 💬 **Conversation Forensics** — reads the screenshots (vision), extracts identifiers, names the manipulation techniques
3. 🏦 **Financial Analysis** — parses the statement PDFs, isolates the fraud transfers
4. 🌐 **OSINT** — registries, telecom, domains, social, scam databases (5 tools over bundled data)
5. 🕸️ **Complaint History Cross-Reference** — prior complaints & known entities (3 tools) — first offence or a series?
6. 🎖️ **Lead Investigator** — synthesizes the structured report (schema-enforced JSON)

## Live mode vs. simulation mode

- **Live** (`ANTHROPIC_API_KEY` set): real agentic runs — upload your own
  screenshots/statements, ask follow-up questions.
- **Simulation** (no key, or selected in the UI): streams a bundled recorded
  run with identical UX, labelled **Simulation** in the nav — the
  no-internet / no-key safety net at the client site.

## Run locally

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env        # add ANTHROPIC_API_KEY for live mode (optional)
uvicorn main:app --reload
# open http://localhost:8000
```

## Deploy on Railway

1. Railway → **New Project → Deploy from GitHub repo** → this repo.
2. Service **Settings → Source → branch** = `claude/police-fraud-demo-jfc7w3`
   (root `Dockerfile` + `railway.json` healthcheck are picked up automatically).
3. **Variables**:

   | Variable | Required | Notes |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | for live mode | without it the app runs in simulation mode |
   | `MODEL` | no | default `claude-opus-5`; `claude-sonnet-5` for snappier turns |
   | `LLM_EFFORT` | no | default `medium` |

4. Settings → Networking → **Generate Domain**.

## Demo data

All names, banks, companies, phones and records are fictional. Everything
lives in `backend/demo_data/`:

- `conversation.txt` → rendered into `chat_1..3.png` by
  `backend/scripts/make_chat_screenshots.py` (WhatsApp-style screenshots)
- `bank_statement.pdf` ← `backend/scripts/make_statement_pdf.py`
- `osint.json`, `intel_db.json` — the OSINT sources and prior-complaint data
  the agent tools query
- `replay.json` — the recorded simulation run

Swap these files to retheme the storyline for another client.
