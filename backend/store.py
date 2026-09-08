"""In-memory case + analysis-run store (demo scope: no persistence)."""
from __future__ import annotations

import base64
import io
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from pypdf import PdfReader

from config import DEMO_DIR

MAX_EVIDENCE_CHARS = 40000
MAX_FILES_PER_KIND = 8

import json


@dataclass
class Case:
    case_id: str
    complaint: dict = field(default_factory=dict)
    # Complaint evidence — the conversation/complaint comes in as screenshots
    complaint_images: list[dict] = field(default_factory=list)   # {name, b64, media}
    complaint_text: str = ""                                     # optional txt/pdf fallback
    # Financial statements — one or more PDFs/CSVs (text extracted)
    statements: list[dict] = field(default_factory=list)         # {name, text}
    is_demo: bool = False
    memos: dict[str, str] = field(default_factory=dict)
    report: Optional[dict] = None
    qa_history: list[dict] = field(default_factory=list)

    def has_evidence(self) -> bool:
        return bool(self.complaint_images or self.complaint_text or self.statements)

    def evidence_summary(self) -> dict:
        return {
            "complaint_images": [i["name"] for i in self.complaint_images],
            "complaint_text": bool(self.complaint_text),
            "complaint_text_preview": self.complaint_text[:300],
            "statements": [s["name"] for s in self.statements],
            "statement_preview": self.statements[0]["text"][:300] if self.statements else "",
        }


CASES: dict[str, Case] = {}
RUNS: dict[str, dict[str, Any]] = {}  # run_id -> {queue, case_id, mode, status}


def new_case() -> Case:
    case = Case(case_id=f"case-{uuid.uuid4().hex[:12]}")
    CASES[case.case_id] = case
    return case


def get_case(case_id: str) -> Optional[Case]:
    return CASES.get(case_id)


def load_demo_case() -> Case:
    case = new_case()
    case.is_demo = True
    case.complaint = json.loads((DEMO_DIR / "complaint.json").read_text(encoding="utf-8"))
    for i in (1, 2, 3):
        p = DEMO_DIR / f"chat_{i}.png"
        if p.exists():
            case.complaint_images.append({
                "name": f"WhatsApp screenshot {i} of 3.png",
                "b64": base64.standard_b64encode(p.read_bytes()).decode(),
                "media": "image/png",
            })
    if not case.complaint_images:  # fallback if screenshots are missing
        case.complaint_text = (DEMO_DIR / "conversation.txt").read_text(encoding="utf-8")
    case.statements.append({
        "name": "Al Noor National Bank statement — Aug 2026.pdf",
        "text": extract_pdf_text((DEMO_DIR / "bank_statement.pdf").read_bytes()),
    })
    return case


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return ("\n".join(parts)).strip()[:MAX_EVIDENCE_CHARS]


def attach_evidence(case: Case, kind: str, filename: str, data: bytes,
                    content_type: str) -> dict:
    """Attach an uploaded file to the case (appends). Returns a UI summary."""
    name = filename or "upload"
    lowered = name.lower()
    if kind == "complaint":
        if len(case.complaint_images) >= MAX_FILES_PER_KIND:
            raise ValueError(f"Maximum {MAX_FILES_PER_KIND} complaint images")
        if content_type.startswith("image/") or lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
            media = content_type if content_type.startswith("image/") else (
                "image/png" if lowered.endswith(".png") else "image/jpeg")
            case.complaint_images.append({
                "name": name,
                "b64": base64.standard_b64encode(data).decode(),
                "media": media,
            })
        elif lowered.endswith(".pdf"):
            case.complaint_text += ("\n\n" if case.complaint_text else "") + extract_pdf_text(data)
        else:
            text = data.decode("utf-8", errors="replace")[:MAX_EVIDENCE_CHARS]
            case.complaint_text += ("\n\n" if case.complaint_text else "") + text
    elif kind == "statement":
        if len(case.statements) >= MAX_FILES_PER_KIND:
            raise ValueError(f"Maximum {MAX_FILES_PER_KIND} statements")
        if lowered.endswith(".pdf") or content_type == "application/pdf":
            text = extract_pdf_text(data)
        else:
            text = data.decode("utf-8", errors="replace")[:MAX_EVIDENCE_CHARS]
        case.statements.append({"name": name, "text": text})
    else:
        raise ValueError(f"Unknown evidence kind: {kind}")
    return case.evidence_summary()
