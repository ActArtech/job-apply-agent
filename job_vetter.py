"""
job_vetter.py — AI pre-screening to evaluate scraped jobs against strict user criteria.

Criteria (Alaa, US-based; adapted from the author's India-based original):
1. Product-based company (no agencies/consultancies).
2. Remote (global, allowing candidates from the United States) OR located in the United States.
   Roles located outside the United States are skipped, not applied to.
3. Compensation target: > $150,000 USD.
4. Any software engineering / development role (AI, platform, full stack, backend, frontend).
5. Ignore years-of-experience requirements.
"""

import logging
from typing import Optional, Tuple

from ai_providers import (
    call_provider,
    call_provider_tracked,
    ProviderBothResult,
    local_available as _local_available,
)

log = logging.getLogger(__name__)

VALID_STAGES = {
    "pre_seed", "seed", "series_a", "series_b",
    "series_c_plus", "public", "bootstrapped", "unknown",
}
STAGE_BUCKETS = {
    "pre_seed": "early", "seed": "early", "series_a": "early", "series_b": "early",
    "series_c_plus": "growth",
    "public": "established", "bootstrapped": "established",
    "unknown": "unknown",
}


def _stage_bucket(stage: str) -> str:
    return STAGE_BUCKETS.get(stage, "unknown")


def _normalize_stage(value) -> str:
    stage = str(value or "").strip().lower()
    return stage if stage in VALID_STAGES else "unknown"


VETTING_PROMPT = """You are a strict, expert job evaluator for a Senior AI / Platform Software Engineer based in Delaware, United States.
Your job is to read the provided Job Description and determine if it meets ALL 5 of the following strict criteria:

1. PRODUCT-BASED COMPANY: The company MUST build their own product. STRICTLY REJECT any service-based companies, IT consultancies, dev shops, or agencies (e.g., TCS, Infosys, Wipro, generic web-dev agencies).
2. LOCATION: The role MUST be Remote (allowing candidates from the United States) OR located directly in the United States.
   - CRITICAL: If the job says "Remote", ASSUME it allows the United States unless the text explicitly states "India only", "EU only", "APAC only", "Must reside in <country>", or explicitly lists a subset of countries that does not include the United States. If it's a generic "Remote" worldwide role, APPROVE IT.
   - REJECT any role located outside the United States (Canada, India, Germany, the UK, Israel, and every Middle East market are all out of scope).
3. COMPENSATION (STAGE-AWARE): Target is > $150,000 USD.
   - If the company is EARLY or GROWTH stage (pre-seed through Series C+), funding stage is the pay proxy: DO NOT reject for a missing or unstated salary — assume a funded startup at this stage can meet the target. Reject ONLY if a salary is explicitly stated below the target.
   - If the company is ESTABLISHED (public or large bootstrapped), keep the comp expectation: if salary is explicitly below target, REJECT.
   - If stage is UNKNOWN and salary is unstated, stay permissive for a remote/global product role.
   - IMPORTANT: an UNSTATED salary is NEVER on its own a reason to reject. Only an EXPLICITLY stated salary below the target is a rejection. If the JD does not state a salary, do not reject for compensation; say "compensation not stated" in the reason and approve.
4. ROLE: It must be a Software Engineering / Development role (Backend, Frontend, Full Stack, iOS, Android, etc.).
5. EXPERIENCE: Do NOT reject based on high Years of Experience requirements. If it matches the other criteria, approve it.

FUNDING STAGE: Estimate the company's funding stage from the JD and your knowledge of the company. Choose exactly one: pre_seed, seed, series_a, series_b, series_c_plus, public, bootstrapped, or unknown. If unsure, use "unknown".

JOB DETAILS:
Company: {company}
Role: {role}
URL: {url}

JOB DESCRIPTION:
{jd}

TASK:
Return ONLY a valid JSON object. No markdown, no backticks, no explanations outside the JSON.
Structure:
{{
  "is_approved": true or false,
  "score": <0-100 integer confidence score>,
  "reason": "<1 sentence explaining why it passed or failed. Be specific about Compensation, Product-based, and Location.>",
  "stage": "<pre_seed|seed|series_a|series_b|series_c_plus|public|bootstrapped|unknown>",
  "stageEvidence": "<short phrase: why you chose this stage>",
  "missingSignals": ["<important missing signal, if any>"]
}}
"""

def _normalize_vetting_result(data: dict) -> dict:
    score = data.get("score", 100 if data.get("is_approved") else 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    missing = data.get("missingSignals", [])
    if not isinstance(missing, list):
        missing = []
    stage = _normalize_stage(data.get("stage"))
    return {
        "approved": bool(data.get("is_approved", data.get("approved", False))),
        "score": score,
        "reason": data.get("reason", "No reason provided."),
        "stage": stage,
        "stage_bucket": _stage_bucket(stage),
        "missingSignals": [str(item) for item in missing],
    }


def vetting_status(vetting: Optional[dict]) -> Optional[str]:
    """
    Canonical vetting state: "approved" | "rejected" | "error" | None (never vetted).

    Handles legacy files without a status field — including pre-overhaul rows
    where provider failures were recorded as rejections with an
    "AI vetting failed" reason; those derive to "error" so dedup re-vets them.
    """
    if not vetting:
        return None
    status = vetting.get("status")
    if status in ("approved", "rejected", "error"):
        return status
    if vetting.get("provider") == "both":
        gemini = vetting.get("gemini")
        groq = vetting.get("groq")
        if gemini is None and groq is None:
            return "error"
        chosen = gemini or groq
        return "approved" if chosen.get("approved") else "rejected"
    reason = vetting.get("reason")
    if isinstance(reason, str) and reason.startswith("AI vetting failed"):
        return "error"
    return "approved" if vetting.get("approved") is True else "rejected"


def vet_job_detail(company: str, role: str, url: str, jd: str, provider: str = "gemini",
                   location: str = "") -> dict:
    """
    Evaluates job against 5-rule criteria using AI.

    provider="gemini"|"groq": single vetting dict with status/engine metadata.
    provider="both":          {"gemini": dict|None, "groq": dict|None, "provider": "both"}.
    status is "approved" | "rejected" | "error" — error means the job could
    not be vetted (short JD, rate limit, provider down) and is retryable.
    """
    requested_provider = provider

    if not jd or len(jd) < 100:
        message = "Job description too short or empty."
        return {
            "status": "error",
            "approved": None,
            "score": 0,
            "reason": message,
            "error": message,
            "missingSignals": ["job_description"],
            "engine": {"requested": requested_provider, "answered": None},
        }

    # Deterministic gate first. The vetting model writes its justification in
    # prose and a local model will claim "located in the United States" for a
    # posting that never mentions the US. A fabricated reason must not be able
    # to carry an approval, so location and language are checked against the
    # actual job text before the AI verdict is trusted.
    from vet_guard import check_job
    guard = check_job(jd, location)
    if not guard["ok"]:
        return {
            "status": "rejected",
            "approved": False,
            "score": 0,
            "reason": "; ".join(guard["reasons"]),
            "error": None,
            "missingSignals": ["location" if not guard["location"]["ok"] else "language"],
            "engine": {"requested": provider, "answered": None},
            "guard": {"ok": False, "reasons": guard["reasons"]},
        }
    # A stated salary below the target is a hard rejection. An unstated salary
    # is not: the prompt says to stay permissive for a remote product role when
    # the funding stage is unknown, and a small model often ignores that and
    # rejects for "unknown funding stage" alone.
    from vet_guard import compensation_verdict
    comp = compensation_verdict(jd)
    if not comp["ok"]:
        return {
            "status": "rejected",
            "approved": False,
            "score": 0,
            "reason": comp["reason"],
            "error": None,
            "missingSignals": ["compensation"],
            "engine": {"requested": provider, "answered": None},
            "guard": {"ok": False, "reasons": [comp["reason"]]},
        }

    prompt = VETTING_PROMPT.format(company=company, role=role, url=url, jd=jd)

    # The requested provider is preserved for reporting. The engine that
    # actually answers is reported separately, so "requested" stays truthful.
    # Local Ollama takes over when configured (no cloud key needed). The
    # upstream "both" mode compares two cloud engines; here the local engine
    # is the one that actually answers.
    #
    # The local engine must win for ANY requested provider when the requested
    # cloud engine has no key: otherwise provider="gemini" (the default) tries
    # Gemini, falls back to Groq, and both fail with "client not configured",
    # turning every job into a spurious rejection.
    # Cloud MiniMax first when configured: it fabricates far less than the
    # local model. Ollama remains the offline fallback.
    from ai_providers import minimax_available as _minimax_available
    if _minimax_available() and provider in ("gemini", "both"):
        provider = "minimax"
    elif _local_available() and provider in ("gemini", "both"):
        provider = "ollama"

    if provider == "both":
        result = call_provider(prompt, "both")
        gemini_vet = _normalize_vetting_result(result.gemini) if result.gemini else None
        groq_vet = _normalize_vetting_result(result.groq) if result.groq else None
        return {"gemini": gemini_vet, "groq": groq_vet, "provider": "both"}

    try:
        raw, answered = call_provider_tracked(prompt, provider)
    except Exception as e:
        log.error(f"AI vetting failed for {company}: {e}")
        return {
            "status": "error",
            "approved": None,
            "score": 0,
            "reason": f"Could not vet: {e}",
            "error": str(e),
            "missingSignals": ["ai_vetting"],
            "engine": {"requested": requested_provider, "answered": None},
        }

    vet = _normalize_vetting_result(raw)
    vet["status"] = "approved" if vet["approved"] else "rejected"
    vet["engine"] = {"requested": requested_provider, "answered": answered}
    return vet


def vet_job(company: str, role: str, url: str, jd: str) -> Tuple[bool, str]:
    """
    Compatibility wrapper for legacy scraper callers.
    Returns (is_approved, reason).
    """
    result = vet_job_detail(company=company, role=role, url=url, jd=jd)
    return result["approved"], result["reason"]
