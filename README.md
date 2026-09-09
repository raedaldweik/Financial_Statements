# Financial Crime Complaint Analyzer — Agentic AI Demo

> **This branch** (`claude/police-fraud-demo-jfc7w3`) contains a standalone demo app.
> The dashboards on `main` are untouched; this app reuses their exact design
> system (gold-waves landing, glass/gold dashboard pages) with all logos and
> customer references removed.

A demo for police financial investigation units, built around a real story:
a victim pays for a product online, it never arrives, the seller disappears —
and when the police call, the officer has a folder of screenshots and no idea
what happened. The platform fixes that in two acts.

**Act 1 — the citizen.** An e-Crime reporting portal: describe what
happened, enter the beneficiary details you were given, attach the chat
screenshots, the payment confirmation and a bank statement, submit, get a
reference number.

**Act 2 — the investigator.** A case-management workspace: a queue of open
cases (sortable by risk score, date or amount) where the new submission
appears immediately, is analysed in the background, and flips to *Ready for
review*. Opening a case shows the case file an investigator actually needs:

1. **Case narrative** — what happened in plain chronological language, key
   facts, evidence assessment (verified / partial / unverified), timeline.
2. **Investigation** — complaint-history matches (the same account, IBAN,
   phone or company in other complaints, with the exact identifiers
   matched), entity resolution, open-source and registry checks, money
   movement, key findings. No network diagram — that is SAS Visual
   Investigator's job in the next step.
3. **Recommendations** — prioritised actions with addressee and timeframe
   (six-month statements and KYC from the bank, freeze, telecom data,
   platform preservation, consolidation), each with a **Draft** button.
4. **Evidence** — the submitted screenshots and statement, plus the
   complainant's statement.

A case assistant (bottom-right) answers questions about the file and drafts
the requests with the exact identifiers.

**The scenario (from the client scenario pack):** Ahmed Hassan pays AED 12,500
to Mubarak Salem, account 5660609, IBAN AE600340005660609, for an electronics
bundle from "Prime Gulf Electronics". The queue already holds FC-2026-0187 —
a AED 275,000 citizenship-by-investment fraud paid to the **same account** —
and FC-2026-0204, paid to the "alternative account" the seller offered in the
chat. Three complaints, two accounts, one network: AED 296,400.

## Pages

| Page | Role | What it does |
|---|---|---|
| `index.html` | — | Landing page (dark gold-waves design) with both entrances |
| `report-fraud.html` | Citizen | e-Crime reporting form + evidence upload (`?sample=1` pre-fills the demo submission) |
| `cases.html` | Investigator | Case queue: KPIs, search, filters, sort by risk / date / amount |
| `case.html?ref=…` | Investigator | Case file: narrative · investigation · recommendations · evidence, chat assistant |
| `analysis.html?ref=…` | Investigator | Analysis log — the six agents' activity and findings for a case |

## The six agents

1. **Intake & Triage** — classifies the complaint, briefs the specialists
2. **Conversation Forensics** — reads the screenshots (vision), extracts identifiers, names the manipulation techniques
3. **Financial Analysis** — parses the statement PDFs, isolates the fraud transfers
4. **OSINT** — registries, telecom, domains, social, scam databases (5 tools over bundled data)
5. **Complaint History Cross-Reference** — prior complaints & known entities (3 tools) — first offence or a series?
6. **Lead Investigator** — synthesizes the structured report (schema-enforced JSON)

## Live mode vs. simulation mode

- **Live** (`ANTHROPIC_API_KEY` set): real agentic runs — upload your own
  screenshots/statements, ask follow-up questions.
- **Recorded** (no key): streams a bundled recorded run with identical UX —
  the no-internet / no-key safety net at the client site. If a live run fails
  for any reason (key, quota, network) the case is completed with the
  recorded analysis automatically, so the queue never shows a failed case.
- Force a mode for one browser with `report-fraud.html?mode=live` or
  `?mode=replay` (`?mode=auto` resets). Nothing in the UI shows which mode
  ran; the `error` field on `/api/cases/{ref}` records a live failure.

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
   | `DEMO_TZ` | no | timezone for filing timestamps, default `Asia/Dubai` |
   | `DEMO_TODAY` | no | pin "today" (`2026-09-10`) for a rehearsal; normally unset |

4. Settings → Networking → **Generate Domain**.

## Demo data

All names, banks, companies, phones and records are fictional. Everything
lives in `backend/demo_data/`:

- `conversation.txt` → rendered into `chat_1..3.png` by
  `backend/scripts/make_chat_screenshots.py` (WhatsApp-style screenshots)
- `receipt.jpg` ← `backend/scripts/make_receipt.py` (Example Bank transfer confirmation)
- `bank_statement.pdf` ← `backend/scripts/make_statement_pdf.py`
- `osint.json`, `intel_db.json` — the OSINT sources and prior-complaint data
  the agent tools query
- `replay.json` — the recorded run (filing-date placeholders such as
  `{{FILED_LONG}}` are filled with the real submission date at run time)
- `cases.json` — the seeded case queue (11 cases with their case files)

Swap these files to retheme the storyline for another client.
