"""Financial Crime Unit — complaint intake portal + investigator case management.

FastAPI backend serving the API and the static frontend. See README.md.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio
from typing import Optional

from pydantic import BaseModel

import config
import pipeline
import registry
import translate
import store

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Financial Crime Unit — Complaint Analyzer", version="2.0")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_configured": config.llm_configured(),
            "model": config.MODEL, "default_mode": pipeline.resolve_mode("auto"),
            "today": registry.today()}


# ─── Citizen portal ─────────────────────────────────────────────────

@app.post("/api/case/new")
def case_new() -> dict:
    case = store.new_case()
    return {"case_id": case.case_id, "evidence": case.evidence_summary()}


@app.post("/api/case/demo")
def case_demo() -> dict:
    case = store.load_demo_case()
    return {"case_id": case.case_id, "complaint": case.complaint,
            "evidence": case.evidence_summary()}


@app.post("/api/upload")
async def upload(case_id: str = Form(...), kind: str = Form(...),
                 file: UploadFile = File(...)) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(404, "Unknown case id")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (15 MB max)")
    try:
        evidence = store.attach_evidence(case, kind, file.filename or "upload",
                                        data, file.content_type or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"case_id": case.case_id, "evidence": evidence}


class SubmitRequest(BaseModel):
    case_id: str
    complaint: dict
    mode: str = "auto"          # auto | live | replay (investigator setting)
    filed_local: Optional[str] = None   # browser local time "YYYY-MM-DDTHH:MM"


@app.post("/api/submit")
async def submit(req: SubmitRequest) -> dict:
    case = store.get_case(req.case_id)
    if not case:
        raise HTTPException(404, "Unknown case id")
    mode = pipeline.resolve_mode(req.mode)
    if mode == "live" and not config.llm_configured():
        mode = "replay"
    if mode == "live" and not case.has_evidence():
        raise HTTPException(400, "Please attach at least one screenshot or statement.")
    case.complaint = req.complaint
    case.memos.clear()
    case.report = None
    # register first so the ref is known, then start the run bound to it
    entry = registry.register_submission(case, case.complaint, run_id="", mode=mode,
                                         filed=req.filed_local)
    run_id = pipeline.start_run(case, mode, ref=entry["ref"])
    entry["run_id"] = run_id
    return {"ref": entry["ref"], "filed": entry["filed"], "run_id": run_id, "mode": mode}


# ─── Investigator workspace ─────────────────────────────────────────

@app.get("/api/cases")
def cases() -> dict:
    return {"today": registry.today(), "cases": registry.list_cases()}


@app.get("/api/cases/{ref}")
def case_detail(ref: str) -> dict:
    c = registry.get(ref)
    if not c:
        raise HTTPException(404, "Unknown case reference")
    return c


@app.get("/api/cases/{ref}/evidence/{index}")
def case_evidence(ref: str, index: int) -> Response:
    hit = registry.evidence_image(ref, index, store.get_case)
    if not hit:
        raise HTTPException(404, "No such evidence image")
    data, media = hit
    return Response(content=data, media_type=media)


@app.get("/api/stream/{run_id}")
async def stream(run_id: str) -> StreamingResponse:
    return StreamingResponse(
        pipeline.event_stream(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AskRequest(BaseModel):
    ref: str
    question: str
    lang: str = "en"


@app.post("/api/ask")
async def ask(req: AskRequest) -> dict:
    entry = registry.CASES.get(req.ref)
    if not entry:
        raise HTTPException(404, "Unknown case reference")
    if not req.question.strip():
        raise HTTPException(400, "Empty question")
    sc = store.get_case(entry["case_id"]) if entry.get("case_id") else None
    return await pipeline.answer_question(entry, req.question.strip()[:2000], sc,
                                          lang="ar" if req.lang == "ar" else "en")


@app.post("/api/cases/{ref}/translate")
async def case_translate(ref: str) -> dict:
    """Arabic case file: bundled, cached, or produced in the background."""
    entry = registry.CASES.get(ref)
    if not entry:
        raise HTTPException(404, "Unknown case reference")
    st = translate.schedule(ref)
    out = {"ref": ref, "status": st}
    if st == "ready":
        out["report_ar"] = entry.get("report_ar")
        out["complaint_text_ar"] = entry.get("complaint_text_ar")
    return out


@app.on_event("startup")
async def _prewarm_translations() -> None:
    asyncio.get_running_loop().create_task(translate.prewarm())


# ─── Demo assets ────────────────────────────────────────────────────

@app.get("/api/demo/statement.pdf")
def demo_statement() -> FileResponse:
    return FileResponse(config.DEMO_DIR / "bank_statement.pdf",
                        media_type="application/pdf",
                        filename="bank_statement_sep_2026.pdf")


@app.get("/api/demo/img/{n}")
def demo_evidence_image(n: int) -> FileResponse:
    if not 0 <= n < len(store.DEMO_IMAGES):
        raise HTTPException(404, "No such image")
    fname, _, media = store.DEMO_IMAGES[n]
    return FileResponse(config.DEMO_DIR / fname, media_type=media)


app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
