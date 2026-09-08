"""Fraud Complaint Analyzer — agentic AI demo for police financial investigation units.

FastAPI backend serving the API + the static frontend. See README.md at the
repository root for the storyline and Railway deployment notes.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import pipeline
import store

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Fraud Complaint Analyzer", version="1.0")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_configured": config.llm_configured(),
            "model": config.MODEL,
            "default_mode": pipeline.resolve_mode("auto")}


@app.post("/api/case/new")
def case_new() -> dict:
    case = store.new_case()
    return {"case_id": case.case_id, "complaint": {}, "evidence": case.evidence_summary()}


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


class AnalyzeRequest(BaseModel):
    case_id: str
    mode: str = "auto"          # auto | live | replay
    complaint: dict | None = None


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest) -> dict:
    case = store.get_case(req.case_id)
    if not case:
        raise HTTPException(404, "Unknown case id")
    if req.complaint:
        case.complaint = req.complaint
    mode = pipeline.resolve_mode(req.mode)
    if mode == "live" and not config.llm_configured():
        raise HTTPException(400, "Live mode requires ANTHROPIC_API_KEY. "
                                 "Use simulation mode or configure the key.")
    if mode == "live" and not case.has_evidence():
        raise HTTPException(400, "Attach at least one piece of evidence "
                                 "(complaint screenshots or a financial statement) "
                                 "before analyzing.")
    case.memos.clear()
    case.report = None
    run_id = pipeline.start_run(case, mode)
    return {"run_id": run_id, "mode": mode}


@app.get("/api/stream/{run_id}")
async def stream(run_id: str) -> StreamingResponse:
    return StreamingResponse(
        pipeline.event_stream(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AskRequest(BaseModel):
    case_id: str
    question: str


@app.post("/api/ask")
async def ask(req: AskRequest) -> dict:
    case = store.get_case(req.case_id)
    if not case:
        raise HTTPException(404, "Unknown case id")
    if not req.question.strip():
        raise HTTPException(400, "Empty question")
    return await pipeline.answer_question(case, req.question.strip()[:2000])


@app.get("/api/demo/statement.pdf")
def demo_statement() -> FileResponse:
    return FileResponse(config.DEMO_DIR / "bank_statement.pdf",
                        media_type="application/pdf",
                        filename="bank_statement_aug_2026.pdf")


@app.get("/api/demo/conversation.txt")
def demo_conversation() -> FileResponse:
    return FileResponse(config.DEMO_DIR / "conversation.txt",
                        media_type="text/plain; charset=utf-8")


@app.get("/api/demo/img/{n}")
def demo_evidence_image(n: int) -> FileResponse:
    if not 0 <= n < len(store.DEMO_IMAGES):
        raise HTTPException(404, "No such image")
    fname, _, media = store.DEMO_IMAGES[n]
    return FileResponse(config.DEMO_DIR / fname, media_type=media)


app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
