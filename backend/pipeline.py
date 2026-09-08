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

def start_run(case: Case, mode: str) -> str:
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
        except Exception as exc:  # surface everything to the UI
            logger.exception("Run %s failed", run_id)
            RUNS[run_id]["status"] = "error"
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


# ─── Follow-up Q&A (Case AI assistant) ───────────────────────────────

QA_SYSTEM = (
    "You are the investigation assistant of a police financial crime unit, answering "
    "follow-up questions about one specific analyzed case. You have tool access to OSINT "
    "sources and the unit's intelligence repository — use them when the answer needs data "
    "beyond the case file. Answer concisely in markdown (short paragraphs or bullets), "
    "cite identifiers exactly, and say clearly when something is not in the case file or "
    "repository. Never invent case records."
)


async def answer_question(case: Case, question: str) -> dict:
    client = get_client()
    if client is None:
        return {"answer": "Live AI is not configured (no ANTHROPIC_API_KEY set). "
                          "Follow-up Q&A needs live mode.", "tools_used": []}

    context = ["── CASE FILE ──",
               json.dumps(case.complaint, ensure_ascii=False, indent=1)]
    for key, memo in case.memos.items():
        context.append(f"── {key.upper()} MEMO ──\n{memo}")
    if case.report:
        context.append("── FINAL REPORT (JSON) ──\n" +
                       json.dumps(case.report, ensure_ascii=False))

    messages: list[dict] = []
    for turn in case.qa_history[-6:]:
        messages.append({"role": "user", "content": turn["q"]})
        messages.append({"role": "assistant", "content": turn["a"]})
    messages.append({"role": "user", "content":
                     "\n\n".join(context) + f"\n\nQuestion: {question}"})

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
            return {"answer": "The model declined to answer this question.",
                    "tools_used": tools_used}
        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "tool_use" and tool_blocks:
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tb in tool_blocks:
                tools_used.append(tb.name)
                out = run_tool(ALL_TOOLS, tb.name, dict(tb.input))
                results.append({"type": "tool_result", "tool_use_id": tb.id,
                                "content": out})
            messages.append({"role": "user", "content": results})
            rounds += 1
            if rounds >= config.MAX_TOOL_ROUNDS:
                kwargs["tool_choice"] = {"type": "none"}
            continue
        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        case.qa_history.append({"q": question, "a": answer})
        return {"answer": answer, "tools_used": tools_used}
