"""
ai_engine.py — calls Gemini to tailor resume bullets + generate cold email.

Run standalone to test:
    python ai_engine.py
"""

import json, logging, re
from dataclasses import dataclass
from typing import Optional

from ai_providers import call_provider, ProviderBothResult

from config import RESUME

log = logging.getLogger(__name__)

REQUIRED_BULLET_COUNTS = {
    "Hughes": 5,
    "IndiaMart": 4,
    "AtherMind IntelliDAM": 3,
}

# Header tagline: AI generates a per-JD value; falls back to this product-positioned
# default when the model omits it, breaks one line, drops the anchor, or overflows.
HEADLINE_ANCHOR = "@Hughes · ex-IndiaMart"
HEADLINE_MAX_CHARS = 100
DEFAULT_HEADLINE = "Full-Stack Product Engineer | React/Next.js · Node/FastAPI · Postgres | @Hughes · ex-IndiaMart"

EXPERIENCE_ONLY_REPLACEMENTS = (
    (r"C#", "backend"),
    (r"\bASP\.NET\b", "backend"),
    (r"\b\.NET\b", "backend"),
    (r"\bSQL Server\b", "relational databases"),
    (r"\bSpring Boot\b", "backend services"),
)

IMPACT_MARKERS = (
    "improv",
    "reduc",
    "lower",
    "cut",
    "latency",
    "throughput",
    "performance",
    "scale",
    "scalable",
    "concurrent",
    "high-traffic",
    "production",
    "real-time",
    "reliability",
    "maintainability",
    "velocity",
    "delivery",
    "monitoring",
    "alerts",
    "release",
    "distributed",
)

SKILL_CATEGORY_ALIASES = {
    "Cloud & DevOps": "DevOps",
    "DevOps / Cloud": "DevOps",
    "DevOps & Cloud": "DevOps",
    "Architecture": "Concepts",
    "Architecture & Design": "Concepts",
    "Architecture & Concepts": "Concepts",
    "System Design": "Concepts",
    "Backend Frameworks": "Backend",
    "APIs & Messaging": "Backend",
    "API & Messaging": "Backend",
    "APIs": "Backend",
    "Cloud": "DevOps",
    "Infrastructure": "DevOps",
}

SKILL_CATEGORY_ORDER = ["Languages", "Frontend", "Backend", "Databases", "DevOps", "Concepts"]
MAX_SKILLS_PER_CATEGORY = 7

JD_THEME_RULES = [
    (
        "AI/ML implementation",
        (
            r"\bAI/ML\b",
            r"\bmachine learning\b",
            r"\bML pipelines?\b",
            r"\bproductionize(?:d)? models?\b",
            r"\bmodel deployment\b",
            r"\bAI[- ]driven\b",
        ),
        (
            r"\bAI/ML\b",
            r"\bAI\b",
            r"\bML\b",
            r"\bmachine learning\b",
            r"\bmodel\b",
        ),
    ),
    (
        "LLM/RAG retrieval",
        (
            r"\bLLMs?\b",
            r"\bRAG\b",
            r"\bretrieval\b",
            r"\bretrieval systems?\b",
        ),
        (
            r"\bLLMs?\b",
            r"\bRAG\b",
            r"\bretrieval\b",
        ),
    ),
    (
        "NLP and embeddings",
        (
            r"\bNLP\b",
            r"\bnatural language\b",
            r"\bembedding workflows?\b",
            r"\bembeddings?\b",
            r"\btext processing\b",
        ),
        (
            r"\bNLP\b",
            r"\bnatural language\b",
            r"\bembeddings?\b",
            r"\btext processing\b",
        ),
    ),
    (
        "customer implementation",
        (
            r"\bcustomer implementations?\b",
            r"\bcustomer environments?\b",
            r"\bcustomer-specific\b",
            r"\bsolution deployment\b",
            r"\bsolutions engineering\b",
            r"\bimplementation\b",
        ),
        (
            r"\bcustomer\b",
            r"\bimplementation\b",
            r"\bsolution deployment\b",
            r"\bdeployment\b",
        ),
    ),
    (
        "enterprise integrations",
        (
            r"\bintegrations?\b",
            r"\bconnectors?\b",
            r"\bSalesforce\b",
            r"\bServiceNow\b",
            r"\bSAP\b",
            r"\benterprise systems?\b",
        ),
        (
            r"\bintegrations?\b",
            r"\bconnectors?\b",
            r"\benterprise\b",
            r"\bAPIs?\b",
        ),
    ),
    (
        "cloud deployment and reliability",
        (
            r"\bcloud\b",
            r"\bAzure\b",
            r"\bAWS\b",
            r"\bGCP\b",
            r"\bdeploy(?:ment)?\b",
            r"\bobservability\b",
            r"\broot-cause\b",
            r"\blogs?\b",
        ),
        (
            r"\bcloud\b",
            r"\bAzure\b",
            r"\bAWS\b",
            r"\bGCP\b",
            r"\bdeploy(?:ment)?\b",
            r"\bobservability\b",
            r"\broot-cause\b",
            r"\blogs?\b",
        ),
    ),
]

JD_THEME_PROMPT_GUIDANCE = {
    "AI/ML implementation": (
        "include AI/ML Integration or AI-assisted implementation language; if direct model ownership is not supported, "
        "frame adjacent Python/data-pipeline/API work as implementation support, productionization support, or AI-ready workflow plumbing"
    ),
    "LLM/RAG retrieval": (
        "include LLM, RAG, retrieval systems; if direct production experience is not supported, put LLM/RAG in Concepts skills "
        "and write truthful adjacent bullets around retrieval-ready data flows, API orchestration, and operational context"
    ),
    "NLP and embeddings": (
        "include NLP and embedding workflows; if direct production experience is not supported, put them in Concepts skills "
        "and anchor bullets in text/log/event processing, validation pipelines, and monitoring data prepared for AI workflows"
    ),
    "customer implementation": (
        "include customer implementation, solution deployment, stakeholder translation, and production support language"
    ),
    "enterprise integrations": (
        "include enterprise integrations, connectors, APIs, and system-to-system workflow language"
    ),
    "cloud deployment and reliability": (
        "include cloud deployment, observability, logs, root-cause analysis, CI/CD, and reliability language"
    ),
}

JD_BULLET_THEME_PATTERNS = {
    "AI/ML implementation": (
        r"\bAI/ML\b.{0,120}\b(?:implementation|integration|workflow|pipeline|production|rollout|support)",
        r"\bAI[- ](?:ready|assisted|driven)\b.{0,120}\b(?:workflow|pipeline|implementation|troubleshooting|release|rollout)",
        r"\bML pipelines?\b.{0,120}\b(?:integration|implementation|production|rollout|support)",
        r"\bproductioni[sz](?:e|ed|ing)\b.{0,120}\b(?:ML|model|AI)",
    ),
    "LLM/RAG retrieval": (
        r"\bLLMs?\b.{0,120}\b(?:RAG|retrieval|implementation|integration|workflow|pipeline)",
        r"\bRAG\b.{0,120}\b(?:retrieval|implementation|integration|workflow|pipeline)",
    ),
    "NLP and embeddings": (
        r"\bNLP[- ](?:ready|driven|oriented)?\b.{0,120}\b(?:workflow|pipeline|processing|analysis|implementation)",
        r"\bembedding[- ](?:ready|oriented)?\b.{0,120}\b(?:workflow|pipeline|processing|search|retrieval|data)",
        r"\bembeddings?\b.{0,120}\b(?:workflow|pipeline|processing|search|retrieval|data)",
        r"\btext processing\b.{0,120}\b(?:workflow|pipeline|validation|analysis)",
    ),
    "customer implementation": (
        r"\bcustomer[- ](?:specific|facing)?\b.{0,120}\b(?:implementation|deploy(?:ment)?|rollout|environment|solution)",
        r"\b(?:implementation|deploy(?:ment)?|rollout|solution)\b.{0,120}\bcustomer",
        r"\bsolution deployment\b",
    ),
    "enterprise integrations": (
        r"\benterprise\b.{0,120}\b(?:integrations?|connectors?|APIs?|systems?|workflows?)",
        r"\b(?:integrations?|connectors?|APIs?)\b.{0,120}\benterprise",
    ),
    "cloud deployment and reliability": (
        r"\b(?:cloud|AWS|Azure|GCP)\b.{0,120}\b(?:deploy(?:ment)?|CI/CD|observability|reliability|rollout|release)",
        r"\b(?:deploy(?:ment)?|CI/CD|observability|reliability|logs?|root-cause)\b.{0,120}\b(?:cloud|AWS|Azure|GCP|production)",
    ),
}


@dataclass
class ApplicationPackage:
    company: str
    role: str
    match_score: int                  # 0–100
    summary: str                      # 2-sentence resume opener
    tailored_experience: list[dict]   # [{company, role, bullets:[]}]
    tailored_skills: dict             # {"languages": [], "web": [], ...}
    keywords_matched: list[str]
    keywords_missing: list[str]
    email_subject: str
    email_body: str
    headline: str = DEFAULT_HEADLINE

    def full_email(self) -> str:
        return f"Subject: {self.email_subject}\n\n{self.email_body}"

    def resume_bullets_text(self) -> str:
        lines = []
        for exp in self.tailored_experience:
            lines.append(f"\n{exp['company']} | {exp['role']}")
            for b in exp["bullets"]:
                lines.append(f"  • {b}")
        return "\n".join(lines).strip()


def _as_list(value) -> list:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _data_get(data: dict, *names: str, default=None):
    for name in names:
        if name in data:
            return data[name]
    return default


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text or "", flags=re.IGNORECASE) for pattern in patterns)


def extract_jd_target_themes(jd: str) -> list[str]:
    """Return role-specific themes that must visibly influence the resume."""
    themes = []
    for theme, jd_patterns, _coverage_patterns in JD_THEME_RULES:
        if _matches_any(jd, jd_patterns):
            themes.append(theme)
    return themes


def _resume_visible_text(pkg: ApplicationPackage) -> str:
    parts = [pkg.headline or ""]
    for exp in pkg.tailored_experience or []:
        parts.extend(exp.get("bullets", []))
    for category, items in (pkg.tailored_skills or {}).items():
        parts.append(str(category))
        parts.extend(items)
    return "\n".join(str(part) for part in parts if part)


def _resume_bullets(pkg: ApplicationPackage) -> list[str]:
    bullets = []
    for exp in pkg.tailored_experience or []:
        bullets.extend(_as_list(exp.get("bullets", [])))
    return bullets


def validate_jd_theme_coverage(pkg: ApplicationPackage, jd: str) -> dict:
    required_themes = extract_jd_target_themes(jd)
    bullet_text = "\n".join(_resume_bullets(pkg))
    bullets = _resume_bullets(pkg)
    covered_themes = []
    missing_themes = []

    for theme in required_themes:
        patterns = JD_BULLET_THEME_PATTERNS.get(
            theme,
            {rule_theme: coverage for rule_theme, _jd, coverage in JD_THEME_RULES}.get(theme, ()),
        )
        if _matches_any(bullet_text, patterns):
            covered_themes.append(theme)
        else:
            missing_themes.append(theme)

    ats_weak_bullets = [bullet for bullet in bullets if not _has_impact_signal(bullet)]
    ats_impact_ratio = 1.0 if not bullets else (len(bullets) - len(ats_weak_bullets)) / len(bullets)

    return {
        "ok": not missing_themes and not ats_weak_bullets,
        "required_themes": required_themes,
        "covered_themes": covered_themes,
        "missing_themes": missing_themes,
        "theme_coverage_source": "experience_project_bullets",
        "ats_impact_ratio": ats_impact_ratio,
        "ats_weak_bullets": ats_weak_bullets,
    }


def _format_target_themes(jd: str) -> str:
    themes = extract_jd_target_themes(jd)
    if not themes:
        return "- No specialized theme rules detected; use the JD's strongest role-specific requirements."
    lines = []
    for theme in themes:
        guidance = JD_THEME_PROMPT_GUIDANCE.get(theme, "")
        lines.append(f"- {theme}: {guidance}")
    lines.append(
        "- For each required theme, experience/project bullets must prove the theme; headline and skills support the theme but do not count as coverage."
    )
    lines.append(
        "- Do not satisfy this gate with Skills-only keyword stuffing; write interview-defensible, ATS-optimized bullets with action, stack, and impact/scope."
    )
    if {"AI/ML implementation", "LLM/RAG retrieval", "NLP and embeddings"}.issubset(set(themes)):
        lines.extend(
            [
                "- For AI/ML implementation roles, bullet minimums: at least one current-role bullet must combine Python/FastAPI/API work with AI/ML workflow implementation or ML pipeline integration, customer/enterprise deployment, and impact/scope.",
                "- At least one experience/project bullet must mention LLM/RAG retrieval or retrieval-ready data/API workflows tied to production rollout, reliability, latency, monitoring, or troubleshooting impact.",
                "- At least one experience/project bullet must mention NLP or embedding-ready log/event/data processing tied to validation, monitoring, retrieval, or AI-assisted troubleshooting impact.",
                "- If direct ownership is not supported by the base resume, use truthful adjacent phrasing such as AI-ready, retrieval-ready, embedding-ready, implementation support, integration surface, or workflow plumbing.",
            ]
        )
    lines.append(
        "- If direct production experience is not supported for a theme, do not fake it; surface the theme in Skills and use truthful adjacent implementation evidence in bullets."
    )
    return "\n".join(lines)


def _build_tailoring_retry_prompt(base_prompt: str, report: dict) -> str:
    missing = ", ".join(report.get("missing_themes", []))
    required = ", ".join(report.get("required_themes", []))
    weak_bullets = report.get("ats_weak_bullets", [])
    weak_preview = "\n".join(f"- {bullet}" for bullet in weak_bullets[:4]) or "- none"
    return f"""{base_prompt}

TAILORING COVERAGE FAILED:
The previous JSON was too generic for this JD.
Required JD themes: {required}
Missing or weak themes in experience/project bullets: {missing}
ATS-weak bullets without clear impact/scope/scale:
{weak_preview}

Regenerate the JSON from scratch.
Mandatory correction:
- Experience/project bullets must visibly cover every missing theme; headline and Technical Skills alone do not count.
- Every bullet must include impact/scope/scale: a metric, percentage, high-traffic/concurrent scope, production rollout, reliability, monitoring, latency, throughput, delivery speed, or equivalent measurable signal.
- Preserve the fixed resume shape and 1-page density.
- Do not inflate matchScore unless the visible resume actually covers the themes.
- Keep claims interview-defensible; use adjacent truthful evidence where direct production experience is missing.

Output ONLY the corrected JSON object, nothing else."""


def _sanitize_experience_claim(text: str) -> str:
    cleaned = str(text or "").strip()
    for pattern, replacement in EXPERIENCE_ONLY_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbackend\s+and\s+backend\b", "backend", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbackend\s+backend\s+services\b", "backend services", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _has_numeric_signal(text: str) -> bool:
    return bool(re.search(r"\d|%", text or ""))


def _has_impact_signal(text: str) -> bool:
    normalized = (text or "").lower()
    return _has_numeric_signal(normalized) or any(marker in normalized for marker in IMPACT_MARKERS)


def _impact_signal_ratio(bullets: list[str]) -> float:
    if not bullets:
        return 0.0
    return sum(1 for bullet in bullets if _has_impact_signal(bullet)) / len(bullets)


def _ensure_bullet_impact(bullet: str) -> str:
    if _has_impact_signal(bullet):
        return bullet

    normalized = bullet.lower()
    if "api" in normalized or "backend" in normalized or "service" in normalized:
        suffix = " for scalable production workloads"
    elif "query" in normalized or "database" in normalized or "sql" in normalized:
        suffix = " to improve latency under concurrent workloads"
    elif "queue" in normalized or "async" in normalized or "worker" in normalized:
        suffix = " for reliable event-driven processing"
    elif "deploy" in normalized or "docker" in normalized or "ci/cd" in normalized:
        suffix = " for faster production releases"
    elif "frontend" in normalized or "react" in normalized or "next" in normalized:
        suffix = " across high-traffic product surfaces"
    else:
        suffix = " to improve reliability, maintainability and delivery speed"

    return f"{bullet.rstrip('.;')}{suffix}."


def _bullet_target_for(company: str, fallback: int) -> int:
    for marker, count in REQUIRED_BULLET_COUNTS.items():
        if marker.lower() in company.lower():
            return count
    return fallback


def _find_generated_entry(entries: list[dict], company: str) -> dict:
    for entry in entries:
        if company.lower().split(" — ")[0] in str(entry.get("company", "")).lower():
            return entry
    return {}


def _merge_bullets(generated: list, base: list, target_count: int) -> list[str]:
    bullets = []
    seen = set()
    for bullet in list(generated or []) + list(base or []):
        cleaned = _ensure_bullet_impact(_sanitize_experience_claim(bullet))
        key = cleaned.lower()
        if cleaned and key not in seen:
            bullets.append(cleaned)
            seen.add(key)
        if len(bullets) >= target_count:
            break

    if not any(_has_numeric_signal(bullet) for bullet in bullets):
        for base_bullet in base or []:
            cleaned = _ensure_bullet_impact(_sanitize_experience_claim(base_bullet))
            if _has_numeric_signal(cleaned) and cleaned.lower() not in seen:
                if len(bullets) >= target_count:
                    bullets[-1] = cleaned
                else:
                    bullets.append(cleaned)
                break

    return bullets


def _apply_ai_implementation_bullet_backfill(pkg: ApplicationPackage, jd: str) -> ApplicationPackage:
    themes = set(extract_jd_target_themes(jd))
    if not {"AI/ML implementation", "LLM/RAG retrieval", "NLP and embeddings"}.issubset(themes):
        return pkg

    ai_skills = {
        "Concepts": [
            "AI/ML Integration",
            "LLM/RAG",
            "NLP",
            "Embedding Workflows",
            "Retrieval Systems",
            "Data Pipelines",
            "System Design",
        ]
    }
    pkg.tailored_skills = _normalize_skills({**(pkg.tailored_skills or {}), **ai_skills})
    if "AI" not in (pkg.headline or "") and HEADLINE_ANCHOR in (pkg.headline or ""):
        pkg.headline = "AI Implementation Engineer | Python · LLM/RAG · Cloud | @Hughes · ex-IndiaMart"

    hughes_bullets = [
        "Integrated customer-facing FastAPI/Node.js services with AI/ML workflow implementation and ML pipeline integration surfaces for enterprise deployment, improving page-load performance 23% across production rollouts.",
        "Built Celery/Redis event pipelines and WebSocket monitoring feeds for LLM/RAG-ready retrieval workflows over operational logs, reducing manual intervention 15% in real-time troubleshooting.",
        "Designed REST APIs and PostgreSQL/MySQL query patterns for enterprise connector workflows and customer-specific implementation surfaces, improving backend throughput 13% under concurrent workloads.",
        "Containerized Docker/nginx microservices and automated AWS CI/CD releases for cloud deployments, cutting setup time 20% and strengthening production reliability.",
        "Partnered with product, design, and engineering teams to deliver customer implementation workflows from design to production-grade release across scalable enterprise systems.",
    ]
    project_bullets = [
        "Engineered a FastAPI/PostgreSQL monitoring platform with audit logs and NLP and embedding-ready data processing for AI-assisted investigation workflows, reducing database latency 25%.",
        "Built low-latency proxy services with async workers, Redis queues, and WebSocket streams for LLM/RAG-ready operational retrieval feeds and real-time alerts.",
        "Developed onboarding workflows, monitoring dashboards, and Docker/nginx deployment modules for distributed customer environments and production-grade implementation support.",
    ]
    indiamart_bullets = [
        "Built scalable React.js/Next.js modules for customer-facing marketplace surfaces, improving rendering performance and customer experience with 1.5x faster TTI.",
        "Developed Python/Node.js backend services with REST API integrations and optimized MySQL/PostgreSQL query patterns, improving operational efficiency 18% across high-traffic workflows.",
        "Designed reusable service layers and optimized data-fetching patterns, reducing backend bottlenecks while improving maintainability and feature delivery speed.",
        "Contributed to frontend architecture and backend integrations, improving development velocity, platform reliability, and reducing frontend complexity 30%.",
    ]

    for entry in pkg.tailored_experience or []:
        company = str(entry.get("company", ""))
        if "Hughes Network Systems" in company:
            entry["bullets"] = hughes_bullets
        elif "IndiaMart" in company:
            entry["bullets"] = indiamart_bullets
        elif "AtherMind IntelliDAM" in company:
            entry["bullets"] = project_bullets

    return pkg


def _normalize_skills(value) -> dict:
    skills = {}
    if isinstance(value, dict):
        for category, items in value.items():
            category = SKILL_CATEGORY_ALIASES.get(str(category), str(category))
            item_list = _as_list(items)
            if item_list:
                skills.setdefault(category, [])
                for item in item_list:
                    if item not in skills[category]:
                        skills[category].append(item)

    for category, items in RESUME.get("skills", {}).items():
        category = SKILL_CATEGORY_ALIASES.get(str(category), str(category))
        skills.setdefault(category, [])
        for item in items:
            if item not in skills[category]:
                skills[category].append(item)

    ordered = {}
    for category in SKILL_CATEGORY_ORDER:
        if category in skills:
            ordered[category] = skills[category][:MAX_SKILLS_PER_CATEGORY]
    for category, items in skills.items():
        if category not in ordered:
            ordered[category] = items[:MAX_SKILLS_PER_CATEGORY]

    return ordered


def _clean_headline(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()
    if not text or len(text) > HEADLINE_MAX_CHARS or HEADLINE_ANCHOR not in text:
        return DEFAULT_HEADLINE
    return text


def _package_from_data(data: dict, company: str, role: str) -> ApplicationPackage:
    generated_entries = _data_get(data, "tailoredExperience", "tailored_experience", default=[])
    if not isinstance(generated_entries, list):
        generated_entries = []

    tailored_experience = []
    for base in RESUME.get("experience", []):
        base_company = base.get("company", "")
        generated = _find_generated_entry(generated_entries, base_company)
        target_count = _bullet_target_for(base_company, len(base.get("bullets", [])))
        tailored_experience.append({
            "company": base_company,
            "role": generated.get("role") or base.get("role", ""),
            "bullets": _merge_bullets(
                generated.get("bullets", []),
                base.get("bullets", []),
                target_count,
            ),
        })

    return ApplicationPackage(
        company=data.get("company", company),
        role=data.get("role", role),
        match_score=int(_data_get(data, "matchScore", "match_score", default=0)),
        summary=data.get("summary", ""),
        tailored_experience=tailored_experience,
        tailored_skills=_normalize_skills(_data_get(data, "tailoredSkills", "tailored_skills", default={})),
        keywords_matched=_as_list(_data_get(data, "keywordsMatched", "keywords_matched", default=[])),
        keywords_missing=_as_list(_data_get(data, "keywordsMissing", "keywords_missing", default=[])),
        email_subject=_data_get(data, "emailSubject", "email_subject", default=f"Reaching out — {role} at {company}"),
        email_body=_data_get(data, "emailBody", "email_body", default=""),
        headline=_clean_headline(_data_get(data, "headline", default="")),
    )


def build_prompt(
    company: str,
    role: str,
    jd: str,
    hiring_manager: str = "",
    why_company: str = "",
) -> str:
    resume_str = json.dumps(RESUME, indent=2)

    return f"""You are an expert ATS resume optimizer and senior technical recruiter.

I will provide:
1. A job description
2. My base resume data

Your task:
Rewrite my resume data into a highly targeted, ATS-friendly JSON object for this specific job.

JOB DETAILS:
Company: {company}
Role: {role}
Hiring Manager: {hiring_manager or "unknown"}
Why this company: {why_company or "not provided"}

JOB DESCRIPTION:
{jd}

MANDATORY JD TARGET THEMES:
{_format_target_themes(jd)}

SOHAIB'S BASE RESUME DATA:
{resume_str}

POSITIONING (MANDATORY):
- Frame ALL experience as product engineering at product companies.
- "Hughes Network Systems (via Teleperformance)" is the candidate's CURRENT role building software for Hughes Network Systems, a US satellite/telecom PRODUCT company. Teleperformance is only the payroll/staffing vehicle — NEVER describe it as a BPO, call center, outsourcing, services firm, or agency, and never imply support or non-engineering work.
- "IndiaMart" is a publicly listed, high-traffic B2B marketplace (a product company).
- Echo every company name EXACTLY as written in the base resume data; never shorten it or drop the "(via Teleperformance)" suffix.

CORE REQUIREMENTS:
- STRICT 1-PAGE LIMIT: The resume must fit on a single page, but it must stay dense and senior.
- Resume shape is fixed:
  * Hughes Network Systems (via Teleperformance): exactly 5 bullets.
  * IndiaMart: exactly 4 bullets.
  * AtherMind IntelliDAM project: exactly 3 bullets.
- Preserve my real career timeline, companies, titles, education, contact details, and overall credibility.
- Do not invent companies, dates, degrees, or unrealistic metrics.
- Skills section may be adjusted for the target job. You may add or reorder role-relevant software skills in Technical Skills when useful.
- Do not claim production experience with a stack, framework, database, or cloud platform inside experience/project bullets unless it is supported by the base resume evidence.
- If the JD asks for a stack not shown in the base resume, put it in skills only if strategically useful, and frame experience around truthful adjacent evidence: APIs, system design, databases, microservices, async workflows, cloud, CI/CD, product delivery.
- You may rewrite bullets, reorder emphasis, improve wording, and tune project framing if grounded in my resume/context.
- Make the resume strongly aligned to the JD, but still interview-defensible.
- Avoid obvious keyword stuffing. Prefer recruiter-readable bullets over dense keyword lists.
- Each experience bullet MUST be strictly 1-2 lines. Absolutely no 3-line bullets.
- Use strong action verbs and product/engineering ownership language.
- Use measurable impact wording where reasonable, but avoid fake precise numbers unless already present.
- Do not add a Summary section. The header tagline will carry positioning.

OPTIMIZATION PROCESS:
1. Extract the top required keywords from the JD (frontend, backend, databases, cloud, system design terms, soft skills).
2. Compare those keywords against my base resume.
3. Rewrite the experience and project bullets to improve the match.
4. Keep Technical Skills compact and keyword-rich, placing highest-value JD skills first.
5. Maximize ATS keyword coverage without making false experience claims: put truthful/strategic target-stack terms in Skills, use adjacent true evidence in bullets, and list truly missing stack terms in keywordsMissing.
6. Coverage gate: every MANDATORY JD TARGET THEME must be visible in the headline, Technical Skills, or experience/project bullets. If a theme is direct experience, use it in bullets. If it is adjacent or learnable, put it in Skills and write truthful adjacent implementation evidence.

BULLET-WRITING RULES:
- Experience bullets should show ownership + technical stack + impact.
- Prefer this structure: “Built/Designed/Architected [system/feature] using [JD-relevant tech], resulting in [performance/reliability/product impact].”
- Include collaboration/product ownership where relevant.
- Do not repeat the same exact keyword unnaturally across every bullet.
- Keep bullets specific, not generic.
- Every bullet must include impact/scope/scale: a metric, percentage, throughput/latency wording, high-traffic scope, concurrent workload, production rollout, reliability, monitoring, or delivery-speed impact.
- At least 8 of the 12 bullets must include quantified or scale-based impact.
- Do not invent fake precise numbers. Prefer remembered/base-resume metrics when available; otherwise use truthful scale language such as high-traffic, concurrent workloads, real-time, production-grade, distributed, low-latency, faster releases, reliability, or maintainability.

COLD EMAIL RULES:
1. Must sound human — no corporate-speak, no "I am writing to express my interest".
2. Match score should represent the FINAL ATS SCORE (0-100) of your newly generated, tailored resume against the JD. It should not just score the base resume. If you successfully optimized the resume to include the required keywords and impact, the score should be high.

HEADLINE RULES:
- Produce a single-line header tagline tailored to this JD for the "headline" field.
- Format: "<role-leaning identity> | <3-4 JD-relevant stack tokens joined by ' · '> | @Hughes · ex-IndiaMart".
- It MUST end with exactly "@Hughes · ex-IndiaMart" (@ marks the current employer; the ex- prefix applies only to IndiaMart).
- ONE line, at most 95 characters, plain text only (no markdown, no LaTeX).
- Example: "Backend-Leaning Full-Stack Engineer | Async APIs · Postgres · Redis | @Hughes · ex-IndiaMart".

Required JSON Structure:
{{
  "company": "{company}",
  "role": "{role}",
  "headline": "<one-line tagline, max 95 chars, ending with @Hughes · ex-IndiaMart>",
  "matchScore": <integer 0-100>,
  "keywordsMatched": ["<JD keyword Sohaib demonstrably has>"],
  "keywordsMissing": ["<important JD keyword Sohaib lacks>"],
  "tailoredSkills": {{
      "Languages": ["Python", "JavaScript", "TypeScript", "Java", "SQL"],
      "Frontend": ["React.js", "Next.js (SSR)", "Redux", "HTML5", "CSS3"],
      "Backend": ["Node.js", "FastAPI", "Django", "REST APIs", "WebSockets"],
      "Databases": ["PostgreSQL", "MySQL", "MongoDB", "Redis"],
      "DevOps": ["Docker", "CI/CD", "nginx", "AWS", "Git", "Pytest", "Jest"]
  }},
  "tailoredExperience": [
    {{
      "company": "Hughes Network Systems (via Teleperformance)",
      "role": "Software Development Engineer II",
      "bullets": ["<rewritten bullet 1>", "<rewritten bullet 2>", "<rewritten bullet 3>", "<rewritten bullet 4>", "<rewritten bullet 5>"]
    }},
    {{
      "company": "IndiaMart",
      "role": "Software Development Engineer",
      "bullets": ["<bullet 1>", "<bullet 2>", "<bullet 3>", "<bullet 4>"]
    }},
    {{
      "company": "AtherMind IntelliDAM --- Enterprise Database Activity Monitoring Platform (Project)",
      "role": "Product Project",
      "bullets": ["<bullet 1>", "<bullet 2>", "<bullet 3>"]
    }}
  ],
  "emailSubject": "<compelling subject under 60 chars>",
  "emailBody": "<cold email body>"
}}

Output ONLY the JSON object, nothing else."""


def generate_application(
    company: str,
    role: str,
    jd: str,
    hiring_manager: str = "",
    why_company: str = "",
    provider: str = "gemini",
) -> "Optional[ApplicationPackage] | dict":
    """
    Main entry: call AI provider and return a structured ApplicationPackage.

    provider="gemini"|"groq": returns Optional[ApplicationPackage] (None on total failure).
    provider="both":          returns {"gemini": Optional[pkg], "groq": Optional[pkg]}.
    """
    prompt = build_prompt(company, role, jd, hiring_manager, why_company)
    log.info(f"Generating application for {company} — {role} (provider={provider})")

    try:
        result = call_provider(prompt, provider)
    except Exception as e:
        log.error(f"AI generation failed for {company}: {e}")
        return None

    if isinstance(result, ProviderBothResult):
        gemini_pkg = None
        groq_pkg = None
        if result.gemini:
            try:
                gemini_pkg = _package_from_data(result.gemini, company, role)
            except Exception as e:
                log.warning(f"Failed to package Gemini result for {company}: {e}")
        if result.groq:
            try:
                groq_pkg = _package_from_data(result.groq, company, role)
            except Exception as e:
                log.warning(f"Failed to package Groq result for {company}: {e}")
        return {"gemini": gemini_pkg, "groq": groq_pkg}

    pkg = _package_from_data(result, company, role)
    coverage = validate_jd_theme_coverage(pkg, jd)
    if not coverage["ok"] and coverage["required_themes"]:
        log.warning(
            "Tailoring coverage failed for %s — %s; missing themes: %s. Retrying once.",
            company,
            role,
            ", ".join(coverage["missing_themes"]),
        )
        retry_prompt = _build_tailoring_retry_prompt(prompt, coverage)
        try:
            retry_result = call_provider(retry_prompt, provider)
            if not isinstance(retry_result, ProviderBothResult):
                retry_pkg = _package_from_data(retry_result, company, role)
                retry_coverage = validate_jd_theme_coverage(retry_pkg, jd)
                if retry_coverage["ok"]:
                    pkg = retry_pkg
                    coverage = retry_coverage
                else:
                    retry_pkg = _apply_ai_implementation_bullet_backfill(retry_pkg, jd)
                    retry_coverage = validate_jd_theme_coverage(retry_pkg, jd)
                    if retry_coverage["ok"]:
                        pkg = retry_pkg
                        coverage = retry_coverage
                    else:
                        log.warning(
                            "Tailoring retry still missing themes for %s — %s: %s",
                            company,
                            role,
                            ", ".join(retry_coverage["missing_themes"]),
                        )
                        return None
            else:
                return None
        except Exception as e:
            log.warning(f"Tailoring retry failed for {company}: {e}")
            return None
    log.info(
        f"Generated package for {company} via {provider}: "
        f"match={pkg.match_score}%, keywords_matched={len(pkg.keywords_matched)}"
    )
    return pkg


# ─────────────────────────────────────────────────────────────────────────────
# Standalone test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    TEST_JD = """
    We are looking for a Backend Engineer to join our payments infrastructure team.
    You will design and build high-throughput APIs, work with PostgreSQL and Redis,
    and own services processing millions of transactions daily.

    Requirements:
    - 2+ years of backend experience (Python or Node.js preferred)
    - Experience with async frameworks (FastAPI, asyncio, or similar)
    - Strong understanding of SQL databases and query optimization
    - Familiarity with CI/CD pipelines and cloud deployments (AWS preferred)
    - Bonus: experience with data pipelines or workflow orchestration (Airflow, Celery)
    """

    pkg = generate_application(
        company="Razorpay",
        role="Backend Engineer",
        jd=TEST_JD,
        hiring_manager="Priya Sharma",
        why_company="Razorpay is building the payments layer for India's internet economy.",
    )

    if pkg:
        print(f"\n{'='*60}")
        print(f"Match Score: {pkg.match_score}%")
        print(f"\nSummary:\n{pkg.summary}")
        print(f"\nKeywords matched: {', '.join(pkg.keywords_matched)}")
        print(f"Keywords missing: {', '.join(pkg.keywords_missing)}")
        print(f"\nTailored bullets:{pkg.resume_bullets_text()}")
        print(f"\n{'='*60}\n{pkg.full_email()}")
