"""Arabic versions of case files.

Two sources, in order of preference:
1. Bundled translations (demo_data/cases.ar.json for seeded cases,
   demo_data/replay.ar.json for the recorded run) — attached by the registry.
2. On-demand machine translation of the English case file, schema-enforced so
   the Arabic file has exactly the same structure as the English one. Runs in
   the background; the UI polls the case until `report_ar` appears.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import config
import registry
from agents import REPORT_SCHEMA

logger = logging.getLogger("translate")

_tasks: dict[str, asyncio.Task] = {}

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {"report": REPORT_SCHEMA, "complaint_text": {"type": "string"}},
    "required": ["report", "complaint_text"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the official translator of a UAE police financial crime unit. Translate the "
    "JSON case file you receive from English into formal Modern Standard Arabic in the "
    "register of UAE government and police case files.\n\n"
    "Rules:\n"
    "- Return the same JSON structure with every English string value translated.\n"
    "- Keep unchanged: numbers, amounts, ISO dates, case references (FC-2026-…), "
    "transaction references, IBANs, account numbers, phone numbers, email addresses, "
    "domains, social-media handles, entity ids, and the literal prefix 'THIS CASE — ' in "
    "financial_flow notes (translate only the text after it).\n"
    "- Keep enumerated values exactly as they are: risk_level, confidence, evidence status, "
    "assessment, severity, priority, entity type, flagged, currency.\n"
    "- Write personal names in Arabic script (Ahmed Hassan → أحمد حسن); transliterate "
    "company and product names; 'Example Bank' → 'إكزامبل بنك'; write amounts as "
    "'12,500 درهم'; 'KYC' → «اعرف عميلك»; 'MLRO' → 'مسؤول الإبلاغ عن غسل الأموال'.\n"
    "- Timeframes: Today → اليوم, 48 hours → 48 ساعة, This week → هذا الأسبوع, Routine → روتيني.\n"
    "- Be precise and literal; do not add, drop or soften any finding."
)


async def translate_entry(entry: dict) -> bool:
    from pipeline import get_client  # local import: pipeline imports this module lazily

    client = get_client()
    if client is None or not entry.get("report"):
        return False
    payload = {"report": entry["report"], "complaint_text": entry.get("complaint_text") or ""}
    entry["translation"] = "pending"
    try:
        resp = await client.messages.create(
            model=config.MODEL,
            max_tokens=config.REPORT_MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": "Translate this case file:\n\n"
                       + json.dumps(payload, ensure_ascii=False)}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": TRANSLATE_SCHEMA}},
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        if not text:
            raise RuntimeError(f"empty translation (stop_reason={resp.stop_reason})")
        data = json.loads(text)
        report = data["report"]
        report["case_ref"] = entry["ref"]
        entry["report_ar"] = report
        if data.get("complaint_text"):
            entry["complaint_text_ar"] = data["complaint_text"]
        entry["translation"] = "ready"
        logger.info("Arabic case file ready for %s", entry["ref"])
        return True
    except Exception as exc:  # keep the English file; the UI falls back to it
        logger.exception("Translation of %s failed", entry.get("ref"))
        entry["translation"] = "failed"
        entry["translation_error"] = f"{type(exc).__name__}: {exc}"
        return False


def status(ref: str) -> str:
    entry = registry.CASES.get(ref)
    if not entry or not entry.get("report"):
        return "none"
    if entry.get("report_ar"):
        return "ready"
    task = _tasks.get(ref)
    if task and not task.done():
        return "pending"
    if not config.llm_configured():
        return "unavailable"
    return entry.get("translation") or "idle"


def schedule(ref: str) -> str:
    """Start a background translation if one is needed; returns the status."""
    st = status(ref)
    if st != "idle" and st != "failed":
        return st
    entry = registry.CASES[ref]
    _tasks[ref] = asyncio.get_running_loop().create_task(translate_entry(entry))
    return "pending"


async def prewarm(concurrency: int = 2) -> None:
    """Translate every seeded case that has no bundled Arabic file (startup)."""
    if not config.llm_configured() or os.getenv("PREWARM_TRANSLATIONS", "1") == "0":
        return
    sem = asyncio.Semaphore(concurrency)
    refs = [r for r, c in registry.CASES.items() if c.get("report") and not c.get("report_ar")]

    async def one(ref: str) -> None:
        async with sem:
            await translate_entry(registry.CASES[ref])

    if refs:
        logger.info("Pre-translating %d seeded case files", len(refs))
        await asyncio.gather(*(one(r) for r in refs))
