"""Investigation tools the agents can call.

Two toolsets, both backed by bundled datasets so the demo runs with zero
external dependencies:

- OSINT toolset      -> demo_data/osint.json   (registries, phone/domain/social intel)
- Intelligence toolset -> demo_data/intel_db.json (prior complaints & entity network —
                          the demo stand-in for SAS Visual Investigator)
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from config import DEMO_DIR, TOOL_RESULT_CAP

OSINT = json.loads((DEMO_DIR / "osint.json").read_text(encoding="utf-8"))
INTEL = json.loads((DEMO_DIR / "intel_db.json").read_text(encoding="utf-8"))


def _norm(value: str) -> str:
    """Normalize identifiers: lowercase, alphanumerics only (so 'AE47 0331-...'
    matches 'ae470331...')."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _matches(query: str, blob: str) -> bool:
    q, b = query.lower().strip(), blob.lower()
    if q and q in b:
        return True
    nq = _norm(query)
    return len(nq) >= 4 and nq in _norm(blob)


def _dump(payload: Any) -> str:
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    return text if len(text) <= TOOL_RESULT_CAP else text[:TOOL_RESULT_CAP] + "…[truncated]"


# ─── OSINT tools ─────────────────────────────────────────────────────

def lookup_company_registry(name: str) -> str:
    hits = [c for c in OSINT["company_registry"] if _matches(name, json.dumps(c))]
    return _dump(hits or {"result": "No registry record found", "searched": name})


def lookup_phone(number: str) -> str:
    hits = [p for p in OSINT["phone_intel"] if _matches(number, json.dumps(p))]
    return _dump(hits or {"result": "No intelligence on this number", "searched": number})


def lookup_domain(domain: str) -> str:
    hits = [d for d in OSINT["domains"] if _matches(domain, json.dumps(d))]
    return _dump(hits or {"result": "No WHOIS/hosting intel found", "searched": domain})


def lookup_social(handle: str) -> str:
    hits = [s for s in OSINT["social_profiles"] if _matches(handle, json.dumps(s))]
    return _dump(hits or {"result": "No profile intel found", "searched": handle})


def search_scam_reports(query: str) -> str:
    hits = [r for r in OSINT["scam_reports"] if _matches(query, json.dumps(r))]
    return _dump(hits or {"result": "No public scam reports matched", "searched": query})


# ─── Intelligence repository tools (VI stand-in) ─────────────────────

def search_intelligence(query: str) -> str:
    case_hits = []
    for c in INTEL["cases"]:
        blob = json.dumps(c)
        if _matches(query, blob):
            case_hits.append({
                "case_id": c["case_id"], "filed_date": c["filed_date"],
                "status": c["status"], "victim": c["victim"],
                "amount": c["amount"], "currency": c["currency"],
                "identifiers": c["identifiers"],
            })
    entity_hits = [
        {"id": e["id"], "type": e["type"], "label": e["label"],
         "linked_cases": e.get("linked_cases", [])}
        for e in INTEL["entities"] if _matches(query, json.dumps(e))
    ]
    if not case_hits and not entity_hits:
        return _dump({"result": "No prior cases or known entities matched", "searched": query})
    return _dump({"matched_cases": case_hits, "matched_entities": entity_hits,
                  "hint": "Use get_case_details / expand_entity_network for full records."})


def get_case_details(case_id: str) -> str:
    for c in INTEL["cases"]:
        if c["case_id"].lower() == case_id.lower().strip():
            return _dump(c)
    return _dump({"result": "Case not found", "searched": case_id})


def expand_entity_network(entity_id: str) -> str:
    eid = entity_id.strip().upper()
    entity = next((e for e in INTEL["entities"] if e["id"] == eid), None)
    if entity is None:
        # allow lookup by label fragment
        entity = next((e for e in INTEL["entities"] if _matches(entity_id, e["label"])), None)
    if entity is None:
        # token match: every word of the query appears in the label ("Imran Baig")
        tokens = [t for t in re.split(r"[^a-z0-9]+", entity_id.lower()) if len(t) >= 2]
        if tokens:
            entity = next((e for e in INTEL["entities"]
                           if all(t in e["label"].lower() for t in tokens)), None)
    if entity is None:
        return _dump({"result": "Entity not found", "searched": entity_id})
    links = [l for l in INTEL["links"] if entity["id"] in (l["from"], l["to"])]
    neighbor_ids = {l["from"] for l in links} | {l["to"] for l in links}
    neighbors = [e for e in INTEL["entities"] if e["id"] in neighbor_ids]
    return _dump({"entity": entity, "links": links, "connected_entities": neighbors})


# ─── Tool registry ───────────────────────────────────────────────────

def _tool(name: str, description: str, params: dict[str, str],
          fn: Callable[..., str]) -> dict:
    return {
        "fn": fn,
        "schema": {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v}
                               for k, v in params.items()},
                "required": list(params.keys()),
            },
        },
    }


OSINT_TOOLS = [
    _tool("lookup_company_registry",
          "Look up a company in the UAE trade-license registries (name or license number).",
          {"name": "Company name or license number"}, lookup_company_registry),
    _tool("lookup_phone",
          "Telecom & open-source intelligence on a phone number: registration, SIM type, linked accounts, scam flags.",
          {"number": "Phone number, any format"}, lookup_phone),
    _tool("lookup_domain",
          "WHOIS, hosting and website intelligence for a domain name.",
          {"domain": "Domain, e.g. example.com"}, lookup_domain),
    _tool("lookup_social",
          "Profile intelligence for a social-media handle: creation date, follower anomalies, status.",
          {"handle": "Handle, e.g. @shopname"}, lookup_social),
    _tool("search_scam_reports",
          "Search public scam-report forums and review sites for a name, handle, phone or IBAN fragment.",
          {"query": "Free-text search"}, search_scam_reports),
]

INTEL_TOOLS = [
    _tool("search_intelligence",
          "Search the police financial-crime intelligence repository (prior complaints, known entities) "
          "by any identifier: phone, IBAN, company, handle, website or person name. "
          "ALWAYS search every identifier from the current case, one call per identifier.",
          {"query": "One identifier or name"}, search_intelligence),
    _tool("get_case_details",
          "Retrieve the full record of a prior case by its case id (e.g. CASE-2026-03310).",
          {"case_id": "Case id"}, get_case_details),
    _tool("expand_entity_network",
          "Expand the relationship network around a known entity id (e.g. ENT-ORG-001) or entity name: "
          "returns the entity, its links, and connected entities.",
          {"entity_id": "Entity id or name"}, expand_entity_network),
]

ALL_TOOLS = OSINT_TOOLS + INTEL_TOOLS


def run_tool(toolset: list[dict], name: str, args: dict) -> str:
    for t in toolset:
        if t["schema"]["name"] == name:
            try:
                return t["fn"](**args)
            except TypeError as exc:
                return json.dumps({"error": f"Bad arguments: {exc}"})
    return json.dumps({"error": f"Unknown tool: {name}"})


def schemas(toolset: list[dict]) -> list[dict]:
    return [t["schema"] for t in toolset]
