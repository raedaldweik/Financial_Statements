"""Filing storage: one folder per filing under STORAGE_DIR.

  <id>/source.pdf     the uploaded filing
  <id>/status.json    pipeline progress (stages, log, error)
  <id>/raw.json       extraction output (docmap, notes text)
  <id>/bundle.json    the dashboard bundle once ready
  <id>/meta.json      upload metadata

Seeded demo filings live in backend/seed/<id>.bundle.json with their PDFs in filings/; they are
copied into storage on first start so the registry has a single source of truth.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import config

_lock = threading.RLock()

STAGES = [
    ("extract", "Extract text", "pdftotext per page, page furniture removed"),
    ("segment", "Map document", "auditor's report, primary statements and notes located; notes split by heading"),
    ("statements", "Transcribe statements", "every line with its note reference, values per column"),
    ("company", "Company & auditor", "entity, period, unit, opinion, key audit matters"),
    ("notes", "Curate notes", "summary, key figures, sub-sections, flags per note"),
    ("analysis", "Investor analysis", "KPIs, ratios, charts, analyst brief, investor lens"),
    ("build", "Cross-reference", "statement lines ⟷ notes index"),
]


def filing_dir(fid: str) -> Path:
    return config.STORAGE_DIR / fid


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, data) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def new_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "filing").lower()).strip("-")[:24] or "filing"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def create(upload_name: str, pdf_bytes: bytes, meta: dict) -> str:
    fid = new_id(meta.get("name") or Path(upload_name).stem)
    d = filing_dir(fid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.pdf").write_bytes(pdf_bytes)
    _write(d / "meta.json", {"id": fid, "uploadName": upload_name, "createdAt": time.time(), **meta})
    init_status(fid)
    return fid


def init_status(fid: str) -> dict:
    st = {"id": fid, "state": "queued", "stage": None, "error": None, "startedAt": time.time(), "finishedAt": None,
          "stages": [{"id": s[0], "label": s[1], "detail": s[2], "state": "pending", "info": "", "ms": 0} for s in STAGES], "log": []}
    _write(filing_dir(fid) / "status.json", st)
    return st


def status(fid: str) -> dict | None:
    return _read(filing_dir(fid) / "status.json")


def update_status(fid: str, **patch) -> dict:
    with _lock:
        st = status(fid) or init_status(fid)
        st.update(patch)
        _write(filing_dir(fid) / "status.json", st)
        return st


def stage(fid: str, sid: str, state: str, info: str = "", ms: int | None = None, log: str | None = None) -> None:
    with _lock:
        st = status(fid) or init_status(fid)
        for s in st["stages"]:
            if s["id"] == sid:
                s["state"] = state
                if info:
                    s["info"] = info
                if ms is not None:
                    s["ms"] = ms
        st["stage"] = sid
        st["state"] = "running"
        if log:
            st["log"].append({"t": time.time(), "stage": sid, "msg": log})
            st["log"] = st["log"][-200:]
        _write(filing_dir(fid) / "status.json", st)


def log(fid: str, msg: str, sid: str | None = None) -> None:
    with _lock:
        st = status(fid) or init_status(fid)
        st["log"].append({"t": time.time(), "stage": sid or st.get("stage"), "msg": msg})
        st["log"] = st["log"][-200:]
        _write(filing_dir(fid) / "status.json", st)


def save_raw(fid: str, raw: dict) -> None:
    _write(filing_dir(fid) / "raw.json", raw)


def save_bundle(fid: str, bundle: dict) -> None:
    _write(filing_dir(fid) / "bundle.json", bundle)


def bundle(fid: str) -> dict | None:
    return _read(filing_dir(fid) / "bundle.json")


def meta(fid: str) -> dict | None:
    return _read(filing_dir(fid) / "meta.json")


def pdf_path(fid: str) -> Path | None:
    p = filing_dir(fid) / "source.pdf"
    if p.exists():
        return p
    b = bundle(fid) or {}
    rel = (b.get("pdf") or "").split("/")[-1]
    seed = config.SEED_FILINGS_DIR / rel
    return seed if rel and seed.exists() else None


def list_ids() -> list[str]:
    if not config.STORAGE_DIR.exists():
        return []
    return sorted([p.name for p in config.STORAGE_DIR.iterdir() if p.is_dir() and (p / "status.json").exists() or (p / "bundle.json").exists()],
                  key=lambda n: (meta(n) or {}).get("createdAt", 0))


def delete(fid: str) -> bool:
    d = filing_dir(fid)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


def seed_from(seed_dir: Path) -> list[str]:
    """Copy the bundled demo filings into storage (idempotent)."""
    made = []
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(seed_dir.glob("*.bundle.json")):
        b = _read(f)
        if not b:
            continue
        fid = b["id"]
        d = filing_dir(fid)
        if (d / "bundle.json").exists():
            continue
        d.mkdir(parents=True, exist_ok=True)
        b.setdefault("mode", "curated")
        b.setdefault("createdAt", f.stat().st_mtime)
        _write(d / "bundle.json", b)
        _write(d / "meta.json", {"id": fid, "uploadName": Path(b.get("pdf", "")).name, "createdAt": b["createdAt"], "seed": True})
        st = init_status(fid)
        for s in st["stages"]:
            s["state"] = "done"
        st.update({"state": "ready", "finishedAt": time.time()})
        _write(d / "status.json", st)
        made.append(fid)
    return made
