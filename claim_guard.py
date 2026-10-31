"""claim_guard.py — verify that tailored resume claims are grounded in the CV.

The tailoring model rewrites bullets for each job. A local model will happily
invent metrics ("30% improvement in data throughput") and stack keywords
("Go and Node.js") that never appear in the candidate's real CV. Those claims
end up on a resume the candidate has to defend in an interview.

This module checks two things:
  1. NUMERIC CLAIMS: every percentage, multiplier and "N of M" figure in a
     tailored bullet must already exist in the CV. Otherwise the bullet is
     flagged as ungrounded.
  2. STACK TERMS: technology names used in a tailored bullet must appear in the
     CV's skills or experience text.

A bullet that fails is replaced by the nearest grounded bullet from the same
role, so the resume stays truthful and still fills the required bullet count.
"""
import json
import re
from typing import Iterable

_NUMERIC_CLAIM_RE = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?x\b|\b\d+\s+of\s+\d+\b"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s+(?:requests|queries|users|transactions|events|calls|rows|"
    r"records|documents|accounts|deployments|releases|features|customers|"
    r"endpoints|jobs|tickets|incidents|agents|models|skills)\b"
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|"
    r"million|billion)\s+(?:requests|queries|users|transactions|events|calls|rows|"
    r"records|documents|accounts|deployments|releases|features|customers|"
    r"endpoints|jobs|tickets|incidents|agents|models|skills)\b)",
    re.IGNORECASE,
)

# Common technical terms that may legitimately appear in a job description but
# must be present in the CV before they are allowed into a bullet.
# Discipline-level words: describing AI/ML work at the category level is not a
# claim of a specific technology. Allowed whenever the CV shows AI work at all.
_AI_FAMILY_TERMS = {
    "ai", "ml", "nlp", "llm", "llms", "rag", "ai/ml", "mlops",
    "ai/ml implementation", "ai-driven", "ai-assisted", "ai systems",
    "agentic", "agent", "agents", "multi-agent", "llm/rag",
}

# Specific technologies: naming one in a bullet asserts real experience.
_STOPWORDS = {
    "go", "node", "nodejs", "node.js", "python", "typescript", "javascript",
    "react", "next.js", "nextjs", "vue", "angular", "java", "kotlin", "swift",
    "ruby", "rails", "php", "laravel", "dotnet", "c#", "cpp", "rust", "scala",
    "elixir", "erlang", "haskell", "clojure", "perl", "r", "julia",
    "django", "flask", "fastapi", "express", "nestjs", "spring", "rails",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "sqlite", "oracle",
    "elastic", "elasticsearch", "kafka", "rabbitmq", "celery", "aws", "gcp",
    "azure", "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins",
    "circleci", "github", "gitlab", "nginx", "linux", "unix", "macos", "windows",
    "graphql", "grpc", "rest", "api", "apis", "sql", "nosql", "ci", "cd",
    "llm", "llms", "rag", "nlp", "ml", "ai",  "devops", "sre",
    "microservices", "microservice", "tdd", "agile", "scrum", "git",
    "websocket", "websockets", "kafka", "lambda", "s3", "ec2", "eks", "fargate",
    "dynamodb", "sqs", "sns", "oauth", "oauth2", "jwt", "http", "https", "tcp",
    "jira", "confluence", "figma", "notion", "salesforce", "sap", "wordpress",
    "shopify", "stripe", "twilio", "sendgrid", "segment", "amplitude", "mixpanel",
}


def _normalize_number(token: str) -> str:
    """Normalize a numeric claim so '30%' and '30 %' compare equal."""
    return re.sub(r"\s+", "", token).lower()


def cv_grounding_corpus(profile: dict) -> str:
    """All text from the CV that can ground a claim."""
    parts = []
    for entry in profile.get("experience", []) or []:
        parts.append(str(entry.get("company", "")))
        parts.append(str(entry.get("role", "")))
        for bullet in entry.get("bullets", []) or []:
            parts.append(str(bullet))
    for category, items in (profile.get("skills", {}) or {}).items():
        parts.append(str(category))
        parts.extend(str(i) for i in (items or []))
    for key in ("summary", "headline", "name", "title"):
        if profile.get(key):
            parts.append(str(profile[key]))
    return "\n".join(parts)


def cv_numeric_claims(profile: dict) -> set[str]:
    """Every numeric claim the CV actually supports."""
    corpus = cv_grounding_corpus(profile)
    return {_normalize_number(m.group(1)) for m in _NUMERIC_CLAIM_RE.finditer(corpus)}


def cv_stack_terms(profile: dict) -> set[str]:
    """Technology names the CV supports."""
    corpus = cv_grounding_corpus(profile).lower()
    terms = set()
    for term in _STOPWORDS:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", corpus):
            terms.add(term)
    # also accept any explicit skill entry
    for items in (profile.get("skills", {}) or {}).values():
        for item in (items or []):
            terms.add(str(item).strip().lower())
    return terms


def _has_ai_work(profile: dict) -> bool:
    """True when the CV shows AI/agentic work, so discipline words are fair game."""
    corpus = cv_grounding_corpus(profile).lower()
    markers = ("ai systems", "agentic", "llm", "rag", "ai/ml", "artificial intelligence",
               "machine learning", "evaluation harness", "ai agent")
    return any(marker in corpus for marker in markers)


def ungrounded_claims(bullet: str, numeric_claims: set[str], stack_terms: set[str],
                      allow_ai_family: bool = True,
                      vocabulary: set[str] = None) -> list[str]:
    """Return the list of unsupported claims in a tailored bullet.

    allow_ai_family: when the candidate's CV shows AI work, discipline-level
    words (AI, ML, LLM, RAG, NLP) are allowed. Naming a specific technology
    that is absent from the CV (Celery, RabbitMQ, Kubernetes) is always flagged.
    """
    problems = []
    for match in _NUMERIC_CLAIM_RE.finditer(bullet or ""):
        token = _normalize_number(match.group(1))
        if token not in numeric_claims:
            problems.append(f"numeric claim {match.group(1)!r} is not in the CV")

    lowered = (bullet or "").lower()
    for term in _STOPWORDS:
        if _term_grounded(term, stack_terms):
            continue
        if allow_ai_family and term in _AI_FAMILY_TERMS:
            continue
        if not re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", lowered):
            continue
        problems.append(f"stack term {term!r} is not in the CV")

    # Domain vocabulary: a bullet may not introduce a field of work the CV
    # never mentions (fraud detection, threat hunting, tax engines).
    if vocabulary is not None:
        novel = novel_domain_terms(bullet, vocabulary)
        if len(novel) > NOVEL_TERM_LIMIT:
            problems.append(
                "introduces work not in the CV: " + ", ".join(novel[:6]))
    return problems


def _term_grounded(term: str, stack_terms: set[str]) -> bool:
    """True when the CV supports this technology, allowing singular/plural
    and common spelling variants ("api"/"apis", "node"/"node.js")."""
    if term in stack_terms:
        return True
    variants = {term, term + "s", term.rstrip("s")}
    if term.endswith("s"):
        variants.add(term[:-1])
    if term == "node":
        variants.update({"nodejs", "node.js"})
    if term in ("nodejs", "node.js"):
        variants.add("node")
    if term == "postgres":
        variants.add("postgresql")
    if term == "postgresql":
        variants.add("postgres")
    if term == "javascript":
        variants.add("js")
    if term == "typescript":
        variants.add("ts")
    return any(v in stack_terms for v in variants)


def verify_bullets(bullets: Iterable[str], profile: dict) -> dict:
    """Verify a bullet list against the CV.

    Returns {"ok": bool, "clean": [...], "flagged": [(bullet, reasons), ...]}.
    """
    numeric_claims = cv_numeric_claims(profile)
    stack_terms = cv_stack_terms(profile)
    allow_ai_family = _has_ai_work(profile)
    vocabulary = cv_vocabulary(profile)
    clean, flagged = [], []
    for bullet in bullets or []:
        text = str(bullet or "").strip()
        if not text:
            continue
        problems = ungrounded_claims(text, numeric_claims, stack_terms, allow_ai_family,
                                      vocabulary)
        if problems:
            flagged.append((text, problems))
        else:
            clean.append(text)
    return {"ok": not flagged, "clean": clean, "flagged": flagged}


# Patterns that attach a fabricated number to an otherwise truthful claim.
_DEQUANT_PATTERNS = [
    # "a 30% improvement", "a 25% reduction", "an 18% increase"
    (re.compile(r"\b([Aa]n?|the)\s+\d+(?:\.\d+)?\s*%\s+(?=improvement|reduction|increase|decrease|drop|gain|growth|faster|speedup|speed-up)\b", re.IGNORECASE), r"\1 "),
    # "by 25%", "by 1.5x", "by 30 percent"
    (re.compile(r"\bby\s+\d+(?:\.\d+)?\s*%\b", re.IGNORECASE), "by a measured margin"),
    (re.compile(r"\bby\s+\d+(?:\.\d+)?x\b", re.IGNORECASE), "by a measured multiple"),
    (re.compile(r"\bby\s+\d+(?:\.\d+)?\s+percent\b", re.IGNORECASE), "by a measured margin"),
    # "1.5x faster", "2x faster"
    (re.compile(r"\b\d+(?:\.\d+)?x\s+(?=faster|speedup|speed-up|higher|lower|better)\b", re.IGNORECASE), "measurably "),
    # "cutting setup time 20%", "reducing latency 15%"
    (re.compile(r"\b(cutting|reducing|lowering|improving|increasing|boosting)\s+([a-zA-Z0-9 ,\-]{2,30}?)\s+\d+(?:\.\d+)?\s*%", re.IGNORECASE), r"\1 \2"),
    # a bare trailing percentage: "throughput 30%." / "efficiency 18%"
    (re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE), "a measured margin"),
    # a bare multiplier
    (re.compile(r"\b\d+(?:\.\d+)?x\b", re.IGNORECASE), "a measured multiple"),
]


def dequantify(bullet: str, numeric_claims: set[str]) -> str:
    """Remove numeric claims that the CV does not support.

    A fabricated number makes a bullet indefensible in an interview, but the
    rest of the sentence is often true. The repair is deliberately conservative:
    the clause that the number supported is removed whole, so the result is
    always a complete, readable sentence. When nothing can be removed cleanly
    the bullet is returned unchanged and the caller falls back to the real CV
    bullet instead.
    """
    text = str(bullet or "")
    if not text:
        return text

    def _ungrounded(match: re.Match) -> str:
        token = _normalize_number(match.group(0))
        return match.group(0) if token in numeric_claims else "\x00"

    text = _NUMERIC_CLAIM_RE.sub(_ungrounded, text)
    if "\x00" not in text:
        return text

    # 1. "resulting in a 30% improvement in data throughput" -> "improving data throughput"
    text = re.sub(
        r"\b(?:resulting in|leading to|achieving|delivering|yielding)\s+(?:a|an|the)?\s*\x00\s+"
        r"(improvement|reduction|increase|decrease|drop|gain|growth)\s+in\s+",
        lambda m: {"improvement": "improving ", "reduction": "reducing ",
                   "increase": "increasing ", "decrease": "reducing ",
                   "drop": "reducing ", "gain": "improving ",
                   "growth": "improving "}[m.group(1)] + "the ",
        text, flags=re.IGNORECASE)
    # 2. "improving efficiency 18%" -> "improving efficiency"
    text = re.sub(r"\b(improving|reducing|lowering|increasing|boosting|cutting)\s+"
                  r"([a-zA-Z0-9 ,\-]{2,30}?)\s*\x00\b", r"\1 \2", text, flags=re.IGNORECASE)
    # 3. "improving search relevancy by 35%" -> "improving search relevancy"
    text = re.sub(r"\s+by\s+\x00", "", text)
    # 3b. a trailing clause that only the number supported:
    #     "..., processing over 100,000 queries per day." -> "..."
    text = re.sub(r",\s*[a-zA-Z][a-zA-Z ]{0,24}\s+over\s+\x00[^,.]*", "", text)
    text = re.sub(r",\s*[a-zA-Z][a-zA-Z ]{0,24}\s+(?:up to|over|around|about)\s+\x00[^,.]*", "", text)
    # 4. "with 1.5x faster TTI" -> "with measurably faster TTI"
    text = re.sub(r"\b(?:a|an|the)?\s*\x00\s+(?=faster|speedup|speed-up|higher|lower|better|quicker)",
                  "measurably ", text, flags=re.IGNORECASE)
    # 5. a metric that carried the whole trailing clause: drop that clause,
    #    including the "to improve X, Y and Z" purpose tail it introduced.
    #    The tail is removed first so it cannot be left dangling.
    text = re.sub(r",\s*to\s+improve\s+[a-zA-Z0-9 ,\-]{3,60}", "", text)
    text = re.sub(r"\s+to\s+improve\s+[a-zA-Z0-9 ,\-]{3,60}", "", text)
    text = re.sub(r",\s*(?:resulting in|leading to|yielding|achieving|delivering)\s+"
                  r"(?:a|an|the)?\s*\x00[^,.]*", "", text)
    # 6. anything left over
    text = re.sub(r"\s*\x00[^,.]*", "", text)

    # tidy
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;])", r"\1", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s*,\s*\.", ".", text)
    text = text.strip()
    if not text or text.endswith((",", "and", "to", "in", "for", "the")):
        return ""  # unusable: caller falls back to the real CV bullet
    return text


# --- Domain vocabulary grounding ---------------------------------------------
# A tailored bullet can pass the number and stack checks while still inventing a
# whole field of work. Example seen on a Stripe Abuse Research Engineer resume:
# "Developed automated threat hunting workflows ... reducing the false positives"
# and "Led a team of 5 engineers in building a real-time fraud detection system".
# Python and JavaScript are in the CV, so the stack check passed, but fraud
# detection and threat hunting are not Alaa's work.
#
# The fix: a tailored bullet may not introduce domain vocabulary that does not
# already appear in the CV. Generic engineering language is allowed.

# Words that carry no domain meaning on their own.
_GENERIC_WORDS = frozenset("""
a an the and or of to in on at for with without from by as is are was were be been being
this that these those it its their his her they them we us our you your i me my
develop developed develops building built builds creating created creates creating
implement implemented implements implementing design designed designs designing
engineer engineered engineers engineering lead led leads leading direct directed directs
deliver delivered delivers delivering ship shipped shipping launch launched
manage managed managing coordinate coordinated coordinating own owned owns
improve improved improves improving reduce reduced reduces reducing increase increased
enabling enable enables support supported supports maintain maintained maintains
standardize standardized standardizing translate translated translating collaborate
collaborated collaborating partner partnered prepare prepared preparing
introduce introduced introducing ran run runs migrate migrated migrated
scale scaled scaling configure configured configuring automate automated automating
deploy deployed deploying monitor monitored monitoring test tested testing
document documented documenting present presented present
across within using use used via per each every all any some more less
production prod enterprise platform product system service service services
team teams work working workflow workflows process processes pipeline pipelines
application applications app apps component components module modules
customer customers client clients end users user users business company
data code api apis web web-based software technology technologies
real-time high-traffic concurrent scalable robust reliable modern flexible secure
measurable metric metrics scope impact scale performance reliability maintainability
velocity delivery monitoring observability latency throughput
day-to-day hands-on end-to-end full-stack full stack
one two three four five six seven eight nine ten
first second third new current existing key core main primary secondary
""".split())

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{2,}")


def cv_vocabulary(profile: dict) -> set[str]:
    """Every meaningful word that appears in the CV.

    Compound tokens are split on their separators, so "LLM/RAG" contributes
    both "llm" and "rag" rather than an unmatched "llm/rag".
    """
    corpus = cv_grounding_corpus(profile).lower()
    words = set()
    for token in re.findall(r"[a-z][a-z0-9+#.-]{2,}", corpus):
        token = token.rstrip(".")
        words.add(token)
        for part in re.split(r"[/#+.-]", token):
            if len(part) >= 3:
                words.add(part)
    return words


def novel_domain_terms(bullet: str, vocabulary: set[str]) -> list[str]:
    """Domain words in a bullet that do not appear in the CV."""
    novel = []
    for match in _WORD_RE.finditer(str(bullet or "")):
        token = match.group(0).lower().rstrip(".")
        parts = [p for p in re.split(r"[/#+.-]", token) if len(p) >= 3] or [token]
        for part in parts:
            if part in vocabulary or part in _GENERIC_WORDS:
                continue
            if len(part) < 5:
                continue
            novel.append(part)
    return sorted(set(novel))


# A bullet may introduce at most this many new domain words before it is
# treated as claiming work the candidate never did.
NOVEL_TERM_LIMIT = 2
