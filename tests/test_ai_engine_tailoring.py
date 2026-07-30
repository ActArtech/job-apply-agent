import ai_engine
from ai_engine import ApplicationPackage


NEURON7_JD = """
AI/ML & NLP (Implementation Focus)
Integrate internal ML pipelines, LLM components, and retrieval systems into customer environments.
Work with RAG pipelines, embedding workflows, or NLP modules as needed for solution deployment.
Collaborate with ML Engineers to productionize models and optimize performance.
Build Python services, APIs, customer-specific connectors, data ingestion pipelines, and cloud deployments.
"""


def _generic_backend_package():
    return ApplicationPackage(
        company="Neuron7",
        role="Senior Customer Implementation Engineer",
        match_score=92,
        summary="",
        headline="Backend Engineer | Python · FastAPI · APIs | @Hughes · ex-IndiaMart",
        tailored_experience=[
            {
                "company": "Hughes Network Systems (via Teleperformance)",
                "role": "Software Development Engineer II",
                "bullets": [
                    "Built backend APIs with Python and FastAPI for production workflows.",
                    "Optimized PostgreSQL queries and service reliability for production systems.",
                ],
            }
        ],
        tailored_skills={
            "Languages": ["Python", "SQL"],
            "Backend": ["FastAPI", "REST APIs"],
            "Databases": ["PostgreSQL", "Redis"],
        },
        keywords_matched=["Python", "FastAPI", "REST APIs"],
        keywords_missing=[],
        email_subject="Neuron7 application",
        email_body="Hi",
    )


def _skills_only_ai_package():
    pkg = _generic_backend_package()
    pkg.headline = "AI Implementation Engineer | LLM · RAG · NLP | @Hughes · ex-IndiaMart"
    pkg.tailored_skills = {
        "Languages": ["Python", "SQL"],
        "Backend": ["FastAPI", "REST APIs"],
        "Concepts": ["AI/ML Integration", "LLM", "RAG", "NLP", "Embedding Workflows"],
    }
    return pkg


def _weak_ai_bullet_package():
    pkg = _generic_backend_package()
    pkg.headline = "AI Implementation Engineer | LLM · RAG · NLP | @Hughes · ex-IndiaMart"
    pkg.tailored_experience = [
        {
            "company": "Hughes Network Systems (via Teleperformance)",
            "role": "Software Development Engineer II",
            "bullets": [
                "Worked on AI/ML implementation.",
                "Worked on LLM/RAG retrieval.",
                "Worked on NLP and embedding workflows.",
                "Worked on customer implementation.",
                "Worked on enterprise integrations and cloud deployment.",
            ],
        }
    ]
    pkg.tailored_skills = {
        "Languages": ["Python", "SQL"],
        "Backend": ["FastAPI", "REST APIs"],
        "Concepts": ["AI/ML Integration", "LLM", "RAG", "NLP", "Embedding Workflows"],
    }
    return pkg


def _retrieval_only_ai_package():
    pkg = _generic_backend_package()
    pkg.tailored_experience = [
        {
            "company": "Hughes Network Systems (via Teleperformance)",
            "role": "Software Development Engineer II",
            "bullets": [
                "Integrated customer-facing FastAPI services with AI/ML workflow implementation for enterprise deployment, improving page-load performance 23% across production rollouts.",
                "Built Celery/Redis event pipelines for retrieval-ready operational workflows, reducing manual intervention 15% in real-time troubleshooting.",
                "Engineered audit logs with NLP and embedding-ready data processing for AI-assisted investigation workflows, reducing database latency 25%.",
                "Designed REST APIs for enterprise connector workflows and customer-specific implementation surfaces, improving backend throughput 13% under concurrent workloads.",
                "Automated AWS cloud deployments with Docker and CI/CD, cutting setup time 20% and strengthening production reliability.",
            ],
        }
    ]
    return pkg


def _provider_payload(ai_specific: bool):
    if ai_specific:
        headline = "AI Implementation Engineer | LLM · RAG · Python APIs | @Hughes · ex-IndiaMart"
        skills = {
            "Languages": ["Python", "SQL"],
            "Backend": ["FastAPI", "REST APIs", "Django"],
            "Concepts": ["AI/ML Integration", "LLM", "RAG", "NLP", "Embedding Workflows"],
        }
        hughes = [
            "Integrated Python services with AI/ML workflow plumbing, LLM/RAG retrieval paths, and customer deployment hooks for production rollouts across enterprise environments.",
            "Built NLP and embedding-ready data ingestion flows over event logs and Redis queues, reducing manual triage 15% for AI-assisted troubleshooting.",
            "Partnered with product and engineering stakeholders to productionize ML pipeline integration surfaces with logs, metrics, and root-cause analysis for reliable releases.",
            "Designed FastAPI services and PostgreSQL-backed connector layers for high-throughput enterprise integrations under concurrent workloads.",
            "Supported cloud deployment, CI/CD, and observability for implementation-specific backend services, cutting setup time 20%.",
        ]
        indiamart = [
            "Delivered API-driven product features across backend and frontend surfaces for high-traffic marketplace workflows.",
            "Optimized SQL-backed service integrations and data flows for performance and maintainability.",
            "Collaborated with product and business teams to translate requirements into production releases.",
            "Improved reusable engineering patterns through code review, testing, and release support.",
        ]
        project = [
            "Built an enterprise monitoring platform with FastAPI, PostgreSQL, async jobs, dashboards, and AI-assisted investigation workflows, reducing database latency 25%.",
            "Designed audit, alerting, and NLP-ready analysis flows that turn system activity into retrieval-ready operational insights for production support.",
            "Implemented API orchestration and observability patterns for production-grade troubleshooting workflows across distributed services.",
        ]
    else:
        headline = "Backend Engineer | Python · FastAPI · APIs | @Hughes · ex-IndiaMart"
        skills = {
            "Languages": ["Python", "SQL"],
            "Backend": ["FastAPI", "REST APIs", "Django"],
            "Databases": ["PostgreSQL", "Redis"],
        }
        hughes = [
            "Built Python backend APIs and integration services for production workflows.",
            "Optimized PostgreSQL queries and service reliability for backend systems.",
            "Implemented FastAPI automation and validation flows for operational tools.",
            "Supported CI/CD releases and production debugging across distributed services.",
            "Collaborated with product and engineering teams to ship maintainable backend features.",
        ]
        indiamart = [
            "Delivered API-driven product features across backend and frontend surfaces.",
            "Optimized SQL-backed service integrations and data flows.",
            "Collaborated with product and business teams on production releases.",
            "Improved reusable engineering patterns through code review and testing.",
        ]
        project = [
            "Built an enterprise monitoring platform with FastAPI, PostgreSQL, async jobs, and dashboards.",
            "Designed audit, alerting, and analysis flows for operational insights.",
            "Implemented API orchestration and observability patterns for troubleshooting workflows.",
        ]

    return {
        "company": "Neuron7",
        "role": "Senior Customer Implementation Engineer",
        "headline": headline,
        "matchScore": 92,
        "keywordsMatched": ["Python", "FastAPI"],
        "keywordsMissing": [],
        "tailoredSkills": skills,
        "tailoredExperience": [
            {
                "company": "Hughes Network Systems (via Teleperformance)",
                "role": "Software Development Engineer II",
                "bullets": hughes,
            },
            {"company": "IndiaMart", "role": "Software Development Engineer", "bullets": indiamart},
            {
                "company": "AtherMind IntelliDAM --- Enterprise Database Activity Monitoring Platform (Project)",
                "role": "Product Project",
                "bullets": project,
            },
        ],
        "emailSubject": "Neuron7 application",
        "emailBody": "Hi",
    }


def test_extract_jd_target_themes_identifies_neuron7_ai_ml_focus():
    themes = ai_engine.extract_jd_target_themes(NEURON7_JD)

    assert "AI/ML implementation" in themes
    assert "LLM/RAG retrieval" in themes
    assert "NLP and embeddings" in themes
    assert "customer implementation" in themes


def test_validate_jd_theme_coverage_fails_generic_backend_resume():
    report = ai_engine.validate_jd_theme_coverage(_generic_backend_package(), NEURON7_JD)

    assert not report["ok"]
    assert "LLM/RAG retrieval" in report["missing_themes"]
    assert "NLP and embeddings" in report["missing_themes"]


def test_validate_jd_theme_coverage_rejects_skills_only_ai_keywords():
    report = ai_engine.validate_jd_theme_coverage(_skills_only_ai_package(), NEURON7_JD)

    assert not report["ok"]
    assert "AI/ML implementation" in report["missing_themes"]
    assert "LLM/RAG retrieval" in report["missing_themes"]
    assert "NLP and embeddings" in report["missing_themes"]
    assert report["theme_coverage_source"] == "experience_project_bullets"


def test_validate_jd_theme_coverage_rejects_non_ats_bullets():
    report = ai_engine.validate_jd_theme_coverage(_weak_ai_bullet_package(), NEURON7_JD)

    assert not report["ok"]
    assert report["ats_weak_bullets"]
    assert report["ats_impact_ratio"] < 1.0


def test_validate_jd_theme_coverage_requires_explicit_llm_or_rag_bullets():
    report = ai_engine.validate_jd_theme_coverage(_retrieval_only_ai_package(), NEURON7_JD)

    assert not report["ok"]
    assert "LLM/RAG retrieval" in report["missing_themes"]


def test_ai_backfill_preserves_indiamart_truthful_product_bullets():
    pkg = _retrieval_only_ai_package()
    pkg.tailored_experience.append(
        {
            "company": "IndiaMart",
            "role": "Software Development Engineer",
            "bullets": [
                "Implemented Python-driven data ingestion and transformation pipelines, supporting AI-ready analytics and ensuring data integrity across critical backend services with measurable efficiency gains for scalable production workloads.",
                "Built backend integrations for production workloads.",
                "Built frontend modules for production workloads.",
                "Improved platform reliability for production workloads.",
            ],
        }
    )

    ai_engine._apply_ai_implementation_bullet_backfill(pkg, NEURON7_JD)
    bullets = "\n".join(pkg.resume_bullets_text().splitlines())

    assert "AI-ready analytics" not in bullets
    assert "1.5x faster TTI" in bullets
    assert "operational efficiency 18%" in bullets


def test_build_prompt_includes_mandatory_jd_target_themes():
    prompt = ai_engine.build_prompt("Neuron7", "Senior Customer Implementation Engineer", NEURON7_JD)

    assert "MANDATORY JD TARGET THEMES" in prompt
    assert "AI/ML implementation" in prompt
    assert "LLM/RAG retrieval" in prompt
    assert "NLP and embeddings" in prompt
    assert "LLM, RAG, retrieval systems" in prompt
    assert "If direct production experience is not supported" in prompt
    assert "experience/project bullets must prove the theme" in prompt
    assert "Do not satisfy this gate with Skills-only keyword stuffing" in prompt
    assert "For AI/ML implementation roles, bullet minimums" in prompt
    assert "LLM/RAG retrieval or retrieval-ready data/API workflows" in prompt
    assert "NLP or embedding-ready log/event/data processing" in prompt


def test_generate_application_retries_when_provider_misses_required_themes(monkeypatch):
    calls = []

    def fake_call_provider(prompt, provider):
        calls.append(prompt)
        return _provider_payload(ai_specific=len(calls) > 1)

    monkeypatch.setattr(ai_engine, "call_provider", fake_call_provider)

    pkg = ai_engine.generate_application(
        company="Neuron7",
        role="Senior Customer Implementation Engineer",
        jd=NEURON7_JD,
    )

    assert len(calls) == 2
    assert "TAILORING COVERAGE FAILED" in calls[1]
    report = ai_engine.validate_jd_theme_coverage(pkg, NEURON7_JD)
    assert report["ok"]
    assert "LLM" in pkg.headline
    assert "RAG" in pkg.headline


def test_generate_application_backfills_ai_theme_bullets_when_retry_still_misses_required_themes(monkeypatch):
    calls = []

    def fake_call_provider(prompt, provider):
        calls.append(prompt)
        return _provider_payload(ai_specific=False)

    monkeypatch.setattr(ai_engine, "call_provider", fake_call_provider)

    pkg = ai_engine.generate_application(
        company="Neuron7",
        role="Senior Customer Implementation Engineer",
        jd=NEURON7_JD,
    )

    assert len(calls) == 2
    assert pkg is not None
    report = ai_engine.validate_jd_theme_coverage(pkg, NEURON7_JD)
    assert report["ok"]
    assert report["ats_impact_ratio"] == 1.0
    bullets = "\n".join(pkg.resume_bullets_text().splitlines())
    assert "LLM/RAG-ready retrieval workflows" in bullets
    assert "NLP and embedding-ready" in bullets
    assert "1.5x faster TTI" in bullets
    assert "AI-ready analytics" not in bullets
