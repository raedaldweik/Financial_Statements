"""Investor Financial Intelligence — API + static frontend.

  GET  /api/health                     server mode (llm on/off), model, key status, filing count
  POST /api/llm/check                  re-test the ANTHROPIC_API_KEY against the API
  GET  /api/filings                    registry: ready filings (summary) and filings in progress
  POST /api/filings                    multipart upload (file=PDF, name?, ticker?, sector?) → starts the pipeline
  GET  /api/filings/{id}               the dashboard bundle (or the processing status while it runs)
  GET  /api/filings/{id}/status        pipeline stages + log
  POST /api/filings/{id}/rerun         re-run the pipeline on the stored PDF
  DELETE /api/filings/{id}             remove a filing (samples too; a removed sample stays removed)
  POST /api/samples/restore            put the sample filings back
  DELETE /api/samples                  remove every sample filing
  GET  /filings/{name}.pdf             the source PDF (deep-linked by page from the UI)
  /                                    the frontend (frontend/)
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import llm as llm_mod
import store
from pipeline.build import registry_entry
from pipeline.run import run as run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("misa")

app = FastAPI(title="Investor Financial Intelligence", version="1.0")
_sem = threading.Semaphore(int(__import__("os").getenv("MAX_PARALLEL_JOBS", "2")))


@app.on_event("startup")
def _startup():
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    # samples are app-owned: drop any stored sample that is no longer in the configured set
    wanted = set(store.sample_ids(config.SEED_DIR)) if config.SEED_SAMPLES else set()
    stale = [i for i in store.list_ids() if store.is_sample(i) and i not in wanted]
    for i in stale:
        store.delete(i, remember=False)
    if stale:
        log.info("removed sample filings no longer configured: %s", stale)
    if config.SEED_SAMPLES:
        made = store.seed_from(config.SEED_DIR)
        if made:
            log.info("seeded sample filings: %s", made)
    else:
        log.info("SEED_SAMPLES is off: no sample filings seeded")
    # resume anything interrupted by a restart
    for fid in store.list_ids():
        st = store.status(fid) or {}
        if st.get("state") in ("queued", "running") and (store.filing_dir(fid) / "source.pdf").exists():
            _launch(fid)
    log.info("mode: %s · model: %s · storage: %s", "full" if config.llm_configured() else "extraction-only", config.MODEL, config.STORAGE_DIR)
    if config.llm_configured():
        threading.Thread(target=llm_mod.check_key, name="key-check", daemon=True).start()


def _launch(fid: str):
    def job():
        with _sem:
            run_pipeline(fid)
    threading.Thread(target=job, name=f"pipeline-{fid}", daemon=True).start()


def _status_summary(fid: str) -> dict:
    st = store.status(fid) or {}
    meta = store.meta(fid) or {}
    done = sum(1 for s in st.get("stages", []) if s["state"] == "done")
    return {"id": fid, "name": meta.get("name") or meta.get("uploadName") or fid, "shortName": meta.get("name") or Path(meta.get("uploadName", fid)).stem,
            "ticker": meta.get("ticker"), "sector": meta.get("sector"), "status": st.get("state", "queued"), "stage": st.get("stage"), "stages": st.get("stages", []),
            "progress": round(done / max(len(st.get("stages", [])), 1), 2), "error": st.get("error"), "warnings": st.get("warnings", []),
            "createdAt": meta.get("createdAt"), "startedAt": st.get("startedAt"), "finishedAt": st.get("finishedAt"), "mode": st.get("mode"),
            "log": st.get("log", [])[-12:]}


@app.get("/api/health")
def health():
    ids = store.list_ids()
    samples = [i for i in ids if store.is_sample(i)]
    return {"ok": True, "llm": config.llm_configured(), "model": config.MODEL if config.llm_configured() else None,
            "mode": "full" if llm_mod.llm_ready() else "extraction-only", "filings": len(ids),
            "llmStatus": {k: llm_mod.KEY_STATUS.get(k) for k in ("ok", "error", "checkedAt", "keyHint")},
            "logo": next((f"assets/{n}" for n in ("misa-logo.svg", "misa-logo.png", "misa-logo.jpg", "misa-logo.webp") if (config.FRONTEND_DIR / "assets" / n).exists()), None),
            "samples": len(samples), "uploads": len(ids) - len(samples), "samplesAvailable": len(store.sample_ids(config.SEED_DIR)),
            "maxUploadMb": config.MAX_UPLOAD_MB}


@app.get("/api/filings")
def list_filings():
    out = []
    for fid in store.list_ids():
        b = store.bundle(fid)
        st = store.status(fid) or {}
        if b and st.get("state", "ready") == "ready":
            e = registry_entry(b)
            e["warnings"] = b.get("warnings", [])
            e["sample"] = store.is_sample(fid)
            out.append(e)
        else:
            out.append(_status_summary(fid))
    out.sort(key=lambda x: x.get("createdAt") or 0)
    return out


@app.post("/api/filings")
async def upload(file: UploadFile = File(...), name: str | None = Form(None), ticker: str | None = Form(None), sector: str | None = Form(None)):
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "The upload is not a PDF.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"PDF larger than {config.MAX_UPLOAD_MB} MB.")
    fid = store.create(file.filename or "filing.pdf", data, {"name": (name or "").strip() or None, "ticker": (ticker or "").strip() or None, "sector": (sector or "").strip() or None})
    _launch(fid)
    return {"id": fid, "status": "queued", "mode": "full" if llm_mod.llm_ready() else "extraction-only"}


@app.get("/api/filings/{fid}")
def get_filing(fid: str):
    b = store.bundle(fid)
    st = store.status(fid)
    if b and (not st or st.get("state") == "ready"):
        return JSONResponse(b | {"status": "ready"})
    if st:
        return _status_summary(fid)
    raise HTTPException(404, "Unknown filing")


@app.get("/api/filings/{fid}/status")
def get_status(fid: str):
    if not store.status(fid):
        raise HTTPException(404, "Unknown filing")
    return _status_summary(fid)


@app.post("/api/filings/{fid}/rerun")
def rerun(fid: str):
    if not (store.filing_dir(fid) / "source.pdf").exists():
        raise HTTPException(400, "This filing has no stored PDF to re-run (sample filing).")
    store.init_status(fid)
    _launch(fid)
    return {"id": fid, "status": "queued"}


@app.delete("/api/filings/{fid}")
def delete(fid: str):
    if not store.delete(fid):
        raise HTTPException(404, "Unknown filing")
    return {"deleted": fid}


@app.post("/api/llm/check")
def llm_check():
    """Re-check the API key (after changing it in the environment, redeploy; this re-tests the running value)."""
    st = llm_mod.check_key()
    return {k: st.get(k) for k in ("ok", "error", "checkedAt", "keyHint")} | {"model": config.MODEL, "models": st.get("models", [])[:20]}


@app.post("/api/samples/restore")
def restore_samples():
    made = store.restore_samples(config.SEED_DIR)
    return {"restored": made, "samples": [i for i in store.list_ids() if store.is_sample(i)]}


@app.delete("/api/samples")
def remove_samples():
    gone = [i for i in store.list_ids() if store.is_sample(i) and store.delete(i)]
    return {"deleted": gone}


@app.get("/filings/{name}")
def filing_pdf(name: str):
    if not name.endswith(".pdf"):
        raise HTTPException(404)
    fid = name[:-4]
    p = store.pdf_path(fid)
    if not p:
        seed = config.SEED_FILINGS_DIR / name
        p = seed if seed.exists() else None
    if not p:
        raise HTTPException(404, "PDF not found")
    return FileResponse(p, media_type="application/pdf", filename=name)


app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
