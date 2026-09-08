"""Pipeline orchestration: runs the six agents in sequence, streaming every
step (agent starts, tool calls, memos, final report) as SSE events.

Two modes:
- live:   real agentic runs against the Anthropic API
- replay: streams a bundled recorded run (demo_data/replay.json) so the demo
          works with no API key / no connectivity. Clearly labelled in the UI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Optional

from anthropic import AsyncAnthropic

import config
import registry
from agents import PIPELINE, REPORT_SCHEMA, AgentDef
from store import RUNS, Case
from tools import ALL_TOOLS, run_tool, schemas

logger = logging.getLogger("pipeline")

_client: Optional[AsyncAnthropic] = None


def get_client() -> Optional[AsyncAnthropic]:
    global _client
    if _client is None and config.ANTHROPIC_API_KEY:
        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def resolve_mode(requested: str) -> str:
    if requested in ("live", "replay"):
        return requested
    if config.DEFAULT_MODE in ("live", "replay"):
        return config.DEFAULT_MODE
    return "live" if config.llm_configured() else "replay"


# ─── Live agent execution ────────────────────────────────────────────

async def _run_agent(agent: AgentDef, case: Case, emit) -> str:
    client = get_client()
    messages: list[dict] = [{"role": "user", "content": agent.build_user(case, {})}]
    kwargs: dict[str, Any] = {
        "model": config.MODEL,
        "system": agent.system,
        "max_tokens": config.MAX_TOKENS,
        "output_config": {"effort": config.LLM_EFFORT},
    }
    if agent.key == "lead":
        kwargs["max_tokens"] = config.REPORT_MAX_TOKENS
        kwargs["output_config"] = {
            "effort": config.LLM_EFFORT,
            "format": {"type": "json_schema", "schema": REPORT_SCHEMA},
        }
    if agent.tools:
        kwargs["tools"] = schemas(agent.tools)

    rounds = 0
    while True:
        resp = await client.messages.create(messages=messages, **kwargs)

        if resp.stop_reason == "refusal":
            detail = getattr(resp, "stop_details", None)
            raise RuntimeError(
                f"The model declined this request ({getattr(detail, 'explanation', 'no detail')}).")

        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "tool_use" and tool_blocks:
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tb in tool_blocks:
                await emit({"type": "tool_call", "agent": agent.key,
                            "tool": tb.name, "args": dict(tb.input)})
                out = run_tool(agent.tools, tb.name, dict(tb.input))
                await emit({"type": "tool_result", "agent": agent.key,
                            "tool": tb.name, "summary": out[:280]})
                results.append({"type": "tool_result", "tool_use_id": tb.id,
                                "content": out})
            messages.append({"role": "user", "content": results})
            rounds += 1
            if rounds >= config.MAX_TOOL_ROUNDS:
                # Enough investigation — force the memo on the next turn.
                kwargs["tool_choice"] = {"type": "none"}
            continue

        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason == "max_tokens":
            logger.warning("Agent %s hit max_tokens; using partial output", agent.key)
        return text


async def _run_live(case: Case, emit) -> None:
    for agent in PIPELINE:
        await emit({"type": "agent_start", "agent": agent.key})
        started = time.monotonic()
        text = await _run_agent(agent, case, emit)
        elapsed = round(time.monotonic() - started, 1)
        if agent.key == "lead":
            report = json.loads(text)  # guaranteed valid by output_config.format
            case.report = report
            await emit({"type": "agent_done", "agent": agent.key, "elapsed": elapsed})
            await emit({"type": "report", "report": report})
        else:
            case.memos[agent.key] = text
            await emit({"type": "agent_memo", "agent": agent.key, "memo": text})
            await emit({"type": "agent_done", "agent": agent.key, "elapsed": elapsed})


# ─── Replay (simulation) execution ───────────────────────────────────

async def _run_replay(case: Case, emit, speed: float = 1.0) -> None:
    data = json.loads((config.DEMO_DIR / "replay.json").read_text(encoding="utf-8"))
    for item in data["events"]:
        await asyncio.sleep(min(float(item.get("delay", 0.5)), 6.0) * speed)
        event = item["event"]
        if event.get("type") == "agent_memo":
            case.memos[event["agent"]] = event["memo"]
        if event.get("type") == "report":
            case.report = event["report"]
        await emit(event)


# ─── Run management + SSE ────────────────────────────────────────────

def start_run(case: Case, mode: str, ref: Optional[str] = None) -> str:
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    queue: asyncio.Queue = asyncio.Queue()
    RUNS[run_id] = {"queue": queue, "case_id": case.case_id, "mode": mode,
                    "status": "running"}

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def runner() -> None:
        try:
            await emit({"type": "pipeline_start", "mode": mode,
                        "agents": [{"key": a.key, "name": a.name, "icon": a.icon,
                                    "role": a.role} for a in PIPELINE]})
            if mode == "live":
                await _run_live(case, emit)
            else:
                await _run_replay(case, emit)
            await emit({"type": "done"})
            RUNS[run_id]["status"] = "done"
            if ref and case.report:
                registry.complete(ref, case.report, case.memos)
        except Exception as exc:  # surface everything to the UI
            logger.exception("Run %s failed", run_id)
            RUNS[run_id]["status"] = "error"
            if ref:
                registry.fail(ref, str(exc))
            await emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            await emit({"type": "done"})
        finally:
            await queue.put(None)

    # Must be called from within the event loop (async endpoint).
    asyncio.get_running_loop().create_task(runner())
    return run_id


async def event_stream(run_id: str) -> AsyncGenerator[str, None]:
    run = RUNS.get(run_id)
    if not run:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown run id'})}\n\n"
        return
    queue: asyncio.Queue = run["queue"]
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=15.0)
        except asyncio.TimeoutError:
            yield ": keep-alive\n\n"
            continue
        if event is None:
            break
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ─── Case assistant (investigator Q&A) ───────────────────────────────

QA_SYSTEM = (
    "You are the case assistant of a police financial crime unit, answering an "
    "investigator's questions about one specific case file. You have tool access to OSINT "
    "sources and the unit's complaint-history repository — use them when the answer needs "
    "data beyond the file. When asked to draft a request (bank disclosure, freeze, telecom, "
    "platform preservation), produce a complete, formal, ready-to-send draft with the exact "
    "identifiers from the file (account numbers, IBANs, dates, references). Otherwise answer "
    "concisely in markdown with short paragraphs or bullets. Never invent records; say "
    "clearly when something is not in the file."
)


def _accounts_from(report: dict) -> list[str]:
    accts = []
    for e in report.get("entities", []):
        if e.get("type") == "account":
            accts.append(e["label"])
    if not accts:
        for kf in report.get("key_facts", []):
            if "account" in kf["label"].lower() or "beneficiary" in kf["label"].lower():
                accts.append(kf["value"])
    return accts


def offline_answer(entry: dict, question: str) -> str:
    """Deterministic fallback when no LLM is configured: answers and drafts built
    from the case file itself."""
    q = question.lower()
    rep = entry.get("report") or {}
    ref = entry["ref"]
    accts = _accounts_from(rep)
    acct_lines = "\n".join(f"- {a}" for a in accts) or "- (beneficiary account per case file)"
    today = registry.TODAY
    if any(k in q for k in ("freeze", "hold", "block")):
        return (f"**Draft — request for temporary hold on beneficiary accounts**\n\n"
                f"To: Compliance / MLRO, beneficiary bank\nRef: {ref} — {rep.get('classification','fraud complaint')}\nDate: {today}\n\n"
                f"The Financial Crime Unit is investigating a complaint of {rep.get('classification','fraud').lower()} "
                f"in which the complainant transferred funds to the following account(s):\n{acct_lines}\n\n"
                "Please place a temporary no-debit hold on the above account(s) pending our formal disclosure request, "
                "retain all funds currently held, and confirm the current balance and any pending outward instructions "
                "by return.\n\nInvestigating officer, Financial Crime Unit")
    if any(k in q for k in ("statement", "disclosure", "kyc", "bank record", "6 month", "six month")):
        return (f"**Draft — disclosure request: 6-month statements and KYC**\n\n"
                f"To: Compliance / MLRO, beneficiary bank\nRef: {ref}\nDate: {today}\n\n"
                f"In connection with the above investigation, please provide for each of the following account(s):\n{acct_lines}\n\n"
                "1. Full statements for the six months preceding this request, including counterparties and references.\n"
                "2. The KYC file: identity document, registered address, contact numbers, account-opening form and date.\n"
                "3. Details of all outward transfers, cash withdrawals (with ATM locations) and virtual-asset exchange "
                "transfers since the first complainant credit.\n4. Linked accounts, cards and devices used for online banking.\n\n"
                "Please treat this request as urgent; funds have historically left these accounts within 72 hours.\n\n"
                "Investigating officer, Financial Crime Unit")
    if any(k in q for k in ("telecom", "phone", "sim", "subscriber")):
        phones = [e["label"] for e in rep.get("entities", []) if e.get("type") == "phone"]
        return (f"**Draft — subscriber data request**\n\nTo: Law-enforcement liaison, telecom operator\nRef: {ref}\n\n"
                f"Please provide subscriber registration documents, activation date, IMEI history and cell-site records "
                f"for: {', '.join(phones) or 'the seller number on file'} (period: activation to date).\n\nInvestigating officer, Financial Crime Unit")
    if any(k in q for k in ("what happened", "summar", "narrative", "explain the case", "brief")):
        return rep.get("narrative") or entry.get("complaint_text") or "No narrative is available for this case yet."
    if any(k in q for k in ("link", "other case", "connected", "network", "prior", "before", "same")):
        pcs = rep.get("prior_cases") or []
        if not pcs:
            return "No prior occurrence of this case's identifiers was found in complaint history."
        lines = [f"- **{p['case_id']}** ({p['filed_date']}, {p['victim']}, AED {p['amount']:,.0f}) — matched on: {', '.join(p['matched_on'])}" for p in pcs]
        return (rep.get("investigation_summary", "") + "\n\n" + "\n".join(lines)).strip()
    if any(k in q for k in ("recommend", "next", "action", "what should", "do first")):
        acts = rep.get("recommended_actions") or []
        return "\n".join(f"{i}. **{a['action']}** — {a['addressee']} · {a['timeframe']}" for i, a in enumerate(acts, 1)) or "No recommendations recorded yet."
    if any(k in q for k in ("evidence", "screenshot", "receipt", "reconcil")):
        ev = rep.get("evidence_assessment") or []
        return "\n".join(f"- **{e['item']}** — {e['finding']} ({e['status']})" for e in ev) or "Evidence assessment is not available yet."
    return ((rep.get("investigation_summary") or entry.get("complaint_text") or "") +
            "\n\nI can draft the bank disclosure or freeze request, the telecom request, summarise what happened, "
            "or list the linked cases and recommended actions.").strip()


async def answer_question(entry: dict, question: str, store_case: Optional[Case]) -> dict:
    client = get_client()
    if client is None:
        answer = offline_answer(entry, question)
        entry.setdefault("qa_history", []).append({"q": question, "a": answer})
        return {"answer": answer, "tools_used": []}

    context = [f"── CASE FILE {entry['ref']} ──",
               json.dumps({k: entry.get(k) for k in ("ref", "filed", "complainant", "type", "subtype",
                                                      "amount", "status", "stage", "officer", "evidence")},
                          ensure_ascii=False),
               "── COMPLAINANT STATEMENT ──\n" + (entry.get("complaint_text") or "")]
    for key, memo in (entry.get("memos") or {}).items():
        context.append(f"── {key.upper()} MEMO ──\n{memo}")
    if entry.get("report"):
        context.append("── CASE FILE (JSON) ──\n" + json.dumps(entry["report"], ensure_ascii=False))

    messages: list[dict] = []
    for turn in (entry.get("qa_history") or [])[-6:]:
        messages.append({"role": "user", "content": turn["q"]})
        messages.append({"role": "assistant", "content": turn["a"]})
    messages.append({"role": "user", "content": "\n\n".join(context) + f"\n\nQuestion: {question}"})

    tools_used: list[str] = []
    rounds = 0
    kwargs: dict[str, Any] = {
        "model": config.MODEL, "system": QA_SYSTEM,
        "max_tokens": config.MAX_TOKENS,
        "output_config": {"effort": config.LLM_EFFORT},
        "tools": schemas(ALL_TOOLS),
    }
    while True:
        resp = await client.messages.create(messages=messages, **kwargs)
        if resp.stop_reason == "refusal":
            return {"answer": "The assistant declined to answer this question.", "tools_used": tools_used}
        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "tool_use" and tool_blocks:
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tb in tool_blocks:
                tools_used.append(tb.name)
                out = run_tool(ALL_TOOLS, tb.name, dict(tb.input))
                results.append({"type": "tool_result", "tool_use_id": tb.id, "content": out})
            messages.append({"role": "user", "content": results})
            rounds += 1
            if rounds >= config.MAX_TOOL_ROUNDS:
                kwargs["tool_choice"] = {"type": "none"}
            continue
        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        entry.setdefault("qa_history", []).append({"q": question, "a": answer})
        return {"answer": answer, "tools_used": tools_used}
