"""Thin wrapper over the Anthropic SDK for JSON-schema constrained calls.

Every pipeline step that needs the model goes through `LLM.json()`: a system prompt, a
list of user content blocks (text, PDF document, images), and a JSON schema. The response
is validated JSON (structured outputs), parsed and returned as a dict.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

import config

log = logging.getLogger("misa.llm")


class LLMUnavailable(RuntimeError):
    pass


class LLMRefused(RuntimeError):
    pass


def pdf_block(path: Path) -> dict:
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


# Result of the last key check: {"ok": bool|None, "error": str, "checkedAt": float, "keyHint": str}
KEY_STATUS: dict = {"ok": None, "error": "", "checkedAt": None, "keyHint": config.key_hint(), "models": []}


def check_key() -> dict:
    """Ask the API whether the configured key is accepted (a models listing: no tokens spent)."""
    KEY_STATUS["keyHint"] = config.key_hint()
    if not config.llm_configured():
        KEY_STATUS.update({"ok": None, "error": "ANTHROPIC_API_KEY is not set", "checkedAt": time.time(), "models": []})
        return KEY_STATUS
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=1, timeout=30)
        page = client.models.list(limit=20)
        ids = [m.id for m in page.data]
        err = ""
        if config.MODEL not in ids and not any(i.startswith(config.MODEL) for i in ids):
            err = f"the key works but model '{config.MODEL}' is not available to it"
        KEY_STATUS.update({"ok": not err, "error": err, "checkedAt": time.time(), "models": ids})
    except anthropic.AuthenticationError as e:
        KEY_STATUS.update({"ok": False, "error": f"the API rejected the key (401 invalid x-api-key). Key seen by the server: {config.key_hint()}", "checkedAt": time.time(), "models": []})
    except anthropic.PermissionDeniedError as e:
        KEY_STATUS.update({"ok": False, "error": f"the API refused the key (403): {str(e)[:160]}", "checkedAt": time.time(), "models": []})
    except Exception as e:
        KEY_STATUS.update({"ok": False, "error": f"could not reach the API: {type(e).__name__}: {str(e)[:160]}", "checkedAt": time.time(), "models": []})
    log.info("key check: %s %s", "ok" if KEY_STATUS["ok"] else "FAILED", KEY_STATUS["error"])
    return KEY_STATUS


def llm_ready() -> bool:
    """Key configured and not known to be rejected."""
    return config.llm_configured() and KEY_STATUS.get("ok") is not False


class LLM:
    def __init__(self):
        self.enabled = llm_ready()
        self._client = None
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=3)
        return self._client

    def json(self, *, system: str, content: list[dict], schema: dict, model: str | None = None,
             effort: str | None = None, max_tokens: int = 32000, label: str = "") -> dict:
        if not self.enabled:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        import anthropic
        model = model or config.MODEL
        effort = effort or config.LLM_EFFORT
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": effort},
        )
        t0 = time.time()
        msg = None
        # Preferred: beta endpoint with server-side refusal fallback so a classifier false
        # positive on a filing never fails an ingestion. If the beta surface rejects the
        # request shape, fall back to the GA endpoint without fallbacks.
        try:
            with self.client.beta.messages.stream(**kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default") as s:
                msg = s.get_final_message()
        except (TypeError, anthropic.BadRequestError) as e:
            log.warning("beta fallback request rejected (%s); retrying on the GA endpoint", str(e)[:160])
            with self.client.messages.stream(**kwargs) as s:
                msg = s.get_final_message()
        self.calls += 1
        usage = getattr(msg, "usage", None)
        if usage:
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        if msg.stop_reason == "refusal":
            raise LLMRefused(f"model declined the request ({label})")
        if msg.stop_reason == "max_tokens":
            raise RuntimeError(f"output truncated at max_tokens ({label}); raise max_tokens or reduce the batch")
        text = next((b.text for b in msg.content if b.type == "text"), "")
        log.info("llm %s model=%s %.1fs in=%s out=%s", label, model, time.time() - t0,
                 getattr(usage, "input_tokens", "?"), getattr(usage, "output_tokens", "?"))
        return json.loads(text)
