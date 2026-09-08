# Fraud Complaint Analyzer — Agentic AI Demo (Police Financial Investigation)

> **This branch** (`claude/police-fraud-demo-jfc7w3`) contains a standalone demo app.
> The `main` branch (FTA dashboard HTML files) is untouched.

A demo for police financial investigation units showing how an **agentic AI
engine fuses many evidence sources** — a victim's chat conversation, bank
statement PDFs, automatic OSINT collection and the unit's own intelligence
repository — into one investigation report, network map and action plan.

**The storyline:** a victim pays an Instagram watch shop AED 18,500, is then
squeezed for a fake AED 2,750 "customs deposit", gets ghosted, and files a
complaint. She attaches her WhatsApp export and bank statement. On **Run AI
analysis**, six AI agents work the case live on screen — and the intelligence
cross-reference reveals it's the **fourth strike of one serial fraud network**
(same IBAN, same phone, same script — combined losses AED 67,200), converging
on one controller behind a company with a cancelled trade license.

The intelligence repository is a bundled stand-in for **SAS Visual
Investigator**; the report ends with a "Create case in Visual Investigator"
hook (step-2 integration point). The follow-up Q&A panel mirrors the
Investigation Assistant pattern from the SAS copilot demo.

## The six agents

| # | Agent | What it does | Tools |
|---|---|---|---|
| 1 | 📋 Intake & Triage | Classifies the complaint, extracts claims, briefs the specialists | — |
| 2 | 💬 Conversation Forensics | Reconstructs the chat (text or screenshot via vision), extracts identifiers, names the manipulation techniques | — |
| 3 | 🏦 Financial Analysis | Parses the statement PDF, isolates the fraud transfers, confirms the loss | — |
| 4 | 🌐 OSINT | Works the identifiers through registries, telecom, domains, social, scam DBs | 5 lookup tools |
| 5 | 🕸️ Intelligence Cross-Reference | Searches prior complaints & expands the entity network — first offence or series? | 3 repository tools |
| 6 | 🎖️ Lead Investigator | Synthesizes everything into a structured report (schema-enforced JSON) | — |

Every tool call streams to the UI live (SSE), so the audience sees the agents
actually investigating, not a loading spinner.

## Live mode vs. simulation mode

- **Live** (`ANTHROPIC_API_KEY` set): real agentic runs against Claude — you
  can upload your own conversation/statement and ask follow-up questions.
- **Simulation** (no key, or selected in the UI): streams a bundled recorded
  run with identical UX. Clearly labelled **SIMULATION** in the UI — your
  no-internet / no-key safety net at the client site.

## Run locally

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env        # add your ANTHROPIC_API_KEY (optional)
uvicorn main:app --reload
# open http://localhost:8000
```

## Deploy on Railway

1. Railway → **New Project → Deploy from GitHub repo** → pick this repo.
2. In the service settings, set the **branch** to `claude/police-fraud-demo-jfc7w3`
   (Settings → Source). Build is automatic via the root `Dockerfile`;
   healthcheck is `/api/health` (from `railway.json`).
3. **Variables** tab:

   | Variable | Required | Notes |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | for live mode | Without it the app runs in simulation mode |
   | `MODEL` | no | default `claude-opus-5`; set `claude-sonnet-5` for snappier turns |
   | `LLM_EFFORT` | no | default `medium` |

4. Generate a domain (Settings → Networking → Generate Domain). Done.

## Demo flow (suggested script)

1. **Load sample case** — complaint + WhatsApp export + bank statement appear
   (open the sample PDF to show it's a real document).
2. **Run AI analysis** — narrate the agents as they work; expand the OSINT
   tool calls ("it's checking the trade license registry right now…").
3. When the cross-reference agent fires: **"this is not her first complaint —
   same IBAN in two prior cases, same phone in a third."**
4. Report page: risk score, linked prior complaints, the network graph
   converging on one controller, and the recommended actions (freeze first —
   they cash out in 48h).
5. **Ask the assistant**: e.g. *"Draft the freeze request for Gulf Trust
   Bank"* or *"What do we know about the money mule?"* (live mode).
6. Close on the **Visual Investigator** panel: in production this pushes the
   consolidated case into SAS VI — that's step 2.

## Notes

- All names, banks, companies, phone numbers and records are fictional,
  authored for this demo.
- Data lives in `backend/demo_data/` — swap `conversation.txt`,
  `bank_statement.pdf` (regenerate via `backend/scripts/make_statement_pdf.py`),
  `osint.json` and `intel_db.json` to retheme the storyline.
- No database: cases are in-memory per container (fine for a demo).
