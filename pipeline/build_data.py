#!/usr/bin/env python3
"""Build the curated demo seeds.

    python3 pipeline/build_data.py

For every pipeline/curated/<id>.company.json it merges the hand-curated statements,
the note overlay (pipeline/curated/<id>.notes.json) and the machine-extracted note text
(pipeline/out/<id>.notes.raw.json) with the same assembler the live server uses
(backend/pipeline/build.py) and writes:

  backend/seed/<id>.bundle.json   loaded into storage when the server starts
  frontend/data/<id>.js           static fallback when the pages are opened without the server
  frontend/data/registry.js
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from pipeline.build import assemble, registry_entry  # noqa: E402

CUR = ROOT / "pipeline" / "curated"
RAW = ROOT / "pipeline" / "out"
SEED = ROOT / "backend" / "seed"
DATA = ROOT / "frontend" / "data"


def load(p: Path, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main():
    SEED.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    index = []
    for cf in sorted(CUR.glob("*.company.json")):
        fid = cf.name.replace(".company.json", "")
        company = load(cf)
        raw = load(RAW / f"{fid}.notes.raw.json", {"notes": []})
        curated = {str(n["n"]): n for n in load(CUR / f"{fid}.notes.json", {"notes": []})["notes"]}
        company.setdefault("mode", "curated")
        company.setdefault("createdAt", cf.stat().st_mtime)
        warnings = []
        bundle = assemble(company, raw["notes"], curated, warnings)
        for w in warnings:
            print(f"  ! {fid}: {w}", file=sys.stderr)
        (SEED / f"{fid}.bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        js = "window.FILINGS=window.FILINGS||{};\nwindow.FILINGS[" + json.dumps(fid) + "]=" + json.dumps(bundle, ensure_ascii=False) + ";\n"
        (DATA / f"{fid}.js").write_text(js, encoding="utf-8")
        s = bundle["stats"]
        print(f"{fid}: {s['notes']} notes ({s['curated']} curated), {s['linesWithNotes']} lines carry notes, {s['links']} links, flags={s['flags']} → seed + data ({len(js)//1024} KB)", file=sys.stderr)
        index.append(registry_entry(bundle))
    (DATA / "registry.js").write_text("window.FILING_INDEX=" + json.dumps(index, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"registry: {len(index)} filings", file=sys.stderr)


if __name__ == "__main__":
    main()
