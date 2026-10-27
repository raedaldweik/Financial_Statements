"""Model-driven curation: company & auditor facts, per-note overlay, key-row mapping,
analyst brief and investor lens. All prompts return JSON constrained by a schema; every
number quoted must come from the supplied text, and every note cited must exist.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import config
from llm import LLM
from pipeline.analysis import KEYROWS_SCHEMA, KEYROWS_SYSTEM, KEYS, compact_statements

# ───────────────────────── company & auditor ─────────────────────────
COMPANY_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "full legal name as printed"},
        "shortName": {"type": "string", "description": "short name, 1-3 words"},
        "ticker": {"type": ["string", "null"], "description": "exchange ticker if printed, else null"},
        "exchange": {"type": ["string", "null"]},
        "sector": {"type": "string", "description": "sector and activity in a few words"},
        "hq": {"type": ["string", "null"]},
        "fy": {"type": "string", "description": "e.g. 'FY2024'"},
        "periodEnd": {"type": "string", "description": "e.g. 'December 31, 2024'"},
        "years": {"type": "array", "items": {"type": "string"}, "description": "[current year label, prior year label]"},
        "unit": {"type": "string", "description": "e.g. 'SAR million', 'SAR thousand'"},
        "scale": {"type": "number", "description": "1000000 for millions, 1000 for thousands, 1 for units"},
        "currency": {"type": "string"},
        "approvedBy": {"type": ["string", "null"]},
        "approvedOn": {"type": ["string", "null"]},
        "signatories": {"type": "array", "items": {"type": "string"}},
        "auditor": {
            "type": "object",
            "properties": {
                "firm": {"type": ["string", "null"]},
                "partner": {"type": ["string", "null"]},
                "license": {"type": ["string", "null"]},
                "reportDate": {"type": ["string", "null"]},
                "opinion": {"type": "string", "enum": ["Unmodified", "Qualified", "Adverse", "Disclaimer", "Unknown"]},
                "opinionText": {"type": ["string", "null"], "description": "one-sentence paraphrase of the opinion paragraph"},
                "materiality": {"type": ["string", "null"], "description": "materiality disclosure if present"},
                "emphasisOfMatter": {"type": ["string", "null"]},
                "otherMatter": {"type": ["string", "null"], "description": "other-matter paragraph (e.g. predecessor auditor, qualified prior-year opinion), verbatim-faithful summary"},
                "goingConcern": {"type": ["string", "null"], "description": "material-uncertainty / going-concern paragraph if present"},
                "kams": {"type": "array", "items": {"type": "object", "properties": {
                    "title": {"type": "string"}, "summary": {"type": "string", "description": "2 sentences with the key figures"},
                    "notes": {"type": "array", "items": {"type": "string"}, "description": "note references the KAM points to, e.g. ['2(e)', '6']"}},
                    "required": ["title", "summary", "notes"], "additionalProperties": False}},
            },
            "required": ["firm", "partner", "license", "reportDate", "opinion", "opinionText", "materiality", "emphasisOfMatter", "otherMatter", "goingConcern", "kams"],
            "additionalProperties": False,
        },
    },
    "required": ["name", "shortName", "ticker", "exchange", "sector", "hq", "fy", "periodEnd", "years", "unit", "scale", "currency", "approvedBy", "approvedOn", "signatories", "auditor"],
    "additionalProperties": False,
}
COMPANY_SYSTEM = """You extract entity facts and the independent auditor's report from an audited annual financial statements filing for an investment-authority reviewer.
Use only what the document says. Quote figures and dates exactly. If the auditor's report is a scanned image, read it from the attached pages. Mark the opinion type precisely (an unmodified opinion with an emphasis-of-matter or other-matter paragraph is still "Unmodified")."""


def company_facts(llm: LLM, pdf_subset, text: str) -> dict:
    content = []
    if pdf_subset is not None:
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_subset}})
    content.append({"type": "text", "text": "Extracted text of the cover, contents, auditor's report and first statement pages:\n\n" + text[:60000]})
    return llm.json(system=COMPANY_SYSTEM, content=content, schema=COMPANY_SCHEMA, effort="medium", max_tokens=8000, label="company")


# ───────────────────────── notes ─────────────────────────
NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "n": {"type": "string"},
        "title": {"type": "string", "description": "Title case, no trailing punctuation"},
        "category": {"type": "string", "enum": ["policy", "balance-sheet", "income", "equity", "cash-flow", "risk", "group", "tax", "disclosure"]},
        "summary": {"type": "string", "description": "2-4 plain-English sentences quoting the headline figures with the filing's unit"},
        "keyFigures": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "v": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2, "description": "[current year, prior year] copied verbatim as printed, '–' when absent"}},
            "required": ["label", "v"], "additionalProperties": False}},
        "subnotes": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": ["string", "null"], "description": "as printed without trailing punctuation: '(a)', '16.1', 'A', or null if unnumbered"},
            "title": {"type": "string"}, "summary": {"type": "string", "description": "one sentence"}},
            "required": ["id", "title", "summary"], "additionalProperties": False}},
        "refs": {"type": "array", "items": {"type": "string"}, "description": "other note numbers this note's text explicitly refers to"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "investorRelevance": {"type": ["string", "null"], "description": "one sentence: why an investment-ministry reviewer should open this note; null if routine"},
        "flag": {"type": ["object", "null"], "properties": {"level": {"type": "string", "enum": ["info", "watch", "alert"]}, "text": {"type": "string"}},
                 "required": ["level", "text"], "additionalProperties": False},
    },
    "required": ["n", "title", "category", "summary", "keyFigures", "subnotes", "refs", "tags", "investorRelevance", "flag"],
    "additionalProperties": False,
}
NOTES_SCHEMA = {"type": "object", "properties": {"notes": {"type": "array", "items": NOTE_SCHEMA}}, "required": ["notes"], "additionalProperties": False}
NOTES_SYSTEM = """You curate the notes to audited financial statements for a financial-statement explorer used by reviewers at an investment ministry.

For each note you receive (number, title, extracted text), return the curated record. Rules:
- summary: factual, 2-4 sentences, quote exact figures with the unit (e.g. "SAR 1,637,299 million"). No speculation.
- keyFigures: at most 6 rows copied verbatim from the note's tables, ordered [current year, prior year]; "–" when a value is absent; negatives keep their parentheses. Empty array for narrative-only notes.
- subnotes: only genuine sub-sections that exist in the text, ids exactly as printed.
- refs: note numbers explicitly cited in the text ("Note 29(b)" → "29"; "Notes 12 and 23" → "12", "23"). Never the note's own number.
- flag: null unless the note contains something a reviewer must not miss — impairments, covenant breaches, going-concern language, restatements, large contingencies or guarantees, significant events (fires, disputes, tax assessments), customer or related-party concentration, material subsequent events. level: alert (material, needs action), watch (notable), info (worth knowing).
- investorRelevance: think like a ministry-of-investment analyst assessing the company: ownership and control, government exposure, debt and maturities, commitments, contingencies, segments and geography, related parties, dividends, tax position, group structure. One sentence; null for routine policy notes.
Every figure you write must appear in the note text you were given."""


def curate_notes(llm: LLM, raw_notes: list[dict], unit: str, company_name: str, progress=None) -> dict[str, dict]:
    batches = [raw_notes[i:i + config.NOTES_PER_CALL] for i in range(0, len(raw_notes), config.NOTES_PER_CALL)]
    results: dict[str, dict] = {}

    def run(batch):
        parts = [f"Company: {company_name}. Presentation unit: {unit}. Notes in this filing: 1–{len(raw_notes)}.\n"]
        for n in batch:
            txt = n["text"]
            if len(txt) > config.NOTE_TEXT_CAP:
                txt = txt[:config.NOTE_TEXT_CAP] + f"\n[... {len(n['text']) - config.NOTE_TEXT_CAP} more characters truncated ...]"
            parts.append(f"=== NOTE {n['n']}: {n['title']} (PDF page {n['pdfPage']}) ===\n{txt}\n")
        data = llm.json(system=NOTES_SYSTEM, content=[{"type": "text", "text": "\n".join(parts)}], schema=NOTES_SCHEMA,
                        model=config.MODEL_NOTES, effort="medium", max_tokens=24000, label=f"notes {batch[0]['n']}-{batch[-1]['n']}")
        return {str(x["n"]): x for x in data.get("notes", [])}

    with ThreadPoolExecutor(max_workers=max(1, config.PARALLEL_NOTE_CALLS)) as ex:
        futures = {ex.submit(run, b): b for b in batches}
        for fut in futures:
            b = futures[fut]
            try:
                results.update(fut.result())
                if progress:
                    progress(f"notes {b[0]['n']}–{b[-1]['n']} curated")
            except Exception as e:  # one failed batch must not sink the filing
                if progress:
                    progress(f"notes {b[0]['n']}–{b[-1]['n']} failed: {str(e)[:120]}")
    # sanitise refs to existing notes
    valid = {str(n["n"]) for n in raw_notes}
    for n, rec in results.items():
        rec["refs"] = [r for r in rec.get("refs", []) if r in valid and r != n]
    return results


# ───────────────────────── key rows ─────────────────────────
def key_rows(llm: LLM, statements: list[dict]) -> dict:
    content = [{"type": "text", "text": compact_statements(statements)}]
    raw = llm.json(system=KEYROWS_SYSTEM, content=content, schema=KEYROWS_SCHEMA, effort="medium", max_tokens=4000, label="keyrows")
    # back to {key: {stmt, row, note} | None}, validating every index against the transcribed rows
    by_id = {s["id"]: s for s in statements}
    data: dict = {k: None for k in KEYS}
    data["years"] = raw.get("years") or []
    for ref in raw.get("rows") or []:
        k, st = ref.get("key"), by_id.get(ref.get("stmt"))
        if k not in KEYS or data.get(k) is not None or not st:
            continue
        i = ref.get("row", -1)
        if 0 <= i < len(st["rows"]) and "v" in st["rows"][i]:
            data[k] = {"stmt": ref["stmt"], "row": i, "note": st["rows"][i].get("n")}
    return data


# ───────────────────────── analysis: brief + lens + segment charts ─────────────────────────
LENS_AREAS = ["Ownership & control", "Government relationship", "Going concern & profitability", "Debt capacity, covenants & liquidity",
              "Capital commitments & investment", "Contingencies & guarantees", "Asset quality & impairments", "Segments & geography",
              "Customer & related-party concentration", "Tax & zakat position", "Shareholder returns", "Audit, governance & comparability"]
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "brief": {"type": "string", "description": "Analyst brief, 3 short paragraphs of HTML separated by <br><br>; bold key figures with <strong>; cite notes with [[n:24]] tokens; end with a paragraph wrapped in <em class=\"rec\">...</em> listing what a reviewer should focus on"},
        "lens": {"type": "array", "items": {"type": "object", "properties": {
            "area": {"type": "string"},
            "status": {"type": "string", "enum": ["green", "amber", "red"]},
            "headline": {"type": "string", "description": "one sentence finding with the key figure"},
            "detail": {"type": "string", "description": "2-3 sentences of supporting facts with figures"},
            "notes": {"type": "array", "items": {"type": "string"}, "description": "note numbers supporting the finding"}},
            "required": ["area", "status", "headline", "detail", "notes"], "additionalProperties": False}},
        "segments": {"type": ["object", "null"], "properties": {
            "labels": {"type": "array", "items": {"type": "string"}}, "revenue": {"type": "array", "items": {"type": ["number", "null"]}},
            "ebit": {"type": "array", "items": {"type": ["number", "null"]}, "description": "segment result before interest and tax (or profit before zakat/tax) in the same unit; null if not disclosed"},
            "note": {"type": "string"}}, "required": ["labels", "revenue", "ebit", "note"], "additionalProperties": False},
        "geography": {"type": ["object", "null"], "properties": {
            "labels": {"type": "array", "items": {"type": "string"}}, "revenue": {"type": "array", "items": {"type": ["number", "null"]}}, "note": {"type": "string"}},
            "required": ["labels", "revenue", "note"], "additionalProperties": False},
    },
    "required": ["brief", "lens", "segments", "geography"],
    "additionalProperties": False,
}
ANALYSIS_SYSTEM = """You are a senior analyst at a ministry of investment reviewing an audited annual filing. You receive: company and auditor facts, the transcribed primary statements, computed KPIs, and the curated notes (summaries and flags).

Write (1) an analyst brief and (2) an investor lens with exactly these twelve review areas, in this order:
{areas}

Rules:
- Every figure must come from the supplied material; cite the supporting notes by number. Use the filing's unit.
- status: green = satisfactory, amber = watch, red = attention required. Be decisive and specific; a company with losses, covenant breaches, restatements, qualified prior-year opinions or large guarantees must show it.
- If the filing has no information for an area, say so in the headline and use green.
- segments/geography: if a segment note discloses revenue (and result) by segment or geography, return the current-year series in the filing's unit with the note number; otherwise null.
"""


def analysis(llm: LLM, company: dict, statements: list[dict], derived: dict, curated_notes: dict[str, dict], raw_notes: list[dict]) -> dict:
    note_lines = []
    for n in raw_notes:
        c = curated_notes.get(str(n["n"]), {})
        fl = c.get("flag")
        note_lines.append(f"Note {n['n']} — {c.get('title') or n['title']}" + (f" [{fl['level'].upper()}: {fl['text']}]" if fl else "") + f"\n  {c.get('summary', '')[:900]}")
    facts = {k: company.get(k) for k in ("name", "sector", "fy", "periodEnd", "unit", "auditor", "approvedOn")}
    text = (f"COMPANY & AUDITOR FACTS\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n\n"
            f"COMPUTED KPIS AND RATIOS (unit {company.get('unit')})\n{json.dumps({'kpis': derived['kpis'], 'ratios': derived['ratios']}, ensure_ascii=False)}\n\n"
            f"PRIMARY STATEMENTS\n{compact_statements(statements)}\n\nNOTES\n" + "\n".join(note_lines))
    data = llm.json(system=ANALYSIS_SYSTEM.format(areas="\n".join(f"- {a}" for a in LENS_AREAS)), content=[{"type": "text", "text": text[:240000]}],
                    schema=ANALYSIS_SCHEMA, effort="high", max_tokens=16000, label="analysis")
    valid = {str(n["n"]) for n in raw_notes}
    data["brief"] = re.sub(r"\[\[n:([^\]]+)\]\]", lambda m: m.group(0) if re.match(r"\d{1,2}", m.group(1)) and re.match(r"\d{1,2}", m.group(1)).group(0) in valid else "", data.get("brief", ""))
    for item in data.get("lens", []):
        item["notes"] = [x for x in item.get("notes", []) if re.match(r"\d{1,2}", str(x)) and re.match(r"\d{1,2}", str(x)).group(0) in valid]
        if item.get("status") not in ("green", "amber", "red"):
            item["status"] = "amber"
    return data
