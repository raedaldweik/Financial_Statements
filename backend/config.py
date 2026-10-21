"""Environment configuration.

Only ANTHROPIC_API_KEY is needed for full ingestion (statement transcription, note
curation, investor lens). Without it the server still runs: uploads are processed in
extraction-only mode (statements parsed heuristically, notes split and indexed, no
summaries or flags) and the two sample filings are served from their curated bundles.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SEED_DIR = BASE_DIR / "seed"
SEED_FILINGS_DIR = ROOT_DIR / "filings"
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", ROOT_DIR / "storage")).resolve()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODEL = os.getenv("MODEL", "claude-opus-5-5")             # statements, auditor, lens, brief
MODEL_NOTES = os.getenv("MODEL_NOTES", MODEL)              # per-note curation batches
LLM_EFFORT = os.getenv("LLM_EFFORT", "medium")             # low | medium | high | xhigh | max
NOTES_PER_CALL = int(os.getenv("NOTES_PER_CALL", "6"))
NOTE_TEXT_CAP = int(os.getenv("NOTE_TEXT_CAP", "14000"))   # characters of note text sent per note
PARALLEL_NOTE_CALLS = int(os.getenv("PARALLEL_NOTE_CALLS", "3"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))
PDFTOTEXT = os.getenv("PDFTOTEXT", "pdftotext")
# The two sample filings (Aramco, Saudi Ceramic) are copied into storage at start so a fresh
# deployment shows what the output looks like. Set SEED_SAMPLES=0 to start empty; samples can
# also be removed (and restored) from the UI.
SEED_SAMPLES = os.getenv("SEED_SAMPLES", "1").strip().lower() not in ("0", "false", "no", "off")


def llm_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)
