#!/usr/bin/env python3
"""Assemble the dashboard data bundle for each filing.

    python3 pipeline/build_data.py            # builds data/<id>.js for every curated filing

Inputs per filing <id>:
  pipeline/curated/<id>.company.json   metadata, auditor, KPIs, primary statements (with note refs),
                                       chart series, investor-lens findings, analyst brief
  pipeline/curated/<id>.notes.json     curated note overlay (summary, key figures, sub-notes, flags)
  pipeline/out/<id>.notes.raw.json     machine-extracted note text, pages, auto cross-references

Output:
  data/<id>.js        window.FILINGS["<id>"] = {...}   (notes carry full text + back-links)
  data/registry.js    window.FILING_INDEX = [...]      (light summary for the portfolio page)

The build computes the cross-reference index: every statement line (and every column
heading) that carries a note reference is parsed and recorded on that note as
`referencedBy`, and the auditor's key audit matters and investor-lens findings are
recorded as `mentionedIn`. That index is what drives the drawer back-links and the
cross-reference map in the UI.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / "pipeline" / "curated"
RAW = ROOT / "pipeline" / "out"
DATA = ROOT / "data"

REF = re.compile(r"^(\d{1,2})(?:\s*\(([a-z0-9]+)\)|\s*[-–]\s*([A-Za-z])|\.(\d+))?$")


def parse_ref(ref: str):
    out = []
    for part in re.split(r"\s*,\s*", str(ref or "").strip()):
        if not part:
            continue
        m = REF.match(part)
        if not m:
            num = re.search(r"\d{1,2}", part)
            out.append({"raw": part, "n": num.group(0) if num else "", "sub": None})
            continue
        sub = None
        if m.group(2):
            sub = f"({m.group(2)})"
        elif m.group(3):
            sub = m.group(3).upper()
        elif m.group(4):
            sub = f"{m.group(1)}.{m.group(4)}"
        out.append({"raw": part, "n": m.group(1), "sub": sub})
    return out


def load(p: Path, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def title_case(t: str) -> str:
    if t.isupper():
        small = {"and", "of", "the", "to", "for", "in", "on", "at", "or"}
        words = t.lower().split()
        return " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(words))
    return t


def build(fid: str):
    company = load(CUR / f"{fid}.company.json")
    if not company:
        print(f"skip {fid}: no company.json", file=sys.stderr)
        return None
    raw = load(RAW / f"{fid}.notes.raw.json", {"notes": []})
    curated = load(CUR / f"{fid}.notes.json", {"notes": []})
    cur_by_n = {str(n["n"]): n for n in curated.get("notes", [])}

    notes = []
    for r in raw["notes"]:
        c = cur_by_n.get(str(r["n"]), {})
        refs = sorted(set(map(str, c.get("refs") or [])) | set(map(str, r.get("refs") or [])), key=int)
        refs = [x for x in refs if x != str(r["n"])]
        notes.append({
            "n": str(r["n"]),
            "title": c.get("title") or title_case(r["title"]),
            "category": c.get("category") or "disclosure",
            "summary": c.get("summary") or "",
            "keyFigures": c.get("keyFigures") or [],
            "subnotes": c.get("subnotes") if c.get("subnotes") is not None else r.get("subnotes", [])[:12],
            "refs": refs,
            "tags": c.get("tags") or [],
            "investorRelevance": c.get("investorRelevance"),
            "flag": c.get("flag"),
            "pdfPage": r["pdfPage"],
            "printedPage": r["printedPage"],
            "text": r["text"],
            "referencedBy": [],
            "mentionedIn": [],
        })
    by_n = {n["n"]: n for n in notes}

    # ── cross-reference index from the face of the statements ──
    xrefs = []
    lines_with_notes = 0
    for st in company["statements"]:
        for idx, row in enumerate(st["rows"]):
            if not row.get("n"):
                continue
            lines_with_notes += 1
            for p in parse_ref(row["n"]):
                if p["n"] in by_n:
                    entry = {"stmt": st["id"], "short": st["short"], "row": idx, "label": row["l"] or st["short"], "ref": p["raw"], "sub": p["sub"]}
                    by_n[p["n"]]["referencedBy"].append(entry)
                    xrefs.append({**entry, "n": p["n"]})
                else:
                    print(f"  ! {fid}: {st['id']} row {idx} refers to unknown note {p['raw']}", file=sys.stderr)
        for ci, cn in enumerate(st.get("colNotes") or []):
            if cn and cn in by_n:
                entry = {"stmt": st["id"], "short": st["short"], "row": -(ci + 1), "label": f"Column heading: {st['cols'][ci]}", "ref": cn, "sub": None}
                by_n[cn]["referencedBy"].append(entry)
                xrefs.append({**entry, "n": cn})
    for kam in company.get("auditor", {}).get("kams", []):
        for ref in kam.get("notes", []):
            for p in parse_ref(ref):
                if p["n"] in by_n:
                    by_n[p["n"]]["mentionedIn"].append({"type": "Key audit matter", "title": kam["title"]})
    for item in company.get("lens", []):
        for ref in item.get("notes", []):
            for p in parse_ref(ref):
                if p["n"] in by_n:
                    by_n[p["n"]]["mentionedIn"].append({"type": "Investor lens", "title": item["area"]})

    flags = {"alert": 0, "watch": 0, "info": 0}
    for n in notes:
        if n["flag"]:
            flags[n["flag"]["level"]] = flags.get(n["flag"]["level"], 0) + 1
    referenced = sorted({x["n"] for x in xrefs}, key=int)
    stats = {
        "notes": len(notes),
        "notesReferenced": len(referenced),
        "notesDisclosureOnly": [n["n"] for n in notes if n["n"] not in referenced],
        "statementLines": sum(len(s["rows"]) for s in company["statements"]),
        "linesWithNotes": lines_with_notes,
        "links": len(xrefs),
        "flags": flags,
        "lens": {k: sum(1 for l in company.get("lens", []) if l["status"] == k) for k in ("green", "amber", "red")},
        "curated": len(cur_by_n),
        "textChars": sum(len(n["text"]) for n in notes),
    }

    bundle = dict(company)
    bundle["notes"] = notes
    bundle["xrefs"] = xrefs
    bundle["stats"] = stats
    bundle["years"] = ["2024", "2023"]
    DATA.mkdir(exist_ok=True)
    js = "window.FILINGS=window.FILINGS||{};\nwindow.FILINGS[" + json.dumps(fid) + "]=" + json.dumps(bundle, ensure_ascii=False) + ";\n"
    (DATA / f"{fid}.js").write_text(js, encoding="utf-8")
    print(f"{fid}: {stats['notes']} notes ({stats['curated']} curated), {stats['linesWithNotes']} statement lines carry notes, "
          f"{stats['links']} links, {stats['notesReferenced']} notes referenced, flags={flags} → data/{fid}.js ({len(js)//1024} KB)", file=sys.stderr)
    return {k: bundle[k] for k in ("id", "name", "shortName", "ticker", "sector", "fy", "periodEnd", "unit", "scale", "pdf", "kpis", "ratios", "stats", "lens", "charts")} | {
        "auditor": {"firm": bundle["auditor"]["firm"], "opinion": bundle["auditor"]["opinion"], "kams": len(bundle["auditor"]["kams"]), "otherMatter": bool(bundle["auditor"].get("otherMatter")), "reportDate": bundle["auditor"]["reportDate"]},
        "flagged": [{"n": n["n"], "title": n["title"], "level": n["flag"]["level"], "text": n["flag"]["text"]} for n in notes if n["flag"]],
    }


def main():
    ids = [p.name.replace(".company.json", "") for p in sorted(CUR.glob("*.company.json"))]
    index = [b for b in (build(f) for f in ids) if b]
    (DATA / "registry.js").write_text("window.FILING_INDEX=" + json.dumps(index, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"registry: {len(index)} filings → data/registry.js", file=sys.stderr)


if __name__ == "__main__":
    main()
