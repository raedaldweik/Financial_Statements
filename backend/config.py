"""Environment configuration. Only ANTHROPIC_API_KEY is required for live mode;
without it the app boots and runs the bundled simulation instead."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEMO_DIR = BASE_DIR / "demo_data"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODEL = os.getenv("MODEL", "claude-opus-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "medium")          # low | medium | high | xhigh | max
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8192"))       # per intermediate agent turn
REPORT_MAX_TOKENS = int(os.getenv("REPORT_MAX_TOKENS", "16000"))
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "8"))
TOOL_RESULT_CAP = int(os.getenv("TOOL_RESULT_CAP", "12000"))

# "auto": live when an API key is set, otherwise simulation replay.
# Can be forced per-run from the UI.
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "auto")        # auto | live | replay


def llm_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)
