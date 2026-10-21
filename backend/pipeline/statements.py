"""Primary statements: heuristic transcription from the layout text, and the LLM
transcription from the statement pages (text + the pages themselves as a PDF document).

Row schema (shared with the frontend):
  l   label               n   note reference as printed ("24", "5,6", "35(a)", "16.1")
  v   values per column   i   indent (0-2)      b bold     t total (rule above)
  g   grand total         h   header row (no values)       s section label
  dec decimals for per-share lines
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

NUM = re.compile(r"^\(?-?\d{1,3}(,\d{3})*(\.\d+)?\)?$|^\(?-?\d+(\.\d+)?\)?$")
DASH = re.compile(r"^[–—\-]+$")
NOTE = re.compile(r"^(\d{1,2}([.(\-–][A-Za-z0-9)]{1,6})?)(\s*[,&]\s*\d{1,2}([.(\-–][A-Za-z0-9)]{1,6})?)*$")
YEAR = re.compile(r"\b(20\d\d)\b")
TITLES = {
    "balance": ("Statement of financial position", "Financial position"),
    "income": ("Statement of profit or loss and other comprehensive income", "Profit or loss"),
    "oci": ("Statement of comprehensive income", "Comprehensive income"),
    "equity": ("Statement of changes in equity", "Changes in equity"),
    "cashflow": ("Statement of cash flows", "Cash flows"),
}


def parse_num(tok: str):
    tok = tok.strip()
    if DASH.match(tok):
        return None
    neg = tok.startswith("(") and tok.endswith(")")
    core = tok.strip("()").replace(",", "")
    try:
        v = float(core)
    except ValueError:
        return None
    if neg or core.startswith("-"):
        v = -abs(v)
    return int(v) if v == int(v) and "." not in core else v


def heuristic_statement(sid: str, pages_text: list[str], title_hint: str | None = None) -> dict | None:
    """Parse one statement from the layout text of its pages."""
    lines = []
    for t in pages_text:
        lines.extend(t.splitlines())
    # columns: first line with ≥2 year tokens
    cols = None
    for ln in lines[:60]:
        ys = YEAR.findall(ln)
        if len(ys) >= 2:
            cols = ys[:4]
            break
    # a supplementary currency or a restated opening column repeats the year labels: keep the first set
    if cols:
        seen = []
        for c in cols:
            if c in seen:
                break
            seen.append(c)
        cols = seen
    rows, ncounts = [], []
    parsed = []
    value_like = lambda t: bool(DASH.match(t) or NUM.match(t))
    strong_value = lambda t: bool(DASH.match(t) or (NUM.match(t) and (re.search(r"[,.()]", t) or len(t.strip("()-")) >= 4)))
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        cells = []
        for c in re.split(r"\s{2,}", s):
            c = c.strip()
            if not c:
                continue
            # tightly packed numeric runs ("75,000 26,981 (2,236)") → separate tokens
            if re.fullmatch(r"(\s*(\(?-?[\d,]+(\.\d+)?\)?|[–—-]))+\s*", c) and " " in c:
                cells.extend(c.split())
            else:
                cells.append(c)
        nums, note = [], None
        tail = list(cells)
        while tail and value_like(tail[-1]):
            nums.insert(0, tail.pop())
        # a note reference set off by wide spacing is its own cell: "Revenue   24   1,637,299   1,653,281"
        if tail and NOTE.match(tail[-1]) and nums and not YEAR.match(tail[-1]):
            note = tail.pop()
        label = " ".join(tail).strip()
        if not label and not nums:
            continue
        if nums and all(YEAR.fullmatch(t.strip("()")) for t in nums):   # column-heading line
            continue
        parsed.append([label, note, nums, s])
        if nums:
            ncounts.append(len([t for t in nums if strong_value(t)]))
    if not parsed:
        return None
    if ncounts:
        ncol = max(set(ncounts), key=ncounts.count)
    else:
        ncol = len(cols) if cols else 2
    if cols and len(cols) < ncol and sid != "equity":
        ncol = len(cols)                      # drop supplementary columns (USD convenience, restated opening) beyond the year labels
    if cols and len(cols) > ncol:
        cols = cols[:ncol]
    cols = (cols or [f"col {i + 1}" for i in range(ncol)])[:ncol]
    for row in parsed:
        label, note, nums, s = row
        # a leading bare note number ("12 72 8,955", "16.1 219,040 299,229") when more tokens than columns remain
        if note is None and len(nums) > ncol and NOTE.match(nums[0]) and not YEAR.match(nums[0]) and not re.search(r"[,()]", nums[0]):
            note = nums.pop(0)
            row[1] = note
        row[2] = nums[:ncol] if len(nums) >= ncol else nums
    for label, note, nums, s in parsed:
        if YEAR.search(label) and not nums:
            continue
        if not nums:
            if len(label) > 90 or re.search(r"[.;]$", label):
                continue
            kind = "s" if label.isupper() and len(label) < 60 else "h"
            rows.append({"l": label.rstrip(":"), "n": note, kind: True})
            continue
        vals = [parse_num(x) for x in nums]
        vals = vals[:ncol] if len(vals) >= ncol else [None] * (ncol - len(vals)) + vals
        low = label.lower()
        total = low.startswith(("total", "net ", "gross profit", "operating", "profit", "loss", "income before", "net cash", "cash and cash equivalents at")) or label == ""
        rows.append({"l": label, "n": note, "v": vals, "i": 0 if total else 1, "t": bool(total and label),
                     "b": bool(total), "g": low.startswith(("total assets", "total equity", "total liabilities and", "net cash", "cash and cash equivalents at the end", "net income", "net loss", "profit for the year"))})
    if not any("v" in r for r in rows):
        return None
    # drop page furniture that survived as header rows: statement titles, unit lines, the "Note"
    # column heading, the "accompanying notes" footer and the signature block after the last total
    noise = re.compile(r"^(consolidated\s+)?(statement|balance sheet)|^\(?in\s+.*(riyals?|thousand|million)|^note\b|accompanying notes|^for the year ended|^as at\b|^year ended\b|^at \w+ \d|^(sar|usd|sr)\b|\|", re.I)
    rows = [r for r in rows if not noise.search(r["l"]) and not ("v" in r and len(r["l"]) > 60 and r["l"].isupper())]
    last_val = max(i for i, r in enumerate(rows) if "v" in r)
    rows = rows[:last_val + 1]
    title, short = TITLES.get(sid, (title_hint or sid, sid))
    return {"id": sid, "title": title_hint or title, "short": short, "basis": "", "cols": cols, "rows": rows,
            "wide": sid == "equity" or ncol > 4, "source": "heuristic"}


def subset_pdf(pdf: Path, pages: list[int], out: Path) -> Path:
    """Extract the given 1-based pages into a small PDF (poppler pdfseparate/pdfunite)."""
    pages = sorted(set(pages))
    with tempfile.TemporaryDirectory() as td:
        parts = []
        for p in pages:
            part = Path(td) / f"p{p}.pdf"
            subprocess.run(["pdfseparate", "-f", str(p), "-l", str(p), str(pdf), str(part)], check=True, capture_output=True)
            parts.append(str(part))
        if len(parts) == 1:
            out.write_bytes(Path(parts[0]).read_bytes())
        else:
            subprocess.run(["pdfunite", *parts, str(out)], check=True, capture_output=True)
    return out


ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "l": {"type": "string", "description": "line item label exactly as printed; empty string for an unlabelled subtotal line"},
        "n": {"type": ["string", "null"], "description": "note reference exactly as printed next to the line, e.g. '24', '5,6', '35(a)', '16.1', '5-E,5-F'; null if none"},
        "v": {"type": "array", "items": {"type": ["number", "null"]}, "description": "one value per column, numbers only; amounts in parentheses are negative; dashes/blank are null"},
        "i": {"type": "integer", "description": "indent level 0-2 as printed"},
        "b": {"type": "boolean", "description": "printed in bold"},
        "t": {"type": "boolean", "description": "subtotal/total line (rule above it)"},
        "g": {"type": "boolean", "description": "grand total (total assets, total equity, net income, closing cash...)"},
        "h": {"type": "boolean", "description": "header line without values (e.g. 'Current assets', 'Net income attributable to')"},
        "s": {"type": "boolean", "description": "section label without values (e.g. 'Assets', 'Equity and liabilities')"},
        "dec": {"type": "integer", "description": "decimal places for per-share lines, else 0"},
    },
    "required": ["l", "n", "v", "i", "b", "t", "g", "h", "s", "dec"],
    "additionalProperties": False,
}
STATEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "enum": ["balance", "income", "oci", "equity", "cashflow", "other"]},
        "title": {"type": "string", "description": "statement title as printed"},
        "short": {"type": "string", "description": "2-3 word label for a tab"},
        "basis": {"type": "string", "description": "e.g. 'Year ended December 31' or 'As at 31 December'"},
        "cols": {"type": "array", "items": {"type": "string"}, "description": "column headings in order, e.g. ['2024','2023'] or equity components"},
        "colNotes": {"type": "array", "items": {"type": ["string", "null"]}, "description": "note reference printed in a column heading (e.g. '33' for 'Restated – Note 33'), one entry per column"},
        "wide": {"type": "boolean", "description": "true for the changes-in-equity matrix or statements with more than 4 value columns"},
        "pdfPages": {"type": "array", "items": {"type": "integer"}, "description": "PDF page numbers the statement was read from"},
        "rows": {"type": "array", "items": ROW_SCHEMA},
    },
    "required": ["id", "title", "short", "basis", "cols", "colNotes", "wide", "pdfPages", "rows"],
    "additionalProperties": False,
}
STATEMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "unit": {"type": "string", "description": "presentation unit as stated, e.g. 'SAR million', 'SAR thousand', 'USD'"},
        "scale": {"type": "number", "description": "multiplier to convert a printed value to absolute currency units: 1000000 for millions, 1000 for thousands, 1 otherwise"},
        "currency": {"type": "string"},
        "statements": {"type": "array", "items": STATEMENT_SCHEMA},
    },
    "required": ["unit", "scale", "currency", "statements"],
    "additionalProperties": False,
}

STATEMENTS_SYSTEM = """You transcribe the primary financial statements from an audited annual report into structured JSON for a financial-statement explorer.

Rules:
- Transcribe EVERY line exactly as printed, in order, including headers, section labels, subtotals and unlabelled total lines. Do not summarise, merge or reorder lines.
- Copy the note reference printed on each line verbatim into `n` (e.g. "24", "5,6", "35(a)", "16.1", "5-E,5-F"). A note printed in a column heading (e.g. "2023 Restated – Note 33") goes into `colNotes`.
- Values: numbers only. Parentheses mean negative. Dashes, "nil" or blanks are null. Keep one value per column in `v`, matching `cols` in order. If the filing prints a supplementary currency (e.g. USD convenience columns) next to the main columns, include ONLY the main presentation-currency columns.
- Use the presentation unit stated on the statements ("All amounts in millions of Saudi Riyals", "In Saudi Riyals Thousand") for `unit`/`scale`.
- Statement ids: balance (financial position / balance sheet), income (profit or loss, or combined P&L and OCI), oci (a separate statement of comprehensive income), equity (changes in equity — treat the equity components as the columns and each movement as a row; `wide` = true), cashflow. Use "other" only for anything else.
- The text extraction of each page is provided for exact numbers; the PDF pages are attached to resolve layout, bold lines and column alignment.
"""


def llm_statements(llm, pdf: Path, pages_by_stmt: dict[str, list[int]], pages_text: dict[int, str], workdir: Path) -> dict:
    page_nos = sorted({p for ps in pages_by_stmt.values() for p in ps})
    sub = subset_pdf(pdf, page_nos, workdir / "statements.pdf")
    text_parts = [f"=== PDF page {p} ===\n{pages_text.get(p, '')}" for p in page_nos]
    content = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": __import__("base64").standard_b64encode(sub.read_bytes()).decode("ascii")}},
        {"type": "text", "text": "Text extraction of the same pages (layout preserved):\n\n" + "\n\n".join(text_parts)},
        {"type": "text", "text": f"Statement pages detected: {pages_by_stmt}. Transcribe all primary statements found on these pages."},
    ]
    return llm.json(system=STATEMENTS_SYSTEM, content=content, schema=STATEMENTS_SCHEMA, effort="high", max_tokens=48000, label="statements")


def coerce_statements(data: dict) -> list[dict]:
    """Validate/normalise LLM or heuristic statement objects into the frontend contract."""
    out, seen = [], set()
    for st in data.get("statements", []):
        cols = [str(c) for c in st.get("cols") or []]
        if not cols:
            continue
        sid = st.get("id") or "other"
        base = sid
        k = 2
        while sid in seen:
            sid = f"{base}{k}"; k += 1
        seen.add(sid)
        rows = []
        for r in st.get("rows", []):
            row = {"l": str(r.get("l") or "").strip()}
            n = r.get("n")
            if n and str(n).strip() and str(n).strip().lower() not in ("null", "none", "-"):
                row["n"] = str(n).strip()
            if r.get("s"):
                row["s"] = True
            elif r.get("h") or not r.get("v"):
                row["h"] = True
            else:
                v = list(r.get("v") or [])
                v = [x if isinstance(x, (int, float)) else None for x in v]
                v = (v + [None] * len(cols))[:len(cols)]
                row["v"] = v
                if r.get("i"):
                    row["i"] = int(r["i"])
                for f in ("b", "t", "g"):
                    if r.get(f):
                        row[f] = True
                if r.get("dec"):
                    row["dec"] = int(r["dec"])
            rows.append(row)
        if not rows:
            continue
        colnotes = st.get("colNotes") or []
        colnotes = [(c if c else None) for c in colnotes][:len(cols)] + [None] * max(0, len(cols) - len(colnotes))
        out.append({"id": sid, "title": st.get("title") or sid, "short": st.get("short") or sid, "basis": st.get("basis") or "",
                    "cols": cols, "colNotes": colnotes if any(colnotes) else None, "wide": bool(st.get("wide")) or len(cols) > 4,
                    "pdfPages": st.get("pdfPages") or [], "rows": rows, "source": st.get("source", "llm")})
    order = {"income": 0, "oci": 1, "balance": 2, "equity": 3, "cashflow": 4}
    out.sort(key=lambda s: order.get(s["id"], 9))
    return out
