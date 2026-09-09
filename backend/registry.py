"""Case registry: the investigator's queue. Seeded from demo_data/cases.json,
extended in memory by citizen submissions (demo scope: no persistence)."""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
from typing import Optional

from config import DEMO_DIR

_data = json.loads((DEMO_DIR / "cases.json").read_text(encoding="utf-8"))
CASES: dict[str, dict] = {c["ref"]: c for c in _data["cases"]}
_seq: int = int(_data.get("next_sequence", 231))

# ─── Clock: the unit's local time, not the container's UTC ───────────
TZ_NAME = os.getenv("DEMO_TZ", "Asia/Dubai")


def _tz() -> dt.tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:  # tzdata missing → fixed +04:00
        return dt.timezone(dt.timedelta(hours=4))


def now() -> dt.datetime:
    return dt.datetime.now(_tz())


def today() -> str:
    """ISO date. DEMO_TODAY pins it for rehearsals; otherwise the real local date."""
    return os.getenv("DEMO_TODAY") or now().date().isoformat()


_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def now_stamp(client_stamp: Optional[str] = None) -> str:
    """Filing timestamp. The browser's own local time wins when supplied (so the
    'Filed' column matches the clock on the presenter's screen wherever they are)."""
    if client_stamp and _STAMP_RE.match(client_stamp):
        return client_stamp
    return f"{today()}T{now().strftime('%H:%M')}"


_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def fill_dates(text: str, filed: Optional[str] = None) -> str:
    """Replace filing-date placeholders in bundled content with the real date."""
    if "{{" not in text:
        return text
    d = dt.date.fromisoformat((filed or today())[:10])
    long_ = f"{d.day} {_MONTHS[d.month - 1]}"
    long_ar = f"{d.day} {_MONTHS_AR[d.month - 1]}"
    return (text.replace("{{FILED_DATE}}", d.isoformat())
                .replace("{{FILED_LONG_AR}}", long_ar)
                .replace("{{FILED_SHORT_AR}}", long_ar)
                .replace("{{FILED_LONG}}", long_)
                .replace("{{FILED_SHORT}}", f"{d.day} {_MONTHS[d.month - 1][:3]}")
                .replace("{{FILED_DMY}}", d.strftime("%d/%m/%Y")))


# ─── Bundled Arabic case files ───────────────────────────────────────
_ar_path = DEMO_DIR / "cases.ar.json"
if _ar_path.exists():
    for _ref, _tr in json.loads(_ar_path.read_text(encoding="utf-8")).items():
        if _ref in CASES:
            CASES[_ref]["report_ar"] = _tr.get("report")
            CASES[_ref]["complaint_text_ar"] = _tr.get("complaint_text")


def attach_bundled_ar(ref: str, filed: Optional[str] = None) -> None:
    """Attach the recorded run's Arabic case file and memos to a case entry."""
    c = CASES.get(ref)
    p = DEMO_DIR / "replay.ar.json"
    if not c or not p.exists():
        return
    raw = fill_dates(p.read_text(encoding="utf-8"), filed or c.get("filed"))
    raw = raw.replace("FC-2026-0231", ref)
    data = json.loads(raw)
    report = dict(data.get("report") or {})
    if report:
        report["case_ref"] = ref
        c["report_ar"] = report
    c["memos_ar"] = dict(data.get("memos") or {})
    c["translation"] = "ready"


_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


_METHOD_AR = {"Bank transfer": "تحويل مصرفي", "Card payment": "بطاقة", "Cash": "نقداً",
              "Cryptocurrency": "عملة رقمية", "Other": "أخرى"}


def _payment_line(payment: dict, lang: str) -> str:
    p = payment or {}
    if lang == "ar":
        parts = [p.get("beneficiary_name") and f"اسم المستفيد: {p['beneficiary_name']}",
                 p.get("account") and f"الحساب: {p['account']}",
                 p.get("iban") and f"الآيبان: {p['iban']}",
                 p.get("date") and f"تاريخ الدفع: {p['date']}",
                 p.get("method") and f"طريقة الدفع: {_METHOD_AR.get(p['method'], p['method'])}"]
        parts = [x for x in parts if x]
        return "بيانات الدفع كما قدّمها المبلّغ — " + " · ".join(parts) + "." if parts else ""
    parts = [p.get("beneficiary_name") and f"Beneficiary name: {p['beneficiary_name']}",
             p.get("account") and f"Account: {p['account']}",
             p.get("iban") and f"IBAN: {p['iban']}",
             p.get("date") and f"Date of payment: {p['date']}",
             p.get("method") and f"Payment method: {p['method']}"]
    parts = [x for x in parts if x]
    return "Payment details provided by the complainant — " + " · ".join(parts) + "." if parts else ""


def _demo_complaint() -> dict:
    try:
        return json.loads((DEMO_DIR / "complaint.json").read_text(encoding="utf-8"))
    except OSError:
        return {}


def _complainant_name(store_case, victim: dict) -> str:
    """Queue name. The demo complainant is bundled in both scripts; the English
    form is stored and the interface renders it in the active language."""
    name = (victim.get("name") or "").strip()
    if getattr(store_case, "is_demo", False):
        v = _demo_complaint().get("victim") or {}
        if name in ((v.get("name") or "").strip(), (v.get("name_ar") or "").strip()) and v.get("name"):
            return v["name"]
    return name or "Unnamed complainant"


def complaint_texts(store_case, complaint: dict) -> tuple[str, Optional[str], str]:
    """(complaint_text, complaint_text_ar, lang) for a submission. The demo
    narrative is bundled in both languages; anything else is kept as typed."""
    narrative = (complaint.get("narrative") or "").strip()
    lang = complaint.get("lang") or ("ar" if _ARABIC_RE.search(narrative) else "en")
    payment = complaint.get("payment") or {}
    suffix_en, suffix_ar = _payment_line(payment, "en"), _payment_line(payment, "ar")

    def join(body: str, suffix: str) -> str:
        return body + ("\n\n" + suffix if suffix else "")

    if getattr(store_case, "is_demo", False):
        bundled = _demo_complaint()
        en, ar = (bundled.get("narrative") or "").strip(), (bundled.get("narrative_ar") or "").strip()
        if narrative in (en, ar) and en and ar:
            return join(en, suffix_en), join(ar, suffix_ar), lang
    text = join(narrative, suffix_ar if lang == "ar" else suffix_en)
    return text, (text if lang == "ar" else None), lang

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


def days_open(filed: str) -> int:
    try:
        d = dt.date.fromisoformat(filed[:10])
        return max(0, (dt.date.fromisoformat(today()) - d).days)
    except ValueError:
        return 0


def summary_row(c: dict) -> dict:
    """Queue row: everything except the heavy report body."""
    heavy = ("report", "memos", "complaint_text", "qa_history", "report_ar", "memos_ar", "complaint_text_ar")
    return {k: v for k, v in c.items() if k not in heavy} | {
        "has_ar": bool(c.get("report_ar")),
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


def register_submission(store_case, complaint: dict, run_id: str, mode: str,
                        filed: Optional[str] = None) -> dict:
    global _seq
    ref = f"FC-2026-{_seq:04d}"
    _seq += 1
    victim = complaint.get("victim", {})
    text, text_ar, lang = complaint_texts(store_case, complaint)
    complaint["narrative"] = text  # what the analysts read: narrative + payment details
    evidence = [i["name"] for i in store_case.complaint_images]
    if store_case.complaint_text:
        evidence.append("Conversation transcript (text)")
    evidence += [s["name"] for s in store_case.statements]
    entry = {
        "ref": ref,
        "filed": now_stamp(filed),
        "complainant": _complainant_name(store_case, victim),
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
        "complaint_text": text,
        "complaint_text_ar": text_ar,
        "lang": lang,
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
    complaint["filed_date"] = entry["filed"][:10]
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


def note_error(ref: str, message: str) -> None:
    """Record a live-analysis error on the entry (diagnostics only; the queue
    keeps showing the case as analysed once the fallback run completes)."""
    c = CASES.get(ref)
    if c:
        c["error"] = message


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
