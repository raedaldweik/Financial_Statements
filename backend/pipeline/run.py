"""Pipeline orchestrator: one uploaded PDF → one dashboard bundle, with live stage status.

Full mode (ANTHROPIC_API_KEY set): statements transcribed by the model from the statement
pages, notes curated, investor lens written. Extraction-only mode: deterministic parsing
only — statements parsed heuristically, notes split and indexed with their raw text, KPIs
matched by label; no summaries, flags or lens.
"""
from __future__ import annotations

import base64
import logging
import re
import json
import time
import traceback
from pathlib import Path

import config
from pipeline.fingerprint import sha256_file, text_fingerprint
import store
from llm import LLM
from pipeline import extract as ex
from pipeline.analysis import KEYS, derive
from pipeline.build import assemble
from pipeline.curate import analysis as llm_analysis, company_facts, curate_notes, key_rows
from pipeline.statements import coerce_statements, heuristic_statement, llm_statements, subset_pdf

log = logging.getLogger("misa.pipeline")

LABEL_KEYS = {
    "revenue": r"^(total\s+)?(revenue|revenues|sales|turnover)(,?\s*net)?$",
    "costOfSales": r"^cost of (sales|revenue|revenues|goods sold)$",
    "grossProfit": r"^gross (profit|margin)",
    "operatingIncome": r"^operating (income|profit|\(?loss\)?|result)",
    "profitBeforeTax": r"^(income|profit|loss|net (loss|profit|income)) before (income )?tax|before zakat",
    "netIncome": r"^(net (income|loss|profit)( for the (year|period))?|(profit|loss) for the (year|period)|net (loss|profit) for the year)$",
    "eps": r"(earnings|loss|losses) per share",
    "totalAssets": r"^total assets$",
    "currentAssets": r"^(total )?current assets$",
    "nonCurrentAssets": r"^(total )?non[- ]current assets$",
    "totalEquity": r"^total equity$",
    "totalLiabilities": r"^total liabilities$",
    "currentLiabilities": r"^(total )?current liabilities$",
    "nonCurrentLiabilities": r"^(total )?non[- ]current liabilities$",
    "cash": r"^cash and (cash equivalents|bank balances)$",
    "shortTermInvestments": r"^short[- ]term (investments|deposits)$",
    "borrowingsCurrent": r"^(short[- ]term (borrowings|loans)|borrowings|loans and borrowings|current portion of (long[- ]term )?(borrowings|loans))",
    "borrowingsNonCurrent": r"^(long[- ]term (borrowings|loans)|borrowings|loans and borrowings)",
    "operatingCF": r"^net cash .*operating",
    "investingCF": r"^net cash .*invest",
    "financingCF": r"^net cash .*financ",
    "capex": r"(purchase of|additions to|payments for|capital expenditure).*(property|plant|equipment)|^capital expenditures?",
    "dividendsPaid": r"^dividends? paid",
    "openingCash": r"cash and cash equivalents at (the )?beginning",
    "closingCash": r"cash and cash equivalents at (the )?end",
    "netChangeCash": r"^net (increase|decrease|change).*cash",
}
STMT_FOR = {"revenue": "income", "costOfSales": "income", "grossProfit": "income", "operatingIncome": "income", "profitBeforeTax": "income", "netIncome": "income", "eps": "income",
            "operatingCF": "cashflow", "investingCF": "cashflow", "financingCF": "cashflow", "capex": "cashflow", "dividendsPaid": "cashflow", "openingCash": "cashflow", "closingCash": "cashflow", "netChangeCash": "cashflow"}


def heuristic_keyrows(statements: list[dict]) -> dict:
    out = {k: None for k in KEYS}
    for key, pat in LABEL_KEYS.items():
        rx = re.compile(pat, re.I)
        pref = STMT_FOR.get(key, "balance")
        ordered = sorted(statements, key=lambda s: 0 if s["id"].startswith(pref) else 1)
        found = None
        for st in ordered:
            section = ""
            for i, r in enumerate(st["rows"]):
                if r.get("s") or r.get("h"):
                    section = r["l"].lower()
                if "v" not in r or not rx.search(r["l"].strip().rstrip(":")):
                    continue
                if key == "borrowingsCurrent" and "non-current" in section:
                    continue
                if key == "borrowingsNonCurrent" and ("current" in section and "non" not in section):
                    continue
                found = {"stmt": st["id"], "row": i, "note": r.get("n")}
                break
            if found:
                break
        out[key] = found
    out["years"] = next((s["cols"][:2] for s in statements if s["cols"] and re.match(r"20\d\d", s["cols"][0])), ["current", "prior"])
    return out


def detect_unit(text: str) -> tuple[str, float, str]:
    t = text.lower()
    cur = "SAR" if re.search(r"saudi riyal|\bsar\b|\bsr\b", t) else ("USD" if "us dollar" in t or "usd" in t else ("AED" if "dirham" in t or "aed" in t else "SAR"))
    if re.search(r"millions? of|in millions|\bmillions?\b", t):
        return f"{cur} million", 1e6, cur
    if re.search(r"thousands? of|in thousands|'000|\bthousands?\b", t):
        return f"{cur} thousand", 1e3, cur
    return cur, 1, cur


def _stage(fid, sid):
    class _S:
        def __enter__(self):
            self.t0 = time.time(); store.stage(fid, sid, "running"); return self
        def info(self, msg):
            store.stage(fid, sid, "running", info=msg, log=msg)
        def __exit__(self, et, ev, tb):
            ms = int((time.time() - self.t0) * 1000)
            store.stage(fid, sid, "failed" if et else "done", ms=ms)
            return False
    return _S()


def _restore(fid: str, meta: dict, cached: dict, src: str, sha: str, fp: str, docmap) -> None:
    """The document was processed before: reuse that analysis for this upload."""
    b = json.loads(json.dumps(cached))
    b.update({"id": fid, "pdf": f"filings/{fid}.pdf", "createdAt": meta.get("createdAt", time.time()), "sha256": sha, "textFingerprint": fp,
              "mode": "full" if cached.get("mode") in (None, "full", "curated") else cached["mode"],
              "restoredFrom": {"id": src, "processedAt": cached.get("createdAt")}})
    if meta.get("name"):
        b["shortName"] = meta["name"]
    if meta.get("ticker"):
        b["ticker"] = meta["ticker"]
    if meta.get("sector"):
        b["sector"] = meta["sector"]
    b["warnings"] = [w for w in cached.get("warnings", []) if "API" not in w]
    store.update_status(fid, mode=b["mode"])
    with _stage(fid, "segment") as s:
        s.info(f"document recognised: the same filing was processed on {time.strftime('%d %b %Y', time.localtime(cached.get('createdAt') or time.time()))}; that analysis is restored")
    for sid, msg in (("statements", f"{len(b.get('statements', []))} statements restored"), ("company", f"{b.get('shortName') or b.get('name')} · {b.get('fy', '')} · {((b.get('auditor') or {}).get('firm') or 'auditor n/a')}"),
                     ("notes", f"{len(b.get('notes', []))} notes restored with their summaries and flags"), ("analysis", f"{len(b.get('lens', []))} investor-lens findings restored")):
        with _stage(fid, sid) as s:
            s.info(msg)
    with _stage(fid, "build") as s:
        store.save_bundle(fid, b)
        st = b.get("stats") or {}
        s.info(f"{st.get('links', 0)} cross-references from {st.get('linesWithNotes', 0)} statement lines to {st.get('notesReferenced', 0)} notes")
    store.update_status(fid, state="ready", finishedAt=time.time(), warnings=b["warnings"])


def run(fid: str) -> None:
    d = store.filing_dir(fid)
    pdf = d / "source.pdf"
    meta = store.meta(fid) or {}
    pdf_sha = sha256_file(pdf)
    llm = LLM()
    mode = "full" if llm.enabled else "extraction"
    store.update_status(fid, state="running", startedAt=time.time(), error=None, mode=mode)
    warnings: list[str] = []
    if config.llm_configured() and not llm.enabled:
        from llm import KEY_STATUS
        warnings.append(f"The analysis service could not be used: ANTHROPIC_API_KEY is set on the server but {KEY_STATUS.get('error') or 'the API rejected it'}. "
                        "The filing carries statements, notes and cross-references only; fix the key in the server variables, redeploy and run the filing again.")
    try:
        with _stage(fid, "extract") as s:
            pages, docmap, raw_notes = ex.extract(pdf, config.PDFTOTEXT)
            page_text = {p.no: p.text for p in pages}
            text_fp = text_fingerprint([p.raw for p in pages])
            s.info(f"{docmap.pages} pages, {docmap.text_pages} with a text layer")
            if docmap.text_pages < docmap.pages * 0.5:
                warnings.append("Most pages have no text layer (scanned PDF); only the pages the model reads visually are covered.")
        hit = store.find_cached(pdf_sha, text_fp, exclude=fid)
        if hit:
            _restore(fid, meta, hit[0], hit[1], pdf_sha, text_fp, docmap)
            return
        with _stage(fid, "segment") as s:
            stmt_pages = {k: v for k, v in docmap.statements.items() if v}
            s.info(f"statements on pages {stmt_pages}; auditor's report pages {docmap.auditor or 'not found'}; {len(raw_notes)} notes from page {docmap.notes_start}")
            store.save_raw(fid, {"docmap": docmap.__dict__, "notes": raw_notes})
            if not stmt_pages:
                warnings.append("No primary statement pages were recognised by title; the whole document before the notes was used.")
                first = docmap.notes_start or docmap.pages + 1
                stmt_pages = {"other": [p.no for p in pages if 1 < p.no < first and len(p.text) > 300][:8]}
            if not raw_notes:
                warnings.append("No numbered notes were recognised; the notes explorer will be empty.")

        with _stage(fid, "statements") as s:
            statements, unit, scale, currency = [], None, None, None
            if llm.enabled:
                try:
                    data = llm_statements(llm, pdf, stmt_pages, page_text, d)
                    statements = coerce_statements(data)
                    unit, scale, currency = data.get("unit"), data.get("scale"), data.get("currency")
                    s.info(f"model transcribed {len(statements)} statements, {sum(len(x['rows']) for x in statements)} lines")
                except Exception as e:
                    warnings.append(f"Statement transcription by the analysis service failed ({str(e)[:140]}); the statements were parsed directly from the text instead.")
                    log.exception("statement transcription failed")
            if not statements:
                hs = []
                for sid, ps in stmt_pages.items():
                    st = heuristic_statement(sid, [page_text[p] for p in ps])
                    if st:
                        st["pdfPages"] = ps
                        hs.append(st)
                statements = coerce_statements({"statements": hs})
                s.info(f"heuristic parse: {len(statements)} statements, {sum(len(x['rows']) for x in statements)} lines")
            if not statements:
                raise RuntimeError("could not parse any primary statement from the document")
            stmt_text = "\n".join(page_text[p] for ps in stmt_pages.values() for p in ps)
            if not unit:
                unit, scale, currency = detect_unit(stmt_text[:4000] + "\n" + "\n".join(page_text.get(p, "")[:600] for p in list(page_text)[:3]))

        with _stage(fid, "company") as s:
            company = None
            if llm.enabled:
                try:
                    sel = sorted(set([1, 2] + docmap.auditor[:12] + [min(ps) for ps in stmt_pages.values()]))
                    sel = [p for p in sel if 1 <= p <= docmap.pages]
                    sub = subset_pdf(pdf, sel, d / "company.pdf")
                    text = "\n\n".join(f"=== PDF page {p} ===\n{page_text.get(p, '')}" for p in sel)
                    company = company_facts(llm, base64.standard_b64encode(sub.read_bytes()).decode("ascii"), text)
                    s.info(f"{company.get('name')} · {company.get('fy')} · auditor {company['auditor'].get('firm')} ({company['auditor'].get('opinion')})")
                except Exception as e:
                    warnings.append(f"Model extraction of company and auditor facts failed ({str(e)[:140]}).")
                    log.exception("company facts failed")
            if not company:
                name = meta.get("name") or ex.guess_company_name(pages, raw_notes, meta.get("uploadName") or fid)
                yr = re.search(r"20\d\d", stmt_text[:3000] or "")
                company = {"name": name, "shortName": meta.get("name") or ex.clean_company_name(name.split("(")[0])[:40] or name[:40], "ticker": meta.get("ticker"), "exchange": None,
                           "sector": meta.get("sector") or "—", "hq": None, "fy": f"FY{yr.group(0)}" if yr else "FY", "periodEnd": yr.group(0) if yr else "",
                           "years": statements[0]["cols"][:2], "unit": unit, "scale": scale, "currency": currency, "approvedBy": None, "approvedOn": None, "signatories": [],
                           "auditor": {"firm": None, "partner": None, "license": None, "reportDate": None, "opinion": "Unknown", "opinionText": None, "materiality": None,
                                       "emphasisOfMatter": None, "otherMatter": None, "goingConcern": None, "kams": []}}
                s.info(f"extraction-only: company name '{name}' from the upload form, note 1 or the page headers")
            company["unit"] = company.get("unit") or unit
            company["scale"] = company.get("scale") or scale or 1
            if meta.get("name"):
                company["shortName"] = meta["name"]
            if meta.get("ticker"):
                company["ticker"] = meta["ticker"]
            if meta.get("sector"):
                company["sector"] = meta["sector"]

        with _stage(fid, "notes") as s:
            curated = {}
            if llm.enabled and raw_notes:
                curated = curate_notes(llm, raw_notes, company["unit"], company["name"], progress=s.info)
                s.info(f"{len(curated)} of {len(raw_notes)} notes curated")
            else:
                s.info("extraction-only: notes indexed with their source text (no summaries or flags)")

        with _stage(fid, "analysis") as s:
            kr = None
            if llm.enabled:
                try:
                    kr = key_rows(llm, statements)
                except Exception as e:
                    warnings.append(f"Model key-row mapping failed ({str(e)[:120]}); label matching used.")
            if not kr:
                kr = heuristic_keyrows(statements)
            derived = derive(statements, kr, company["scale"])
            s.info(f"{len(derived['kpis'])} KPIs, {len(derived['ratios'])} ratios")
            brief, lens, charts = "", [], derived["charts"]
            if llm.enabled:
                try:
                    an = llm_analysis(llm, company, statements, derived, curated, raw_notes)
                    brief, lens = an.get("brief", ""), an.get("lens", [])
                    if an.get("segments"):
                        charts["segments"] = an["segments"]
                    if an.get("geography"):
                        charts["geography"] = an["geography"]
                    s.info(f"analyst brief and {len(lens)} lens findings written")
                except Exception as e:
                    warnings.append(f"Analyst brief and investor lens failed ({str(e)[:140]}).")
                    log.exception("analysis failed")
            if not brief:
                brief = (f"<strong>{company['shortName']}</strong> {company['fy']}: the primary statements and {len(raw_notes)} notes were extracted and cross-referenced. "
                         "The analysis layer (note summaries, reviewer flags, the analyst brief and the investor lens) did not run for this filing"
                         + ("; the analysis service rejected the server's API key" if config.llm_configured() else "; no analysis service is configured on this server")
                         + ". Run the filing again once it is available.")

        with _stage(fid, "build") as s:
            years = company.get("years") or kr.get("years") or ["current", "prior"]
            bundle = dict(company)
            bundle.update({
                "id": fid, "pdf": f"filings/{fid}.pdf", "pdfPages": docmap.pages, "pageOffset": docmap.printed_offset or 0,
                "statementsStartPage": min([p for ps in stmt_pages.values() for p in ps]), "notesStartPage": docmap.notes_start,
                "unitShort": (company["unit"] or "").replace("million", "m").replace("thousand", "k"),
                "kpis": derived["kpis"], "ratios": derived["ratios"], "charts": charts, "brief": brief, "lens": lens,
                "statements": statements, "years": years, "keyRows": kr, "mode": mode, "createdAt": meta.get("createdAt", time.time()),
                "sha256": pdf_sha, "textFingerprint": text_fp,
                "llm": {"calls": llm.calls, "inputTokens": llm.input_tokens, "outputTokens": llm.output_tokens, "model": config.MODEL if llm.enabled else None},
            })
            bundle = assemble(bundle, raw_notes, curated, warnings)
            store.save_bundle(fid, bundle)
            s.info(f"{bundle['stats']['links']} cross-references from {bundle['stats']['linesWithNotes']} statement lines to {bundle['stats']['notesReferenced']} notes")
        store.update_status(fid, state="ready", finishedAt=time.time(), warnings=warnings)
    except Exception as e:
        log.error("pipeline failed for %s: %s\n%s", fid, e, traceback.format_exc())
        store.update_status(fid, state="failed", finishedAt=time.time(), error=f"{type(e).__name__}: {e}", warnings=warnings)
