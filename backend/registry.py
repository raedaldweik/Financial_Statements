"""Case registry: the investigator's queue. Seeded from demo_data/cases.json,
extended in memory by citizen submissions (demo scope: no persistence)."""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
from typing import Optional

from config import DEMO_DIR

_data = json.loads((DEMO_DIR / "cases.json").read_text(encoding="utf-8"))
TODAY: str = os.getenv("DEMO_TODAY", _data.get("today", dt.date.today().isoformat()))
CASES: dict[str, dict] = {c["ref"]: c for c in _data["cases"]}
_seq: int = int(_data.get("next_sequence", 231))

_TYPE_MAP = [
    (("purchase", "product", "trading", "delivery", "shop"), "Online purchase fraud"),
    (("investment", "citizenship", "crypto", "trading platform"), "Investment fraud"),
    (("phish", "account takeover", "otp", "card"), "Phishing / account takeover"),
    (("rental", "apartment", "tenancy"), "Rental fraud"),
    (("job", "employment", "recruit"), "Employment fraud"),
    (("romance", "relationship"), "Romance fraud"),
    (("invoice", "email compromise", "supplier"), "Business email compromise"),
]


def _type_for(category: str) -> str:
    c = (category or "").lower()
    for keys, label in _TYPE_MAP:
        if any(k in c for k in keys):
            return label
    return category or "Fraud — other"


def _now_stamp() -> str:
    return f"{TODAY}T{dt.datetime.now().strftime('%H:%M')}"


def days_open(filed: str) -> int:
    try:
        d = dt.date.fromisoformat(filed[:10])
        return max(0, (dt.date.fromisoformat(TODAY) - d).days)
    except ValueError:
        return 0


def summary_row(c: dict) -> dict:
    """Queue row: everything except the heavy report body."""
    return {k: v for k, v in c.items() if k not in ("report", "memos", "complaint_text", "qa_history")} | {
        "has_report": bool(c.get("report")),
        "days_open": days_open(c["filed"]),
        "linked_count": len(c.get("linked_refs") or []),
    }


def list_cases() -> list[dict]:
    rows = [summary_row(c) for c in CASES.values()]
    rows.sort(key=lambda r: r["filed"], reverse=True)
    return rows


def get(ref: str) -> Optional[dict]:
    c = CASES.get(ref)
    if not c:
        return None
    return c | {"days_open": days_open(c["filed"]), "has_report": bool(c.get("report"))}


def register_submission(store_case, complaint: dict, run_id: str, mode: str) -> dict:
    global _seq
    ref = f"FC-2026-{_seq:04d}"
    _seq += 1
    victim = complaint.get("victim", {})
    evidence = [i["name"] for i in store_case.complaint_images]
    if store_case.complaint_text:
        evidence.append("Conversation transcript (text)")
    evidence += [s["name"] for s in store_case.statements]
    entry = {
        "ref": ref,
        "filed": _now_stamp(),
        "complainant": victim.get("name") or "Unnamed complainant",
        "emirate": victim.get("emirate") or "",
        "type": _type_for(complaint.get("category", "")),
        "subtype": complaint.get("category") or "",
        "amount": float(complaint.get("claimed_loss") or 0),
        "currency": complaint.get("currency", "AED"),
        "status": "New",
        "stage": "Analysis in progress",
        "officer": None,
        "risk_score": None,
        "risk_level": None,
        "channel": complaint.get("channel", "e-Crime Portal"),
        "evidence": evidence,
        "complaint_text": complaint.get("narrative", ""),
        "linked_refs": [],
        "report": None,
        "memos": {},
        "qa_history": [],
        "case_id": store_case.case_id,
        "run_id": run_id,
        "mode": mode,
        "processing": True,
        "image_count": len(store_case.complaint_images),
        "is_demo": store_case.is_demo,
    }
    complaint["complaint_ref"] = ref
    CASES[ref] = entry
    return entry


def complete(ref: str, report: dict, memos: dict) -> None:
    c = CASES.get(ref)
    if not c:
        return
    report = dict(report)
    report["case_ref"] = ref
    c["report"] = report
    c["memos"] = dict(memos)
    c["risk_score"] = report.get("risk_score")
    c["risk_level"] = report.get("risk_level")
    c["linked_refs"] = [p["case_id"] for p in report.get("prior_cases", [])]
    c["stage"] = "Ready for review"
    c["processing"] = False


def fail(ref: str, message: str) -> None:
    c = CASES.get(ref)
    if c:
        c["stage"] = "Analysis failed — manual review"
        c["processing"] = False
        c["error"] = message


def evidence_image(ref: str, index: int, store_get) -> Optional[tuple[bytes, str]]:
    c = CASES.get(ref)
    if not c or not c.get("case_id"):
        return None
    sc = store_get(c["case_id"])
    if not sc or index < 0 or index >= len(sc.complaint_images):
        return None
    img = sc.complaint_images[index]
    return base64.standard_b64decode(img["b64"]), img["media"]
