"""
ai_providers.py — centralized AI provider routing.

Owns all raw Gemini/Groq API calls. Fixes response.text None crash.
"""
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from google import genai
from google.genai import types
from groq import Groq

from config import GEMINI_API_KEY, GROQ_API_KEY

log = logging.getLogger(__name__)

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


class ProviderError(Exception):
    def __init__(self, message: str, provider: str):
        super().__init__(message)
        self.provider = provider


@dataclass
class ProviderBothResult:
    gemini: Optional[dict]
    groq: Optional[dict]
    provider: str = "both"


def call_gemini(prompt: str) -> dict:
    if not gemini_client:
        raise ProviderError("Gemini client not configured — set GEMINI_API_KEY", "gemini")
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    if response.text is None:
        finish_reason = "unknown"
        if response.candidates:
            finish_reason = str(getattr(response.candidates[0], "finish_reason", "unknown"))
        raise ProviderError(f"Gemini returned None text (finish_reason={finish_reason})", "gemini")
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


def call_groq(prompt: str) -> dict:
    if not groq_client:
        raise ProviderError("Groq client not configured — set GROQ_API_KEY", "groq")
    completion = groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a strict, expert JSON-only output machine."},
            {"role": "user", "content": prompt},
        ],
        model="llama-3.3-70b-versatile",
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content
    if content is None:
        raise ProviderError("Groq returned None content", "groq")
    return json.loads(content.strip())


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "resource_exhausted" in text


def _retry_delay_seconds(exc: Exception, default: float = 30.0, cap: float = 60.0) -> float:
    match = re.search(r"retry in (\d+(?:\.\d+)?)", str(exc), re.IGNORECASE)
    delay = float(match.group(1)) if match else default
    return min(delay, cap)


def call_provider_tracked(prompt: str, provider: str = "gemini") -> Tuple[dict, str]:
    """
    Single-provider call that records which engine actually answered.
    On 429: wait the provider-suggested delay (capped 60s), retry once,
    then fall back to the other engine. On any other failure: fall back
    immediately. Raises if both engines fail.
    Returns (result_dict, answered_engine).
    """
    if provider == "groq":
        primary_name, secondary_name = "groq", "gemini"
    else:
        primary_name, secondary_name = "gemini", "groq"

    def _call(name: str) -> dict:
        # Resolve through module globals at call time so monkeypatching works.
        return (call_groq if name == "groq" else call_gemini)(prompt)

    try:
        return _call(primary_name), primary_name
    except Exception as exc:
        if _is_rate_limited(exc):
            delay = _retry_delay_seconds(exc)
            log.warning(f"{primary_name} rate-limited; retrying in {delay:.0f}s…")
            time.sleep(delay)
            try:
                return _call(primary_name), primary_name
            except Exception as retry_exc:
                log.warning(f"{primary_name} still failing ({retry_exc}); falling back to {secondary_name}…")
        else:
            log.warning(f"{primary_name} failed ({exc}); falling back to {secondary_name}…")
    return _call(secondary_name), secondary_name


def call_provider(prompt: str, provider: str = "gemini") -> "dict | ProviderBothResult":
    """
    provider="gemini": Gemini with Groq fallback on any failure.
    provider="groq":   Groq only, no fallback.
    provider="both":   run both independently; never raises, partial None is valid.
    """
    if provider == "groq":
        return call_groq(prompt)

    if provider == "both":
        gemini_result: Optional[dict] = None
        groq_result: Optional[dict] = None
        try:
            gemini_result = call_gemini(prompt)
        except Exception as e:
            log.warning(f"Gemini failed in both-mode: {e}")
        try:
            groq_result = call_groq(prompt)
        except Exception as e:
            log.warning(f"Groq failed in both-mode: {e}")
        return ProviderBothResult(gemini=gemini_result, groq=groq_result)

    # Default: "gemini" with Groq fallback
    try:
        return call_gemini(prompt)
    except Exception as e:
        log.warning(f"Gemini failed ({e}). Falling back to Groq…")
        return call_groq(prompt)
