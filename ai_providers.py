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

from config import (GEMINI_API_KEY, GROQ_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL,
                    MINIMAX_API_KEY, MINIMAX_BASE_URL, MINIMAX_MODEL)

log = logging.getLogger(__name__)

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Local provider: Ollama's OpenAI-compatible endpoint. No cloud key needed.
_ollama_client = None
if OLLAMA_BASE_URL:
    try:
        from openai import OpenAI

        _ollama_client = OpenAI(
            api_key="ollama",
            base_url=OLLAMA_BASE_URL.rstrip("/") + "/v1",
            timeout=300.0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Ollama client init failed: %s", exc)
        _ollama_client = None


class ProviderError(Exception):
    def __init__(self, message: str, provider: str):
        super().__init__(message)
        self.provider = provider


@dataclass
class ProviderBothResult:
    gemini: Optional[dict]
    groq: Optional[dict]
    provider: str = "both"


# Cloud provider: MiniMax's OpenAI-compatible endpoint. Preferred over the
# local model because it fabricates far less and is much faster; the local
# engine stays as the offline fallback.
_minimax_client = None
if MINIMAX_API_KEY:
    try:
        from openai import OpenAI as _MiniMaxOpenAI
        _minimax_client = _MiniMaxOpenAI(
            api_key=MINIMAX_API_KEY,
            base_url=MINIMAX_BASE_URL.rstrip("/"),
            timeout=180.0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("MiniMax client init failed: %s", exc)
        _minimax_client = None


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    """MiniMax reasoning models emit a <think> block before the answer."""
    return _THINK_RE.sub("", str(text or "")).strip()


def call_minimax(prompt: str) -> dict:
    if not _minimax_client:
        raise ProviderError("MiniMax client not configured — set MINIMAX_API_KEY", "minimax")
    response = _minimax_client.chat.completions.create(
        model=MINIMAX_MODEL,
        messages=[
            {"role": "system", "content": "You are a strict, expert JSON-only output machine."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        # MiniMax-Text-01 does not reason, so a moderate cap is enough.
        # If you switch MINIMAX_MODEL to M3/M2.5, raise this to 16384: their
        # <think> block counts against max_tokens.
        max_tokens=8192,
        # MiniMax rejects response_format="json_object"; the system prompt
        # plus the JSON parse below is what keeps the output structured.
    )
    content = _strip_think(response.choices[0].message.content)
    if not content:
        raise ProviderError("MiniMax returned empty content", "minimax")
    raw = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


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


def call_ollama(prompt: str) -> dict:
    """Local LLM via Ollama's OpenAI-compatible endpoint."""
    if not _ollama_client:
        raise ProviderError("Ollama not configured — set OLLAMA_BASE_URL", "ollama")
    completion = _ollama_client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a strict, expert JSON-only output machine."},
            {"role": "user", "content": prompt},
        ],
        model=OLLAMA_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content
    if not content:
        raise ProviderError("Ollama returned empty content", "ollama")
    raw = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
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


def _engine_ready(name: str) -> bool:
    """True when the named engine has what it needs to answer."""
    if name == "gemini":
        return gemini_client is not None
    if name == "groq":
        return groq_client is not None
    if name == "ollama":
        return _ollama_client is not None
    if name == "minimax":
        return _minimax_client is not None
    return False


def _resolve_chain(provider: str) -> list[str]:
    """Build the fallback chain for a requested provider.

    The chain is NOT pre-filtered by credentials: an engine with no key raises
    immediately ("client not configured") and the call falls through to the
    next one. The local Ollama engine needs no key and is always last, so with
    no cloud keys configured the request still gets answered locally instead
    of failing and being recorded as a rejection.

    Upstream assumed Gemini and Groq were always configured, so its chain had
    no local fallback and every job was rejected when the keys were absent.
    """
    if provider == "groq":
        # Keep the upstream contract: Groq falls back to Gemini.
        chain = ["groq", "gemini", "minimax", "ollama"]
    elif provider == "ollama":
        chain = ["ollama", "minimax", "gemini", "groq"]
    else:
        # Upstream order first (gemini -> groq), then MiniMax, then local.
        # Unconfigured engines raise instantly and cost nothing, so production
        # falls through to MiniMax while the tests that monkeypatch gemini
        # keep their original contract.
        chain = ["gemini", "groq", "minimax", "ollama"]
    return chain


def call_provider_tracked(prompt: str, provider: str = "gemini") -> Tuple[dict, str]:
    """
    Single-provider call that records which engine actually answered.
    On 429: wait the provider-suggested delay (capped 60s), retry once,
    then fall back to the next configured engine. On any other failure: fall
    back immediately. Raises if every engine fails.
    Returns (result_dict, answered_engine).
    """
    chain = _resolve_chain(provider)
    primary_name = chain[0]
    secondary_name = chain[1] if len(chain) > 1 else None

    def _call(name: str) -> dict:
        # Resolve through module globals at call time so monkeypatching works.
        if name == "groq":
            return call_groq(prompt)
        if name == "ollama":
            return call_ollama(prompt)
        if name == "minimax":
            return call_minimax(prompt)
        return call_gemini(prompt)

    last_error: Optional[Exception] = None
    for index, name in enumerate(chain):
        try:
            return _call(name), name
        except Exception as exc:
            last_error = exc
            if index == 0 and _is_rate_limited(exc):
                delay = _retry_delay_seconds(exc)
                log.warning(f"{name} rate-limited; retrying in {delay:.0f}s…")
                time.sleep(delay)
                try:
                    return _call(name), name
                except Exception as retry_exc:
                    last_error = retry_exc
                    log.warning(f"{name} still failing ({retry_exc})")
            else:
                log.warning(f"{name} failed ({exc})")
            if index + 1 < len(chain):
                log.warning(f"falling back to {chain[index + 1]}…")
    raise last_error if last_error else ProviderError("no AI provider is configured", provider)


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

    if provider == "ollama":
        # Local provider: Ollama first, then Gemini, then Groq.
        try:
            return call_ollama(prompt)
        except Exception as e:
            log.warning(f"Ollama failed ({e}). Falling back to Gemini…")
            try:
                return call_gemini(prompt)
            except Exception:
                return call_groq(prompt)

    # Default: resolved chain (gemini -> groq, with local Ollama inserted when
    # no cloud key is configured).
    chain = _resolve_chain("gemini")
    last_error: Optional[Exception] = None
    for index, name in enumerate(chain):
        try:
            if name == "ollama":
                return call_ollama(prompt)
            if name == "groq":
                return call_groq(prompt)
            if name == "minimax":
                return call_minimax(prompt)
            return call_gemini(prompt)
        except Exception as e:
            last_error = e
            log.warning(f"{name} failed ({e})")
            if index + 1 < len(chain):
                log.warning(f"Falling back to {chain[index + 1]}…")
    raise last_error if last_error else ProviderError("no AI provider is configured", provider)

def local_available() -> bool:
    """True when the local Ollama provider is configured and usable."""
    return _ollama_client is not None


def minimax_available() -> bool:
    """True when the MiniMax cloud provider is configured and usable."""
    return _minimax_client is not None
