"""vet_guard.py — deterministic checks that run before an AI vetting verdict is trusted.

The vetting model is asked to explain its decision in prose. A local model will
happily write "located in the United States" for a job whose text never mentions
the US at all, which turns a fabricated justification into a wrong approval.

These checks are deterministic and run on the actual job text, so a fabricated
reason cannot carry an approval:

  * LOCATION: a role that restricts candidates to a non-US country or region is
    rejected outright, regardless of what the model said.
  * LANGUAGE: a job description written in a non-English language is rejected,
    because applying in English to a Portuguese or German posting is wrong.
  * REMOTE: a role that is neither remote nor US-based is rejected.
"""
import re

# Countries / regions that put a role out of scope for a US-based candidate.
_NON_US_ONLY_PATTERNS = (
    r"\bindia\s+only\b",
    r"\bonly\s+for\s+(?:candidates\s+)?(?:in|residents?\s+of)\s+india\b",
    r"\bmust\s+(?:be\s+)?(?:located|based|reside)\s+in\s+india\b",
    r"\bresidents?\s+of\s+india\s+only\b",
    r"\beurope\s+only\b",
    r"\bonly\s+for\s+(?:candidates\s+)?(?:in|residents?\s+of)\s+europe\b",
    r"\bemea\s+only\b",
    r"\bmiddle\s+east\s+only\b",
    r"\bapac\s+only\b",
    r"\bcanada\s+only\b",
    r"\buk\s+only\b",
    r"\bunited\s+kingdom\s+only\b",
    r"\bgermany\s+only\b",
    r"\bbrazil\s+only\b",
    r"\b[a-z]+\s+only\s+applicants?\b",
    r"\bapplicants?\s+must\s+be\s+(?:based|located|reside)\s+in\s+[a-z ]+",
    r"\bwe\s+do\s+not\s+hire\s+(?:applicants\s+)?(?:from|outside)\b",
    r"\bno\s+visa\s+(?:sponsorship|required)\b",
    r"\bwe\s+do\s+not\s+offer\s+visa\s+sponsorship\b",
    r"\bno\s+visa\s+sponsorship\s+is\s+(?:provided|available|offered)\b",
    r"\bmust\s+have\s+(?:authorization|work\s+permit)\s+to\s+work\s+in\s+[a-z ]+",
    r"\bsecurity\s+clearance\s+is\s+required\b",
)

# Explicitly US-friendly signals: these make a role approvable.
_US_SIGNALS = (
    r"\bunited\s+states\b",
    r"\busa\b",
    r"\bu\.s\.a?\b",
    r"\bnew\s+york\b",
    r"\bsan\s+francisco\b",
    r"\bcalifornia\b",
    r"\bseattle\b",
    r"\baustin\b",
    r"\btexas\b",
    r"\bcolorado\b",
    r"\bmassachusetts\b",
    r"\bwashington\s+state\b",
    r"\bflorida\b",
    r"\bchicago\b",
    r"\bboston\b",
    r"\bdenver\b",
    r"\batlanta\b",
    r"\bportland\b",
    r"\bremote\s+in\s+the\s+(?:us|united\s+states)\b",
    r"\bremote\s*[-–(]?\s*(?:us|usa|u\.s\.a?)\b",
    r"\bremote\s+(?:within|from)\s+the\s+(?:us|united\s+states)\b",
    r"\bus\s+remote\b",
    r"\bremote\s+us\b",
    r"\bunited\s+states\s+remote\b",
    r"\bamericans?\s+only\b",
    r"\bwork\s+from\s+home\s+in\s+the\s+us\b",
)

# Remote signals (location-neutral).
_REMOTE_SIGNALS = (
    r"\bremote\b",
    r"\bwork\s+from\s+home\b",
    r"\bwfh\b",
    r"\bfully\s+remote\b",
    r"\b100%\s*remote\b",
    r"\bdistributed\s+team\b",
    r"\banywhere\b",
    r"\bworldwide\b",
    r"\bglobal\s+remote\b",
)

# Language detection for non-English postings.
_NON_ENGLISH_HINTS = (
    ("portuguese", r"\bnosso\s+prop[oó]sito\b|\bvaga[s]?\s+de\b|\bidiade\b|\bempresa\b.*\bcadastro\b"),
    ("german", r"\bunsere\s+(?:mission|aufgabe|produkt)\b|\bwerkzeug\b.*\bentwickl"),
    ("spanish", r"\bnuestra\s+misi[oó]n\b|\bposici[oó]n\b.*\bcontable\b|\bempresa\s+en\s+crecimiento\b"),
    ("french", r"\bnotre\s+mission\b|\bposte\s+de\s+d[eé]veloppeur\b"),
    ("italian", r"\bla\s+nostra\s+missione\b|\bposizione\s+di\s+sviluppatore\b"),
    ("dutch", r"\bonze\s+missie\b|\bvacature\b.*\bsoftware\b"),
    ("polish", r"\bnasza\s+misja\b"),
)


def _matches_any(text: str, patterns) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def location_verdict(jd: str, location: str = "") -> dict:
    """Deterministic location check for a job description.

    Returns {"ok": bool, "reason": str, "signals": [...]}.
    """
    text = str(jd or "")
    loc_field = str(location or "")
    haystack = f"{text}\n{loc_field}"

    non_us = _matches_any(text, _NON_US_ONLY_PATTERNS)

    # The structured location field is authoritative: it comes from the job
    # board's own field, not from a text scrape that may be truncated. The
    # description cap is 3000 chars, so a location section further down the
    # page is simply not present in the text.
    field_is_remote = bool(re.search(
        r"\b(remote|worldwide|anywhere|global|international|distributed|virtual)\b",
        loc_field, re.IGNORECASE))
    field_is_us = bool(re.search(
        r"\b(united states|usa|u\.s\.?|us|new york|san francisco|california|"
        r"seattle|austin|texas|colorado|florida|chicago|boston|denver|atlanta)\b",
        loc_field, re.IGNORECASE))

    us_ok = _matches_any(haystack, _US_SIGNALS) or field_is_us
    remote_ok = _matches_any(text, _REMOTE_SIGNALS) or field_is_remote

    signals = []
    if non_us:
        signals.append("restricted to a non-US market")
    if us_ok:
        signals.append("mentions the United States")
    if remote_ok:
        signals.append("remote")

    if non_us:
        return {"ok": False, "reason": "role is restricted to a non-US market", "signals": signals}
    if not (us_ok or remote_ok):
        # No location signal anywhere: the description is often truncated before
        # the location section, so this is unknown, not disqualifying. The
        # guard only rejects what it can prove, it never approves.
        return {"ok": True,
                "reason": "no location signal found (description may be truncated)",
                "signals": signals,
                "unknown": True}
    return {"ok": True, "reason": "location is compatible with a US-based candidate", "signals": signals}


def language_verdict(jd: str) -> dict:
    """Reject a posting written in a language other than English."""
    text = str(jd or "")
    for language, pattern in _NON_ENGLISH_HINTS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return {"ok": False, "reason": f"job description is written in {language}", "language": language}
    return {"ok": True, "reason": "job description is in English", "language": "en"}


def check_job(jd: str, location: str = "") -> dict:
    """Run every deterministic check. Returns a combined verdict."""
    lang = language_verdict(jd)
    loc = location_verdict(jd, location)
    reasons = []
    if not lang["ok"]:
        reasons.append(lang["reason"])
    if not loc["ok"]:
        reasons.append(loc["reason"])
    return {
        "ok": lang["ok"] and loc["ok"],
        "language": lang,
        "location": loc,
        "reasons": reasons,
    }
