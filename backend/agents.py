"""Agent definitions for the fraud-complaint analysis pipeline.

Six specialist agents run in sequence. Agents 1-5 produce concise markdown
"findings memos" (streamed to the UI as they complete); each memo is fed to
the downstream agents. Agent 6 (Lead Investigator) synthesizes everything
into a structured case report enforced by a JSON schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from store import Case
from tools import INTEL_TOOLS, OSINT_TOOLS

MEMO_RULES = (
    "Write a findings memo in markdown, at most ~250 words. Start with one "
    "bold verdict line. Include a '**Key identifiers**' bullet list with every "
    "concrete identifier you established (names, aliases, phone numbers, IBANs, "
    "bank names, company names, social handles, websites, order refs, amounts "
    "with currency, dates) — downstream agents rely on that list. Be factual; "
    "flag anything uncertain as uncertain. No preamble, no closing pleasantries."
)


@dataclass
class AgentDef:
    key: str
    name: str
    icon: str
    role: str            # one-line description shown in the UI
    system: str
    tools: list = field(default_factory=list)
    build_user: Callable[[Case, dict], list] = None  # -> content blocks


def _complaint_block(case: Case) -> str:
    c = case.complaint
    victim = c.get("victim", {})
    return (
        f"COMPLAINT {c.get('complaint_ref', '(no ref)')} — filed {c.get('filed_date', '?')} "
        f"via {c.get('channel', '?')}\n"
        f"Category: {c.get('category', '?')}\n"
        f"Victim: {victim.get('name', '?')} — {victim.get('phone', '?')} — "
        f"{victim.get('emirate', '?')}\n"
        f"Claimed loss: {c.get('claimed_loss', '?')} {c.get('currency', 'AED')}\n\n"
        f"Victim statement:\n{c.get('narrative', '(none provided)')}"
    )


def _memo_context(case: Case, keys: list[str]) -> str:
    parts = []
    names = {"intake": "Intake & Triage", "conversation": "Conversation Forensics",
             "financial": "Financial Analysis", "osint": "OSINT",
             "crossref": "Intelligence Cross-Reference"}
    for k in keys:
        if case.memos.get(k):
            parts.append(f"── Memo from {names.get(k, k)} agent ──\n{case.memos[k]}")
    return "\n\n".join(parts)


# ─── 1. Intake & Triage ──────────────────────────────────────────────

def _intake_user(case: Case, ctx: dict) -> list:
    inventory = []
    if case.complaint_images:
        inventory.append(f"- Complaint evidence: {len(case.complaint_images)} screenshot image(s) "
                         "of the conversation with the seller")
    if case.complaint_text:
        inventory.append("- Complaint evidence: conversation transcript (text)")
    for s in case.statements:
        inventory.append(f"- Financial statement: {s['name']}")
    inventory.append("- OSINT collection: will run automatically")
    inventory.append("- Complaint-history cross-reference: will run automatically")
    return [{"type": "text", "text":
             _complaint_block(case) + "\n\nEvidence inventory:\n" + "\n".join(inventory) +
             "\n\nTriage this complaint."}]


INTAKE = AgentDef(
    key="intake", name="Intake & Triage Agent", icon="📋",
    role="Classifies the complaint, profiles the victim's claims, sets analysis priorities",
    system=(
        "You are the intake and triage agent of a police financial crime unit. "
        "Given a citizen fraud complaint and an evidence inventory, you: classify the fraud "
        "typology precisely, extract the claimed facts (who/what/when/how much), assess "
        "completeness of the evidence, and state what each downstream specialist "
        "(conversation forensics, financial analysis, OSINT, intelligence cross-reference) "
        "should focus on. " + MEMO_RULES),
    build_user=_intake_user,
)


# ─── 2. Conversation Forensics ───────────────────────────────────────

def _conversation_user(case: Case, ctx: dict) -> list:
    blocks: list = []
    intro = _memo_context(case, ["intake"]) + "\n\n"
    for img in case.complaint_images:
        blocks.append({"type": "image",
                       "source": {"type": "base64",
                                  "media_type": img["media"],
                                  "data": img["b64"]}})
    if case.complaint_images:
        blocks.append({"type": "text", "text": intro +
                       f"The {len(case.complaint_images)} image(s) above are the complaint "
                       "evidence — screenshots of the conversation with the seller, in order. "
                       "Read them carefully, transcribe the key exchanges, then analyze."})
    if case.complaint_text:
        blocks.append({"type": "text", "text":
                       (intro if not case.complaint_images else "") +
                       "── Additional conversation evidence (text) ──\n" +
                       case.complaint_text + "\n\nAnalyze this conversation."})
    return blocks


CONVERSATION = AgentDef(
    key="conversation", name="Conversation Forensics Agent", icon="💬",
    role="Reconstructs the exchange, extracts identifiers, detects manipulation patterns",
    system=(
        "You are a conversation forensics specialist in a police financial crime unit. "
        "From chat evidence you extract: participants and aliases, every identifier "
        "(phones, handles, IBANs, banks, companies, order refs, websites), the sequence of "
        "promises and payments with dates, and the social-engineering techniques used "
        "(urgency, scarcity, trust signals, advance-fee escalation, ghosting). Name each "
        "technique explicitly — investigators use this to establish intent. " + MEMO_RULES),
    build_user=_conversation_user,
)


# ─── 3. Financial Analysis ───────────────────────────────────────────

def _financial_user(case: Case, ctx: dict) -> list:
    if case.statements:
        stmts = "\n\n".join(
            f"── Statement {i}: {s['name']} (text extracted) ──\n{s['text']}"
            for i, s in enumerate(case.statements, 1))
    else:
        stmts = "(no financial statements provided)"
    return [{"type": "text", "text":
             _memo_context(case, ["intake", "conversation"]) +
             "\n\n" + stmts + "\n\nAnalyze the financial evidence."}]


FINANCIAL = AgentDef(
    key="financial", name="Financial Analysis Agent", icon="🏦",
    role="Parses the bank statement, isolates fraud transfers, quantifies the loss",
    system=(
        "You are a financial analysis specialist in a police financial crime unit. "
        "From bank-statement evidence you: identify every transaction connected to the "
        "complaint (match beneficiary names/IBANs/references against the conversation "
        "evidence), verify claimed amounts and dates, compute the total confirmed loss, "
        "profile the victim's normal spending as contrast, and describe the beneficiary "
        "account details precisely for a freeze/disclosure request. " + MEMO_RULES),
    build_user=_financial_user,
)


# ─── 4. OSINT ────────────────────────────────────────────────────────

def _osint_user(case: Case, ctx: dict) -> list:
    return [{"type": "text", "text":
             _memo_context(case, ["intake", "conversation", "financial"]) +
             "\n\nRun open-source intelligence collection on the identifiers above: the "
             "seller company, phone number, social handles and any websites. Check the "
             "company registry, phone intel, domain records, social profiles and public "
             "scam reports. Then write your memo."}]


OSINT_AGENT = AgentDef(
    key="osint", name="OSINT Agent", icon="🌐",
    role="Queries registries, phone/domain intel, social profiles and scam databases",
    system=(
        "You are an OSINT specialist in a police financial crime unit with tool access to "
        "company registries, telecom intelligence, domain records, social-media analysis and "
        "public scam-report databases. Systematically look up EVERY identifier the earlier "
        "memos established (company names, phone numbers, handles, domains) — one tool call "
        "per identifier, using multiple tools where relevant. Then assess: is the seller a "
        "legitimate business or a manufactured persona? Cite which source each finding came "
        "from. " + MEMO_RULES),
    tools=OSINT_TOOLS,
    build_user=_osint_user,
)


# ─── 5. Intelligence Cross-Reference (the VI moment) ─────────────────

def _crossref_user(case: Case, ctx: dict) -> list:
    return [{"type": "text", "text":
             _memo_context(case, ["intake", "conversation", "financial", "osint"]) +
             "\n\nCross-reference this case against the intelligence repository. Search every "
             "identifier (IBAN, phone, company, handles, person names, websites). For each "
             "prior case that matches, pull the full details and note exactly which "
             "identifiers link it to the current complaint. Expand the entity network around "
             "the strongest hub entities. Then write your memo, including a clear statement "
             "of whether this is a first offence or part of a series."}]


CROSSREF = AgentDef(
    key="crossref", name="Intelligence Cross-Reference Agent", icon="🕸️",
    role="Searches prior complaints & the entity network — is this a first offence or a series?",
    system=(
        "You are the intelligence cross-reference specialist of a police financial crime "
        "unit, with tool access to the unit's intelligence repository of prior complaints "
        "and resolved entities (in production this is SAS Visual Investigator). Your job: "
        "establish whether the identifiers in the current case appear in prior complaints. "
        "Search EVERY identifier separately. When cases match, retrieve full details and "
        "expand the entity network to find the common controller. Quantify the pattern: "
        "number of linked complaints, combined losses, shared infrastructure, modus "
        "operandi. " + MEMO_RULES),
    tools=INTEL_TOOLS,
    build_user=_crossref_user,
)


# ─── 6. Lead Investigator (structured report) ────────────────────────

def _lead_user(case: Case, ctx: dict) -> list:
    return [{"type": "text", "text":
             _complaint_block(case) + "\n\n" +
             _memo_context(case, ["intake", "conversation", "financial", "osint", "crossref"]) +
             "\n\nSynthesize the full investigation report. Rules:\n"
             "- entities: one entry per real-world entity, reuse ids like ENT-ORG-001 where "
             "the memos mention them; give the victim and current case entities new ids "
             "(e.g. ENT-VIC-000, ENT-SOC-000).\n"
             "- timeline: merge conversation, financial, OSINT and prior-case dates into one "
             "chronological view (ISO dates).\n"
             "- financial_flow: every confirmed victim->suspect transfer in this case AND "
             "prior linked cases, plus known onward movement (cash-out, exchange).\n"
             "- prior_cases: every linked complaint with the exact identifiers matched on.\n"
             "- recommended_actions: concrete police actions in priority order (account "
             "freeze, bank disclosure, telecom subpoena, platform preservation requests, "
             "case consolidation, suspect identification steps, victim communication).\n"
             "- vi_case_summary: one short paragraph describing the consolidated case that "
             "should be opened in the unit's network-investigation platform in the next step "
             "(entities, links, prior complaints to merge).\n"
             "- executive_summary: ~150 words, written for a unit commander."}]


LEAD = AgentDef(
    key="lead", name="Lead Investigator Agent", icon="🎖️",
    role="Synthesizes all findings into the case report, network map and action plan",
    system=(
        "You are the lead investigator of a police financial crime unit. You receive the "
        "memos of five specialist agents and produce the consolidated investigation report "
        "as structured JSON following the enforced schema. Be precise with identifiers, "
        "amounts and dates; every claim must trace back to a memo. Risk score reflects: "
        "confirmed loss, serial pattern, organised infrastructure, and likelihood of "
        "continued offending."),
    build_user=_lead_user,
)

PIPELINE: list[AgentDef] = [INTAKE, CONVERSATION, FINANCIAL, OSINT_AGENT, CROSSREF, LEAD]


# ─── Report schema (enforced via output_config.format) ───────────────

def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required if required is not None else list(props.keys()),
            "additionalProperties": False}


def _arr(item: dict) -> dict:
    return {"type": "array", "items": item}


_S = {"type": "string"}
_N = {"type": "number"}
_B = {"type": "boolean"}

ENTITY_TYPES = ["person", "organization", "account", "phone", "social",
                "website", "case", "location", "other"]

REPORT_SCHEMA = _obj({
    "case_ref": _S,
    "classification": _S,
    "typology": _S,
    "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
    "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "executive_summary": _S,
    "key_findings": _arr(_obj({
        "title": _S, "detail": _S,
        "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
        "source": _S})),
    "entities": _arr(_obj({
        "id": _S, "label": _S,
        "type": {"type": "string", "enum": ENTITY_TYPES},
        "role": _S, "flagged": _B})),
    "timeline": _arr(_obj({"date": _S, "event": _S, "source": _S})),
    "financial_flow": _arr(_obj({
        "date": _S, "from": _S, "to": _S, "amount": _N,
        "currency": _S, "note": _S})),
    "prior_cases": _arr(_obj({
        "case_id": _S, "filed_date": _S, "victim": _S, "amount": _N,
        "currency": _S, "matched_on": _arr(_S), "summary": _S, "status": _S})),
    "recommended_actions": _arr(_obj({
        "action": _S,
        "priority": {"type": "string", "enum": ["immediate", "high", "routine"]},
        "rationale": _S})),
    "vi_case_summary": _S,
})
