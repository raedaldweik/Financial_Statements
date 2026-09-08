"""In-memory case + analysis-run store (demo scope: no persistence)."""
from __future__ import annotations

import base64
import io
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from pypdf import PdfReader

from config import DEMO_DIR

MAX_EVIDENCE_CHARS = 40000


@dataclass
class Case:
    case_id: str
    complaint: dict = field(default_factory=dict)
    conversation_text: str = ""
    conversation_image_b64: str = ""
    conversation_image_media: str = ""
    conversation_name: str = ""
    statement_text: str = ""
    statement_name: str = ""
    is_demo: bool = False
    memos: dict[str, str] = field(default_factory=dict)
    report: Optional[dict] = None
    qa_history: list[dict] = field(default_factory=list)

    def evidence_summary(self) -> dict:
        return {
            "conversation": bool(self.conversation_text or self.conversation_image_b64),
            "conversation_name": self.conversation_name,
            "conversation_preview": self.conversation_text[:400],
            "statement": bool(self.statement_text),
            "statement_name": self.statement_name,
            "statement_preview": self.statement_text[:400],
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
    case.conversation_text = (DEMO_DIR / "conversation.txt").read_text(encoding="utf-8")
    case.conversation_name = "WhatsApp chat export — victim & seller.txt"
    case.statement_text = extract_pdf_text((DEMO_DIR / "bank_statement.pdf").read_bytes())
    case.statement_name = "Al Noor National Bank statement — Aug 2026.pdf"
    return case


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return ("\n".join(parts)).strip()[:MAX_EVIDENCE_CHARS]


def attach_evidence(case: Case, kind: str, filename: str, data: bytes,
                    content_type: str) -> dict:
    """Attach an uploaded file to the case. Returns a summary for the UI."""
    name = filename or "upload"
    lowered = name.lower()
    if kind == "conversation":
        if content_type.startswith("image/") or lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
            media = content_type if content_type.startswith("image/") else (
                "image/png" if lowered.endswith(".png") else "image/jpeg")
            case.conversation_image_b64 = base64.standard_b64encode(data).decode()
            case.conversation_image_media = media
            case.conversation_text = ""
        elif lowered.endswith(".pdf"):
            case.conversation_text = extract_pdf_text(data)
            case.conversation_image_b64 = ""
        else:
            case.conversation_text = data.decode("utf-8", errors="replace")[:MAX_EVIDENCE_CHARS]
            case.conversation_image_b64 = ""
        case.conversation_name = name
    elif kind == "statement":
        if lowered.endswith(".pdf") or content_type == "application/pdf":
            case.statement_text = extract_pdf_text(data)
        else:
            case.statement_text = data.decode("utf-8", errors="replace")[:MAX_EVIDENCE_CHARS]
        case.statement_name = name
    else:
        raise ValueError(f"Unknown evidence kind: {kind}")
    return case.evidence_summary()
