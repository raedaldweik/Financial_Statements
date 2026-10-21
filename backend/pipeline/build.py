"""Assemble a filing bundle: statements + notes → cross-reference index, stats, registry row.

The same function builds the curated demo seeds (pipeline/build_data.py) and the bundles of
uploaded filings, so the frontend sees one contract.
"""
from __future__ import annotations

import re

REF = re.compile(r"^(\d{1,2})(?:\s*\(([a-z0-9]+)\)|\s*[-–]\s*([A-Za-z])|\.(\d+))?$")


def parse_ref(ref: str):
    out = []
    for part in re.split(r"\s*[,&]\s*", str(ref or "").strip()):
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


def merge_notes(raw_notes: list[dict], curated: dict[str, dict] | None) -> list[dict]:
    curated = curated or {}
    notes = []
    for r in raw_notes:
        c = curated.get(str(r["n"]), {})
        refs = sorted(set(map(str, c.get("refs") or [])) | set(map(str, r.get("refs") or [])), key=lambda x: int(x) if x.isdigit() else 99)
        refs = [x for x in refs if x != str(r["n"])]
        subnotes = c.get("subnotes")
        if subnotes is None:
            subnotes = (r.get("subnotes") or [])[:12]
        notes.append({
            "n": str(r["n"]),
            "title": c.get("title") or r.get("title") or f"Note {r['n']}",
            "category": c.get("category") or "disclosure",
            "summary": c.get("summary") or "",
            "keyFigures": c.get("keyFigures") or [],
            "subnotes": subnotes,
            "refs": refs,
            "tags": c.get("tags") or [],
            "investorRelevance": c.get("investorRelevance"),
            "flag": c.get("flag"),
            "pdfPage": r.get("pdfPage"),
            "printedPage": r.get("printedPage", r.get("pdfPage")),
            "text": r.get("text", ""),
            "referencedBy": [],
            "mentionedIn": [],
        })
    return notes


def assemble(company: dict, raw_notes: list[dict], curated: dict[str, dict] | None, warnings: list[str] | None = None) -> dict:
    warnings = warnings if warnings is not None else []
    notes = merge_notes(raw_notes, curated)
    by_n = {n["n"]: n for n in notes}
    xrefs, lines_with_notes = [], 0
    for st in company.get("statements", []):
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
                    warnings.append(f"{st['id']} row {idx} ('{row['l'][:40]}') refers to note {p['raw']} which was not found")
        for ci, cn in enumerate(st.get("colNotes") or []):
            if cn and cn in by_n:
                entry = {"stmt": st["id"], "short": st["short"], "row": -(ci + 1), "label": f"Column heading: {st['cols'][ci]}", "ref": cn, "sub": None}
                by_n[cn]["referencedBy"].append(entry)
                xrefs.append({**entry, "n": cn})
    for kam in (company.get("auditor") or {}).get("kams", []):
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
        "statementLines": sum(len(s["rows"]) for s in company.get("statements", [])),
        "linesWithNotes": lines_with_notes,
        "links": len(xrefs),
        "flags": flags,
        "lens": {k: sum(1 for l in company.get("lens", []) if l.get("status") == k) for k in ("green", "amber", "red")},
        "curated": sum(1 for n in notes if n["summary"]),
        "textChars": sum(len(n["text"]) for n in notes),
    }
    bundle = dict(company)
    bundle["notes"] = notes
    bundle["xrefs"] = xrefs
    bundle["stats"] = stats
    bundle["years"] = company.get("years") or ["2024", "2023"]
    bundle["warnings"] = warnings
    return bundle


def registry_entry(bundle: dict) -> dict:
    a = bundle.get("auditor") or {}
    return {k: bundle.get(k) for k in ("id", "name", "shortName", "ticker", "sector", "fy", "periodEnd", "unit", "scale", "pdf", "kpis", "ratios", "stats", "lens", "charts", "mode", "createdAt")} | {
        "auditor": {"firm": a.get("firm"), "opinion": a.get("opinion"), "kams": len(a.get("kams") or []), "otherMatter": bool(a.get("otherMatter")), "reportDate": a.get("reportDate")},
        "flagged": [{"n": n["n"], "title": n["title"], "level": n["flag"]["level"], "text": n["flag"]["text"]} for n in bundle["notes"] if n.get("flag")],
        "status": "ready",
    }
