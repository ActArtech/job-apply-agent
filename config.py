"""Configuration for the job-application agent.

Secrets come from the environment (see .env.example). Candidate details come from
profile.json, which is gitignored — copy profile.example.json to profile.json and
fill in your own details before running the pipeline.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── API Keys ────────────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
# Local LLM via Ollama (OpenAI-compatible). Empty disables it.
OLLAMA_BASE_URL     = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL        = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
# MiniMax cloud (OpenAI-compatible). Empty key disables it.
MINIMAX_API_KEY     = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL    = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
MINIMAX_MODEL       = os.getenv("MINIMAX_MODEL", "MiniMax-M3")
HUNTER_API_KEY      = os.getenv("HUNTER_API_KEY", "")          # hunter.io
APOLLO_API_KEY      = os.getenv("APOLLO_API_KEY", "")          # apollo.io
SNOV_API_KEY        = os.getenv("SNOV_API_KEY", "")            # snov.io
SERPER_API_KEY      = os.getenv("SERPER_API_KEY", "")          # serper.dev
GOOGLE_SHEET_ID     = os.getenv("GOOGLE_SHEET_ID", "")         # from sheet URL
GMAIL_CREDENTIALS   = os.getenv("GMAIL_CREDENTIALS", "credentials.json")  # OAuth2 file

# ── Candidate Profile ────────────────────────────────────────────────────────
_PROFILE_PATH = Path(os.getenv("PROFILE_PATH", Path(__file__).parent / "profile.json"))
_EXAMPLE_PATH = Path(__file__).parent / "profile.example.json"


def _load_profile() -> dict:
    """Load profile.json, falling back to the shipped example."""
    for path in (_PROFILE_PATH, _EXAMPLE_PATH):
        if path.exists():
            return json.loads(path.read_text())
    raise FileNotFoundError(
        "No profile found. Copy profile.example.json to profile.json and fill it in."
    )


PROFILE = _load_profile()
_contact = PROFILE["contact"]

MY_NAME      = _contact["name"]
MY_EMAIL     = _contact["email"]
MY_PHONE     = _contact["phone"]
MY_PORTFOLIO = _contact.get("portfolio", "")
MY_LINKEDIN  = _contact.get("linkedin", "")

MY_LEGAL_FIRST_NAME            = _contact.get("legal_first_name", MY_NAME)
MY_LEGAL_LAST_NAME             = _contact.get("legal_last_name", "")
MY_PREFERRED_FIRST_NAME        = _contact.get("preferred_first_name", MY_NAME)
MY_PREFERRED_LAST_NAME         = _contact.get("preferred_last_name", "")
MY_REQUIRED_LAST_NAME_FALLBACK = _contact.get("last_name_fallback", "N/A")

_address = PROFILE.get("address", {})
MY_ADDRESS_LINE_1 = _address.get("line1", "")
MY_CITY           = _address.get("city", "")
MY_STATE          = _address.get("state", "")
MY_POSTAL_CODE    = _address.get("postal_code", "")
MY_COUNTRY        = _address.get("country", "")

_authorization = PROFILE.get("work_authorization", {})
MY_WORK_AUTHORIZED_INDIA = _authorization.get("authorized_in_country", True)
MY_REQUIRES_SPONSORSHIP  = _authorization.get("requires_sponsorship", False)

# ── Resume Data (source of truth for AI tailoring) ───────────────────────────
RESUME = {
    "name":       MY_NAME,
    "email":      MY_EMAIL,
    "phone":      MY_PHONE,
    "portfolio":  MY_PORTFOLIO,
    "linkedin":   MY_LINKEDIN,
    "experience": PROFILE["experience"],
    "skills":     PROFILE["skills"],
    "education":  PROFILE["education"],
}

# ── Job Search Filters ────────────────────────────────────────────────────────
TARGET_ROLES = PROFILE.get("target_roles", [
    "engineer", "developer", "programmer", "software", "backend", "frontend",
    "full stack", "full-stack", "fullstack", "sde", "tech lead", "architect",
    "systems", "node", "python", "react", "java",
])

EXCLUDED_KEYWORDS = PROFILE.get("excluded_keywords", [
    "data scientist", "ml engineer", "machine learning", "qa",
    "hardware", "firmware", "robotics", "mechanical",
])

# ── Sending Limits (stay under spam radar) ────────────────────────────────────
MAX_EMAILS_PER_DAY   = int(os.getenv("MAX_EMAILS_PER_DAY", "25"))
DELAY_BETWEEN_EMAILS = (90, 300)   # random seconds between sends (min, max)
FOLLOWUP_AFTER_DAYS  = 5           # days before sending a follow-up

# ── Google Sheets column order ────────────────────────────────────────────────
SHEET_COLUMNS = [
    "Date", "Company", "Role", "JD URL", "Hiring Manager", "Their Email", "LinkedIn URL",
    "Match Score", "Outcome", "Email Sent?", "Email Subject", "Follow-up Sent?",
    "Response", "Notes",
]
