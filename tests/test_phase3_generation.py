import ai_engine
from config import RESUME


def test_resume_source_uses_dense_current_profile():
    experience = RESUME["experience"]

    assert experience[0]["company"] == "ActArtech / Keyteller Portfolio"
    assert len(experience[0]["bullets"]) == 5
    assert experience[1]["company"] == "Keyteller"
    assert len(experience[1]["bullets"]) == 4
    assert "Earlier work" in experience[2]["company"]
    assert len(experience[2]["bullets"]) == 3

    all_bullets = " ".join(
        bullet
        for entry in experience
        for bullet in entry["bullets"]
    )
    assert "safety gate" in all_bullets
    assert "68 of 68" in all_bullets
    assert "five business units" in all_bullets
    assert "zero downtime" in all_bullets

    skills = RESUME["skills"]
    assert "TypeScript" in skills["Languages"]
    assert "Python" in skills["Languages"]
    assert "Next.js" in skills["Frontend"]
    assert "PostgreSQL" in skills["Databases"]
    assert "Docker" in skills["DevOps"]
    assert "Agentic Systems" in skills["Concepts"]


def test_build_prompt_allows_skill_targeting_but_protects_experience_truth():
    prompt = ai_engine.build_prompt(
        company="Acme",
        role="Java Backend Engineer",
        jd="Need Java, Spring, APIs, SQL, AWS.",
    )

    assert "Skills section may be adjusted" in prompt
    assert "Do not claim production experience" in prompt
    assert "ActArtech / Keyteller Portfolio: exactly 5 bullets" in prompt
    assert "Keyteller: exactly 4 bullets" in prompt
    assert "Earlier work" in prompt


def test_build_prompt_includes_positioning_and_headline_rules():
    prompt = ai_engine.build_prompt(
        company="Acme",
        role="Backend Engineer",
        jd="Need REST APIs, Postgres, AWS.",
    )

    assert "POSITIONING (MANDATORY)" in prompt
    assert "NEVER describe it as an agency, consultancy, or outsourcing firm" in prompt
    assert "Echo every company name EXACTLY" in prompt
    assert "HEADLINE RULES" in prompt
    assert '"headline"' in prompt
    assert "@ActArtech" in prompt


def test_build_prompt_requires_ats_coverage_and_impact_density():
    prompt = ai_engine.build_prompt(
        company="Acme",
        role="Backend Platform Engineer",
        jd="Need REST APIs, microservices, AWS, Redis, CI/CD, observability.",
    )

    assert "ATS keyword coverage" in prompt
    assert "Every bullet must include impact/scope/scale" in prompt
    assert "At least 8 of the 12 bullets" in prompt
    assert "Do not invent fake precise numbers" in prompt
    assert "keywordsMissing" in prompt


def test_generated_package_keeps_dense_shape_and_sanitizes_experience_claims():
    data = {
        "company": "ACV Auctions",
        "role": "Software Engineer IV",
        "matchScore": 92,
        "summary": "",
        "keywordsMatched": ["C#", "ASP.NET", "SQL Server", "REST APIs"],
        "keywordsMissing": ["Spring Boot"],
        "tailoredSkills": {
            "Languages": ["C#", "Java", "Python", "JavaScript", "SQL"],
            "Backend": ["ASP.NET", "FastAPI", "Node.js", "REST APIs"],
            "Databases": ["SQL Server", "PostgreSQL", "MySQL", "Redis"],
            "DevOps": ["AWS", "Docker", "CI/CD"],
        },
        "tailoredExperience": [
            {
                "company": "ActArtech / Keyteller Portfolio",
                "role": "Software Development Engineer II",
                "bullets": [
                    "Built C# and ASP.NET backend services with SQL Server for customer-facing APIs.",
                ],
            },
            {
                "company": "Keyteller",
                "role": "Software Development Engineer",
                "bullets": [
                    "Developed scalable backend services in Node.js and Python with REST API integrations.",
                ],
            },
            {
                "company": "Earlier work — branding, websites and systems",
                "role": "Product Project",
                "bullets": [
                    "Built low-latency proxy services with event-driven processing and WebSocket streams.",
                ],
            },
        ],
        "emailSubject": "Backend engineer for ACV Auctions",
        "emailBody": "Hi, I can help with backend APIs and distributed systems.",
    }

    pkg = ai_engine._package_from_data(data, "ACV Auctions", "Software Engineer IV")

    assert [entry["company"] for entry in pkg.tailored_experience] == [
        "ActArtech / Keyteller Portfolio",
        "Keyteller",
        "Earlier work — branding, websites and systems",
    ]
    assert [len(entry["bullets"]) for entry in pkg.tailored_experience] == [5, 4, 3]

    experience_text = " ".join(
        bullet
        for entry in pkg.tailored_experience
        for bullet in entry["bullets"]
    )
    assert "C#" not in experience_text
    assert "ASP.NET" not in experience_text
    assert "SQL Server" not in experience_text
    assert "backend services" in experience_text

    assert "C#" in pkg.tailored_skills["Languages"]
    assert "ASP.NET" in pkg.tailored_skills["Backend"]
    assert "SQL Server" in pkg.tailored_skills["Databases"]


def test_generated_package_adds_impact_signal_to_weak_bullets():
    data = {
        "company": "ACV Auctions",
        "role": "Software Engineer IV",
        "matchScore": 88,
        "keywordsMatched": ["REST APIs", "microservices", "AWS"],
        "keywordsMissing": ["C#"],
        "tailoredSkills": {
            "Languages": ["Python", "Java", "SQL"],
            "Backend": ["FastAPI", "Node.js", "REST APIs"],
            "Databases": ["PostgreSQL", "Redis"],
            "DevOps": ["AWS", "Docker", "CI/CD"],
        },
        "tailoredExperience": [
            {
                "company": "ActArtech / Keyteller Portfolio",
                "role": "Software Development Engineer II",
                "bullets": [
                    "Built backend APIs.",
                    "Designed database queries.",
                    "Worked on queues.",
                    "Deployed services.",
                    "Collaborated with teams.",
                ],
            },
            {
                "company": "Keyteller",
                "role": "Software Development Engineer",
                "bullets": [
                    "Built frontend modules.",
                    "Developed backend services.",
                    "Designed service layers.",
                    "Worked on architecture.",
                ],
            },
            {
                "company": "Earlier work — branding, websites and systems",
                "role": "Product Project",
                "bullets": [
                    "Built monitoring platform.",
                    "Developed proxy services.",
                    "Deployed distributed services.",
                ],
            },
        ],
        "emailSubject": "Backend engineer for ACV Auctions",
        "emailBody": "Hi, I can help with backend APIs.",
    }

    pkg = ai_engine._package_from_data(data, "ACV Auctions", "Software Engineer IV")
    bullets = [
        bullet
        for entry in pkg.tailored_experience
        for bullet in entry["bullets"]
    ]

    assert len(bullets) == 12
    assert ai_engine._impact_signal_ratio(bullets) >= 0.8
    assert any("%" in bullet or any(char.isdigit() for char in bullet) for bullet in bullets)
    assert any("production" in bullet.lower() for bullet in bullets)


def test_skill_normalization_merges_equivalent_categories_for_one_page_density():
    skills = ai_engine._normalize_skills({
        "Languages": ["Python", "JavaScript", "SQL"],
        "Backend": ["Node.js", "FastAPI", "REST APIs"],
        "Databases": ["PostgreSQL", "Redis"],
        "DevOps & Cloud": ["Docker", "AWS", "CI/CD"],
        "Architecture & Design": ["Microservices", "System Design"],
        "Backend Frameworks": ["Spring Boot", "FastAPI"],
        "APIs & Messaging": ["REST APIs", "WebSockets"],
        "Architecture & Concepts": ["Distributed Systems"],
    })

    assert "DevOps & Cloud" not in skills
    assert "Architecture & Design" not in skills
    assert "Backend Frameworks" not in skills
    assert "APIs & Messaging" not in skills
    assert "Architecture & Concepts" not in skills
    assert "DevOps" in skills
    assert "Concepts" in skills
    assert "AWS" in skills["DevOps"]
    assert "Docker" in skills["DevOps"]
    assert "System Design" in skills["Concepts"]
    assert "Spring Boot" in skills["Backend"]
    assert "REST APIs" in skills["Backend"]
    assert "Distributed Systems" in skills["Concepts"]
    assert len(skills) <= 6


def test_package_from_data_accepts_saved_snake_case_package():
    data = {
        "company": "ACV Auctions",
        "role": "Software Engineer IV",
        "match_score": 82,
        "keywords_matched": ["REST APIs", "AWS"],
        "keywords_missing": ["C#"],
        "tailored_skills": {
            "Languages": ["Python", "Java", "SQL"],
            "Backend": ["FastAPI", "REST APIs"],
            "DevOps": ["AWS", "Docker"],
        },
        "tailored_experience": [
            {
                "company": "ActArtech / Keyteller Portfolio",
                "role": "Software Development Engineer II",
                "bullets": ["Built backend APIs for production workloads."],
            }
        ],
        "email_subject": "Backend engineer",
        "email_body": "Hi, backend APIs.",
    }

    pkg = ai_engine._package_from_data(data, "ACV Auctions", "Software Engineer IV")

    assert pkg.match_score == 82
    assert pkg.keywords_matched == ["REST APIs", "AWS"]
    assert pkg.keywords_missing == ["C#"]
    assert pkg.email_subject == "Backend engineer"
    assert "AWS" in pkg.tailored_skills["DevOps"]


def test_clean_headline_accepts_valid_anchored_line():
    h = "Backend-Leaning Full-Stack Engineer | Async APIs · Postgres | @ActArtech"
    assert ai_engine._clean_headline(h) == h


def test_clean_headline_falls_back_when_missing():
    assert ai_engine._clean_headline("") == ai_engine.DEFAULT_HEADLINE
    assert ai_engine._clean_headline(None) == ai_engine.DEFAULT_HEADLINE


def test_clean_headline_falls_back_when_anchor_missing():
    assert ai_engine._clean_headline("Backend Engineer | APIs · Postgres") == ai_engine.DEFAULT_HEADLINE


def test_clean_headline_falls_back_when_too_long():
    # Build the over-length string from the real limit and the real anchor so the
    # test does not depend on the anchor's character count.
    too_long = "X" * (ai_engine.HEADLINE_MAX_CHARS + 20) + " | " + ai_engine.HEADLINE_ANCHOR
    assert len(too_long) > ai_engine.HEADLINE_MAX_CHARS
    assert ai_engine._clean_headline(too_long) == ai_engine.DEFAULT_HEADLINE


def test_clean_headline_collapses_whitespace_and_newlines():
    messy = "Backend Engineer  |\n APIs · Postgres | @ActArtech"
    cleaned = ai_engine._clean_headline(messy)
    assert "\n" not in cleaned
    assert "  " not in cleaned
    assert cleaned.endswith("@ActArtech")


def test_package_from_data_extracts_headline():
    data = {
        "headline": "Backend-Leaning Full-Stack Engineer | Async APIs · Postgres | @ActArtech",
    }
    pkg = ai_engine._package_from_data(data, "Acme", "Backend Engineer")
    assert pkg.headline.endswith("@ActArtech")
    assert pkg.headline.startswith("Backend-Leaning")


def test_package_from_data_headline_defaults_when_absent():
    pkg = ai_engine._package_from_data({}, "Acme", "Backend Engineer")
    assert pkg.headline == ai_engine.DEFAULT_HEADLINE
