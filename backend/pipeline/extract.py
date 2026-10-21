"""PDF → pages → document map → notes.

Works for any IFRS-style annual financial statements PDF:

1. pdftotext -layout per page (tables keep their column alignment).
2. Page furniture (repeated headers/footers, page numbers) is detected statistically:
   a short line that repeats on a third of the pages is furniture.
3. The document map finds the auditor's report, each primary statement and the start of
   the notes by their titles.
4. Notes are split on numbered headings. Several numbering styles are recognised
   ("24. Revenue", "16 - Borrowings", "Note 7 Inventories", "7 INVENTORIES") and note
   numbers must increase by exactly one, which separates real headings from footnotes and
   "continued" headers.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RIYAL = re.compile("‫?\\s*﷼\\s*‬?")

STATEMENT_TITLES = {
    "balance": re.compile(r"statement\s+of\s+financial\s+position|balance\s+sheet", re.I),
    "income": re.compile(r"statement\s+of\s+(profit\s+or\s+loss|profit\s+and\s+loss|income|operations|comprehensive\s+income)", re.I),
    "equity": re.compile(r"statement\s+of\s+changes\s+in\s+(shareholders'?\s*|owners'?\s*|stockholders'?\s*)?equity", re.I),
    "cashflow": re.compile(r"statement\s+of\s+cash\s*flows?", re.I),
}
NOTES_TITLE = re.compile(r"notes\s+to\s+(the\s+)?(consolidated\s+|interim\s+|condensed\s+)*financial\s+statements?", re.I)
AUDITOR_TITLE = re.compile(r"independent\s+auditor['’]?s?['’]?\s+(review\s+)?report", re.I)
CONTENTS_TITLE = re.compile(r"^\s*(contents|index|table\s+of\s+contents)\b", re.I | re.M)
NAV_STRIP = re.compile(r"\d{1,2}\.\s+[A-Z]{3,}.*\d{1,2}\.\s+[A-Z]{3,}")   # "1. OVERVIEW   2. RESULTS" side-bar strips

HEADING_PATTERNS = [
    re.compile(r"^\s*(?:note\s+)?(\d{1,2})\s*[.\-–:]\s*([A-Za-z].{2,100}?)\s*$", re.I),  # "24. Revenue" / "16 - Borrowings" / "10.Trade" / "Note 7: Inventories"
    re.compile(r"^\s*(?:note\s+)?(\d{1,2})\s{2,}([A-Z][^\n]{2,100}?)\s*$", re.I),      # "7    INVENTORIES"
    re.compile(r"^\s*(?:note\s+)?(\d{1,2})\s+([A-Z][A-Za-z][^\n]{2,100}?)\s*$"),       # "7 Inventories"
]
SUBNOTE = re.compile(r"^\s*(\([a-z]\)|\([ivx]+\)|\d{1,2}[-.]\d{1,2}|[A-H][-.]|[a-h][-.)])\s+(.{3,90})$")
XREF = re.compile(r"\bNotes?\s+(\d{1,2}(?:\s*\([a-z0-9]+\))*(?:\s*(?:,|and|&)\s*\d{1,2}(?:\s*\([a-z0-9]+\))*)*)", re.I)


@dataclass
class Page:
    no: int
    raw: str
    lines: list[str] = field(default_factory=list)   # cleaned lines

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class DocMap:
    pages: int
    text_pages: int
    auditor: list[int]
    statements: dict[str, list[int]]
    notes_start: int | None
    first_note_page: int | None
    printed_offset: int | None          # pdf page − printed page
    furniture: list[str]


def pdf_pages(pdf: Path, pdftotext: str = "pdftotext") -> list[str]:
    out = subprocess.run([pdftotext, "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line)).strip().lower()


def detect_furniture(pages: list[str]) -> set[str]:
    """Lines (digits normalised) that repeat on ≥ 30% of pages and sit near the top/bottom."""
    n = max(len(pages), 1)
    counter: Counter[str] = Counter()
    for p in pages:
        ls = [l for l in p.splitlines() if l.strip()]
        edge = ls[:4] + ls[-4:]
        for l in set(_norm(x) for x in edge if len(x.strip()) < 220):
            counter[l] += 1
    return {l for l, c in counter.items() if c >= max(3, n * 0.3)}


def clean_pages(raw_pages: list[str], pdftotext_style: bool = True) -> list[Page]:
    furniture = detect_furniture(raw_pages)
    pages = []
    for i, raw in enumerate(raw_pages, start=1):
        lines = []
        for line in raw.splitlines():
            s = RIYAL.sub("SAR ", line).rstrip()
            core = s.strip()
            if not core:
                lines.append("")
                continue
            if _norm(core) in furniture or NAV_STRIP.search(core):
                continue
            if re.fullmatch(r"[-–]?\s*\d{1,3}\s*[-–]?", core):      # bare page number
                continue
            lines.append(re.sub(r"[ ]{3,}", "   ", s))
        # collapse runs of blank lines
        out, blank = [], 0
        for l in lines:
            blank = blank + 1 if not l else 0
            if blank <= 1:
                out.append(l)
        pages.append(Page(no=i, raw=raw, lines=out))
    return pages


def _head(page: Page, n: int = 10) -> str:
    return "\n".join([l for l in page.lines if l.strip()][:n])


def build_docmap(pages: list[Page]) -> DocMap:
    auditor, statements = [], {k: [] for k in STATEMENT_TITLES}
    notes_start = None
    contents_pages = set()
    for p in pages:
        head = _head(p)
        hits = sum(1 for rx in STATEMENT_TITLES.values() if rx.search(head))
        if CONTENTS_TITLE.search(head) or hits >= 3:
            contents_pages.add(p.no)
            continue
        if AUDITOR_TITLE.search(head):
            auditor.append(p.no)
        if NOTES_TITLE.search(head) and notes_start is None:
            # the notes section starts at the first page that carries the heading of note 1
            if any(_match_heading(l, 1) for l in p.lines[:60]):
                notes_start = p.no
    for p in pages:
        if notes_start and p.no >= notes_start:
            break
        if p.no in contents_pages:
            continue
        head = _head(p, 8)
        if NOTES_TITLE.search(head):
            continue
        for key, rx in STATEMENT_TITLES.items():
            if rx.search(head):
                statements[key].append(p.no)
    first_stmt = min([p for ps in statements.values() for p in ps], default=None)
    if first_stmt:
        # a scanned auditor's report (no text layer) sits between the contents and the first statement
        scanned = [p.no for p in pages if 1 < p.no < first_stmt and p.no not in contents_pages and len(p.text.strip()) < 200]
        auditor = sorted(set(auditor) | set(scanned))[:14]
    first_note_page = notes_start
    # printed-page offset: printed page numbers sit at the end of the last lines of a page
    offset = None
    votes: Counter[int] = Counter()
    for p in pages:
        tail = [l for l in p.raw.splitlines() if l.strip()][-3:]
        for l in tail:
            m = re.search(r"(?:^|\s)[-–]?\s*(\d{1,3})\s*[-–]?\s*$", l)
            if m:
                n = int(m.group(1))
                if 1 <= n <= p.no and 0 <= p.no - n <= 40:
                    votes[p.no - n] += 1
    if votes and votes.most_common(1)[0][1] >= 3:
        offset = votes.most_common(1)[0][0]
    text_pages = sum(1 for p in pages if len(p.text.strip()) > 200)
    return DocMap(pages=len(pages), text_pages=text_pages, auditor=auditor, statements=statements,
                  notes_start=notes_start, first_note_page=first_note_page, printed_offset=offset,
                  furniture=sorted(detect_furniture([p.raw for p in pages]))[:12])


def _match_heading(line: str, expected: int):
    for rx in HEADING_PATTERNS:
        m = rx.match(line)
        if not m:
            continue
        n, title = int(m.group(1)), m.group(2).strip()
        if n != expected:
            continue
        if re.search(r"\b(continued|cont'd|\(cont\.?\))", title, re.I):
            return None
        if len(title) > 100 or re.search(r"\d{3,}", title):      # table rows, not headings
            continue
        if re.search(r"\s\d{1,2}\.\s+[A-Z]", title):              # several numbered items on one line: a nav strip
            continue
        if title.endswith(".") and len(title) > 60:                # a sentence, e.g. a footnote
            continue
        words = title.split()
        if len(words) > 14:
            continue
        return n, re.sub(r"[.:\-–\s]+$", "", title)
    return None


def split_notes(pages: list[Page], start_page: int | None) -> list[dict]:
    """Return [{n, title, pdfPage, text, subnotes, refs}] in order."""
    if not start_page:
        return []
    notes, current, expected = [], None, 1
    for p in pages:
        if p.no < start_page:
            continue
        for line in p.lines:
            h = _match_heading(line, expected)
            if h:
                current = {"n": str(h[0]), "title": h[1], "pdfPage": p.no, "lines": []}
                notes.append(current)
                expected += 1
                continue
            if current is not None:
                current["lines"].append(line)
    out = []
    for nt in notes:
        text = "\n".join(nt["lines"]).strip("\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        subs = []
        for ln in text.splitlines():
            m = SUBNOTE.match(ln)
            if m and len(ln.strip()) < 100 and not re.search(r"\d{3,}", m.group(2)):
                subs.append({"id": m.group(1).rstrip("-.)"), "title": m.group(2).strip()})
        refs = set()
        for m in XREF.finditer(text):
            for num in re.findall(r"\d{1,2}", m.group(1)):
                if num != nt["n"] and 1 <= int(num) <= len(notes):
                    refs.add(num)
        out.append({"n": nt["n"], "title": nt["title"], "pdfPage": nt["pdfPage"], "text": text,
                    "subnotes": subs[:40], "refs": sorted(refs, key=int), "chars": len(text)})
    return out


def title_case(t: str) -> str:
    if t.isupper():
        small = {"and", "of", "the", "to", "for", "in", "on", "at", "or", "net"}
        words = t.lower().split()
        return " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(words))
    return t


def extract(pdf: Path, pdftotext: str = "pdftotext") -> tuple[list[Page], DocMap, list[dict]]:
    raw = pdf_pages(pdf, pdftotext)
    pages = clean_pages(raw)
    docmap = build_docmap(pages)
    notes = split_notes(pages, docmap.notes_start)
    for n in notes:
        n["title"] = title_case(n["title"])
        n["printedPage"] = n["pdfPage"] - docmap.printed_offset if docmap.printed_offset is not None else n["pdfPage"]
    return pages, docmap, notes
