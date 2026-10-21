#!/usr/bin/env python3
"""Split an IFRS annual-report PDF into its numbered notes.

Usage:
    python3 extract_notes.py <filing.pdf> --id aramco --page-offset 3 \
        --style aramco --out out/aramco.notes.raw.json

What it does
------------
1. Runs `pdftotext -layout` so tables keep their column alignment.
2. Strips running headers / footers / page furniture.
3. Finds the note headings ("24. Revenue", "16 - Borrowings", ...) requiring
   that note numbers increase by exactly one, which separates real headings
   from footnotes ("1. Additions include ...") and from "continued" headings.
4. Records, for every note: number, title, first PDF page, the page printed in
   the statements, the cleaned text, the sub-note headings found inside it and
   the other notes it refers to ("Note 29(a)", "Notes 12 and 23").

The output is a plain JSON file that `build_data.py` merges with the curated
summaries into the dashboard's data bundle.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RIYAL = re.compile("‫?\\s*﷼\\s*‬?")      # the ﷼ glyph pdftotext emits with bidi marks

FURNITURE = {
    "aramco": [
        r"^SAUDI ARAMCO",            # "SAUDI ARAMCO | CONSOLIDATED FINANCIAL STATEMENTS 2024  26"
        r"^\d{1,3}\s+SAUDI ARAMCO",  # "202   SAUDI ARAMCO | ANNUAL REPORT 2024 ..."
        r"^FINANCIAL$", r"^\| ANNUAL$", r"^STATEMENTS$", r"^REPORT ?2024$",
        r"^2024 \d{3,5}$",           # merged page numbers from the annual-report side bar
        r"ARAMCO OVERVIEW", r"ORGANIZATIONAL", r"STRUCTURE AND", r"GOVERNANCE",
        r"^\d\. [A-Z][A-Z ,&/-]+$",  # side-bar section labels: "7. CONSOLIDATED"
        r"^Notes to the consolidated financial statements( continued)?$",
        r"^All amounts in millions of Saudi Riyals unless otherwise stated$",
        r"^CORPORATE$", r"^AND LEGAL$", r"^RESULTS AND$", r"^FINANCIAL$",
    ],
    "ceramic": [
        r"^SAUDI CERAMIC COMPANY$", r"^Saudi Ceramic Company$",
        r"^\(Saudi Joint Stock Company\)$",
        r"^NOTES TO (THE )?CONSOLIDATED FINANCIAL STATEMENTS?( \(CONTINUED\))?$",
        r"^Notes to consolidated financial statements( \(continued\))?$",
        r"^FOR THE YEAR ENDED (31 )?DECEMBER( 31)?,? 2024$",
        r"^For the year ended (31 )?December( 31)?,? 2024$",
        r"^\(In Saudi Riyals Thousand( unless stated otherwise)?\)$",
        r"^\d{1,2}$",                # bare page numbers
        r"^-\d{1,2}-$",
    ],
}

HEADING = {
    # "24. Revenue"  — title must contain a lowercase letter (side-bar labels are all caps)
    "aramco": re.compile(r"^\s*(\d{1,2})\.\s+([A-Z][^\n]{2,95})\s*$"),
    # "16 - Borrowings", "1- ORGANIZATION ACTIVITIES", "10.Trade and other receivables"
    "ceramic": re.compile(r"^\s*(\d{1,2})\s*[-–.]\s*([A-Za-z][^\n]{2,95})\s*$"),
}

SUBNOTE = re.compile(r"^\s*(\([a-z]\)|\([ivx]+\)|\d{1,2}[-.]\d|[A-H]-|[A-H]\.)\s+(.{3,90})$")
XREF = re.compile(r"\bNotes?\s+(\d{1,2}(?:\s*\([a-z0-9]+\))*(?:\s*(?:,|and)\s*\d{1,2}(?:\s*\([a-z0-9]+\))*)*)")


def pdf_pages(pdf: Path) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                         capture_output=True, text=True).stdout
    return txt.split("\f")


def clean_line(line: str, style: str) -> str | None:
    s = RIYAL.sub("SAR ", line).rstrip()
    core = s.strip()
    if not core:
        return ""
    for pat in FURNITURE[style]:
        if re.search(pat, core):
            return None
    return re.sub(r"[ ]{3,}", "   ", s)       # keep table columns readable, drop huge gaps


def is_heading(line: str, style: str, expected: int):
    m = HEADING[style].match(line)
    if not m:
        return None
    n, title = int(m.group(1)), m.group(2).strip()
    if n != expected:
        return None
    if re.search(r"continued|\(Continued\)", title, re.I):
        return None
    if style == "aramco" and not re.search(r"[a-z]", title):
        return None
    if len(title) > 95 or title.endswith("."):
        if not (style == "ceramic" and title.endswith(".")):
            return None
    return n, title.rstrip(".").strip()


def extract(pdf: Path, style: str, page_offset: int, first_page: int):
    pages = pdf_pages(pdf)
    notes, current = [], None
    expected = 1
    for pno, page in enumerate(pages, start=1):
        if pno < first_page:
            continue
        for raw in page.splitlines():
            cl = clean_line(raw, style)
            if cl is None:
                continue
            h = is_heading(cl, style, expected)
            if h:
                current = {"n": str(h[0]), "title": h[1], "pdfPage": pno,
                           "printedPage": pno - page_offset, "lines": []}
                notes.append(current)
                expected += 1
                continue
            if current is not None:
                current["lines"].append(cl)
    out = []
    for nt in notes:
        text = "\n".join(nt["lines"]).strip("\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        subs = []
        for ln in text.splitlines():
            m = SUBNOTE.match(ln)
            if m and len(ln.strip()) < 100 and not re.search(r"\d{2,}", m.group(2)):
                subs.append({"id": m.group(1).rstrip("-."), "title": m.group(2).strip()})
        refs = set()
        for m in XREF.finditer(text):
            for num in re.findall(r"\d{1,2}", m.group(1)):
                if num != nt["n"]:
                    refs.add(num)
        out.append({"n": nt["n"], "title": nt["title"], "pdfPage": nt["pdfPage"],
                    "printedPage": nt["printedPage"], "text": text,
                    "subnotes": subs[:40], "refs": sorted(refs, key=int), "chars": len(text)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--style", choices=list(HEADING), required=True)
    ap.add_argument("--page-offset", type=int, default=0,
                    help="PDF page number minus the page number printed in the statements")
    ap.add_argument("--first-page", type=int, default=1, help="PDF page where the notes start")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    notes = extract(a.pdf, a.style, a.page_offset, a.first_page)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"id": a.id, "source": a.pdf.name, "notes": notes},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.id}: {len(notes)} notes → {a.out}", file=sys.stderr)
    for n in notes:
        print(f"  {n['n']:>2}  p{n['pdfPage']:<3} {n['chars']:>6} chars  refs={','.join(n['refs'])}  {n['title']}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
