import csv
from types import SimpleNamespace

import main
import scraper
from scraper import Job


def make_job(
    title="Backend Engineer",
    company="Acme",
    url="https://example.com/job",
    source="wellfound",
    description="Build APIs",
    remote=True,
    location="Remote",
    company_domain="example.com",
    vetting_reason="deterministic filters passed",
):
    job = Job(
        title=title,
        company=company,
        company_domain=company_domain,
        location=location,
        url=url,
        description=description,
        source=source,
        remote=remote,
    )
    job.vetting_reason = vetting_reason
    return job


def test_get_all_jobs_is_phase1_only(monkeypatch):
    monkeypatch.setattr(scraper, "scrape_wellfound", lambda _max: [])
    monkeypatch.setattr(scraper, "scrape_yc", lambda _max: [])
    monkeypatch.setattr(scraper, "scrape_himalayas", lambda _max: [], raising=False)
    monkeypatch.setattr(scraper, "scrape_jobicy", lambda _max: [], raising=False)
    monkeypatch.setattr(scraper, "scrape_adzuna", lambda _max: [], raising=False)
    monkeypatch.setattr(scraper, "scrape_direct_ats", lambda _max: [], raising=False)
    monkeypatch.setattr(
        scraper,
        "scrape_instahyre",
        lambda _max: [
            make_job(
                title="Backend Engineer",
                company="Acme",
                url="https://jobs.test/1",
                location="Bengaluru, India",
                remote=False,
                source="instahyre",
            ),
            make_job(title="Data Scientist", company="Bad Fit", url="https://jobs.test/2", source="instahyre"),
        ],
    )
    monkeypatch.setattr(
        scraper,
        "scrape_remotive",
        lambda _max: [
            make_job(title="Backend Engineer", company="Acme Duplicate", url="https://jobs.test/1", source="remotive"),
            make_job(title="Python Engineer", company="Gamma", url="https://jobs.test/4", source="remotive"),
        ],
        raising=False,
    )
    monkeypatch.setattr(
        scraper,
        "scrape_wwr",
        lambda _max: [
            make_job(title="", company="No Title", url="https://jobs.test/5", source="weworkremotely"),
            make_job(title="QA Engineer", company="QA Co", url="https://jobs.test/6", source="weworkremotely"),
            make_job(title="Frontend Developer", company="Beta", url="https://jobs.test/3", source="weworkremotely"),
        ],
        raising=False,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("phase 1 gather must not call AI vetting, JD fetch, or cache writes")

    monkeypatch.setattr(scraper, "vet_job", forbidden, raising=False)
    monkeypatch.setattr(scraper, "fetch_full_jd", forbidden)
    monkeypatch.setattr(scraper, "save_vetted", forbidden)

    jobs = scraper.get_all_jobs(max_per_source=3)

    assert [job.title for job in jobs] == [
        "Backend Engineer",
        "Python Engineer",
        "Frontend Developer",
    ]
    assert [job.url for job in jobs] == [
        "https://jobs.test/1",
        "https://jobs.test/4",
        "https://jobs.test/3",
    ]
    assert all(job.vetting_reason.startswith("deterministic filters passed") for job in jobs)


def test_phase1_preference_filters():
    india_wfo = make_job(location="Bengaluru, India", remote=False, source="instahyre")
    foreign_remote = make_job(location="United States", remote=True, source="remotive")
    foreign_wfo = make_job(location="San Francisco, CA", remote=False, source="linkedin")
    worldwide_remote = make_job(location="Worldwide", remote=True, source="himalayas")
    service_company = make_job(
        company="Acme IT Services",
        description="We provide consulting, staffing, and outsourced client projects.",
        location="Bengaluru, India",
        remote=False,
        source="instahyre",
    )
    manager_role = make_job(title="Engineering Manager", location="Remote", remote=True)
    team_leader_role = make_job(title="Engineering Team Leader", location="Remote", remote=True)

    assert scraper._company_region(india_wfo) == "india"
    # region is location-based only: a US marker is foreign, a bare "Worldwide" remote is unknown
    assert scraper._company_region(foreign_remote) == "foreign"
    assert scraper._company_region(worldwide_remote) == "unknown"
    assert scraper._work_mode(india_wfo) == "wfo"
    assert scraper._work_mode(make_job(location="Hybrid - Mumbai", remote=False)) == "hybrid"
    assert scraper._passes_phase1_filters(india_wfo) == (
        True,
        "deterministic filters passed: india/wfo",
    )
    assert scraper._passes_phase1_filters(foreign_remote) == (
        True,
        "deterministic filters passed: foreign/remote",
    )
    assert scraper._passes_phase1_filters(foreign_wfo) == (
        False,
        "foreign job is not remote",
    )
    assert scraper._passes_phase1_filters(service_company) == (
        False,
        "service/consulting/staffing company signal",
    )
    assert scraper._passes_phase1_filters(manager_role) == (
        False,
        "management role",
    )
    assert scraper._passes_phase1_filters(team_leader_role) == (
        False,
        "management role",
    )


def test_scrape_himalayas_parses_remote_engineering_jobs(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Python Engineer",
                        "companyName": "HimalayaCo",
                        "applicationLink": "https://himalayas.app/companies/himalayaco/jobs/python-engineer",
                        "description": "<p>Build Python services</p>",
                        "excerpt": "Build Python services",
                        "locationRestrictions": ["Worldwide"],
                        "category": ["Software Development"],
                    },
                    {
                        "title": "Sales Lead",
                        "companyName": "SalesCo",
                        "applicationLink": "https://himalayas.app/jobs/sales",
                        "description": "<p>Sell</p>",
                        "category": ["Sales"],
                    },
                ]
            }

    requests = SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    jobs = scraper.scrape_himalayas(max_jobs=5)

    assert len(jobs) == 1
    assert jobs[0].company == "HimalayaCo"
    assert jobs[0].title == "Python Engineer"
    assert jobs[0].location == "Worldwide"
    assert jobs[0].remote is True
    assert jobs[0].source == "himalayas"
    assert jobs[0].description == "Build Python services"


def test_scrape_remotive_parses_remote_engineering_jobs(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Backend Engineer",
                        "company_name": "RemoteCo",
                        "url": "https://remotive.com/remote-jobs/software-dev/backend-engineer",
                        "description": "<p>Build APIs</p>",
                        "candidate_required_location": "Worldwide",
                        "category": "Software Development",
                    },
                    {
                        "title": "Customer Support Specialist",
                        "company_name": "SupportCo",
                        "url": "https://remotive.com/remote-jobs/customer-support/support",
                        "description": "<p>Answer tickets</p>",
                        "candidate_required_location": "Worldwide",
                        "category": "Customer Support",
                    },
                ]
            }

    requests = SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    jobs = scraper.scrape_remotive(max_jobs=5)

    assert len(jobs) == 1
    assert jobs[0].company == "RemoteCo"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].location == "Worldwide"
    assert jobs[0].remote is True
    assert jobs[0].source == "remotive"
    assert jobs[0].description == "Build APIs"


def test_scrape_jobicy_parses_remote_engineering_jobs(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "jobTitle": "React Engineer",
                        "companyName": "JobicyCo",
                        "url": "https://jobicy.com/jobs/react-engineer",
                        "jobDescription": "<p>Build React UI</p>",
                        "jobExcerpt": "Build React UI",
                        "jobGeo": "Anywhere",
                    },
                    {
                        "jobTitle": "Marketing Specialist",
                        "companyName": "MarketingCo",
                        "url": "https://jobicy.com/jobs/marketing",
                        "jobDescription": "<p>Run campaigns</p>",
                        "jobGeo": "Anywhere",
                    },
                ]
            }

    requests = SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    jobs = scraper.scrape_jobicy(max_jobs=5)

    assert len(jobs) == 1
    assert jobs[0].company == "JobicyCo"
    assert jobs[0].title == "React Engineer"
    assert jobs[0].location == "Anywhere"
    assert jobs[0].remote is True
    assert jobs[0].source == "jobicy"
    assert jobs[0].description == "Build React UI"


def test_scrape_adzuna_skips_without_credentials(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Adzuna should not call the API without credentials")

    requests = SimpleNamespace(get=forbidden)
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    assert scraper.scrape_adzuna(max_jobs=5) == []


def test_scrape_adzuna_parses_jobs_when_credentials_exist(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "app-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "app-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Backend Developer",
                        "company": {"display_name": "AdzunaCo"},
                        "redirect_url": "https://adzuna.example/job",
                        "description": "Remote backend APIs",
                        "location": {"display_name": "Remote"},
                    },
                    {
                        "title": "Data Scientist",
                        "company": {"display_name": "DataCo"},
                        "redirect_url": "https://adzuna.example/data",
                        "description": "ML models",
                        "location": {"display_name": "Remote"},
                    },
                ]
            }

    requests = SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    jobs = scraper.scrape_adzuna(max_jobs=5)

    assert len(jobs) == 1
    assert jobs[0].company == "AdzunaCo"
    assert jobs[0].source == "adzuna"
    assert jobs[0].remote is True


def test_direct_ats_adapters_parse_configured_company_feeds(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, **_kwargs):
        if "greenhouse" in url:
            return FakeResponse(
                {
                    "jobs": [
                        {
                            "title": "Backend Engineer",
                            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                            "location": {"name": "Remote"},
                            "content": "<p>Build APIs</p>",
                        }
                    ]
                }
            )
        if "lever.co" in url:
            return FakeResponse(
                [
                    {
                        "text": "Frontend Engineer",
                        "hostedUrl": "https://jobs.lever.co/beta/1",
                        "categories": {"location": "Remote"},
                        "descriptionPlain": "Build React",
                    }
                ]
            )
        if "ashbyhq" in url:
            return FakeResponse(
                {
                    "jobs": [
                        {
                            "title": "Full Stack Engineer",
                            "jobUrl": "https://jobs.ashbyhq.com/gamma/1",
                            "location": "Remote",
                            "isRemote": True,
                            "descriptionPlain": "Build product features",
                            "isListed": True,
                        }
                    ]
                }
            )
        if "smartrecruiters" in url:
            return FakeResponse(
                {
                    "content": [
                        {
                            "name": "Python Engineer",
                            "applyUrl": "https://jobs.smartrecruiters.com/delta/1",
                            "company": {"name": "Delta"},
                            "location": {"city": "Bengaluru", "country": "in", "remote": False},
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected URL {url}")

    requests = SimpleNamespace(get=fake_get)
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    jobs = scraper.scrape_direct_ats(
        max_jobs=10,
        greenhouse_boards=["acme"],
        lever_sites=["beta"],
        ashby_boards=["gamma"],
        smartrecruiters_companies=["delta"],
    )

    assert [job.source for job in jobs] == [
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
    ]
    assert [job.company for job in jobs] == ["Acme", "Beta", "Gamma", "Delta"]
    assert [job.title for job in jobs] == [
        "Backend Engineer",
        "Frontend Engineer",
        "Full Stack Engineer",
        "Python Engineer",
    ]


def test_scrape_wwr_parses_rss_jobs(monkeypatch):
    class FakeResponse:
        text = """
        <rss>
          <channel>
            <item>
              <title>RemoteCo: Backend Engineer</title>
              <link>https://weworkremotely.com/remote-jobs/remoteco-backend-engineer</link>
              <description><![CDATA[<p>Remote backend APIs</p>]]></description>
            </item>
            <item>
              <title>SupportCo: Customer Support Specialist</title>
              <link>https://weworkremotely.com/remote-jobs/supportco-support</link>
              <description><![CDATA[<p>Answer tickets</p>]]></description>
            </item>
          </channel>
        </rss>
        """

        def raise_for_status(self):
            return None

    requests = SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(scraper, "requests", requests, raising=False)

    jobs = scraper.scrape_wwr(max_jobs=5)

    assert len(jobs) == 1
    assert jobs[0].company == "RemoteCo"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].location == "Remote"
    assert jobs[0].remote is True
    assert jobs[0].source == "weworkremotely"
    assert jobs[0].description == "Remote backend APIs"


def test_scrape_only_writes_phase1_csv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "get_all_jobs",
        lambda max_per_source: [
            make_job(
                title="Backend Engineer",
                company="Acme",
                url="https://jobs.test/1",
                description="Build APIs",
                company_domain="acme.test",
            )
        ],
    )

    main.scrape_only(max_per_source=1)

    assert not (tmp_path / "vetted_jobs.csv").exists()
    output = tmp_path / "phase1_jobs.csv"
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows == [
        {
            "Company": "Acme",
            "Title": "Backend Engineer",
            "Location": "Remote",
            "Work Mode": "remote",
            "Company Region": "unknown",
            "Source": "wellfound",
            "URL": "https://jobs.test/1",
            "Remote": "Yes",
            "Company Domain": "acme.test",
            "Description": "Build APIs",
            "Reason": "deterministic filters passed",
        }
    ]


def test_phase2_vet_only_writes_phase2_csv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "get_vetted_jobs",
        lambda max_per_source: [
            make_job(
                title="Backend Engineer",
                company="Acme",
                url="https://jobs.test/1",
                description="Build APIs",
                company_domain="acme.test",
                vetting_reason="AI-approved product company",
            )
        ],
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("phase 2 vet-only must not apply, send, or generate applications")

    monkeypatch.setattr(main, "send_email", forbidden)
    monkeypatch.setattr(main, "apply_directly", forbidden)
    monkeypatch.setattr(main, "generate_application", forbidden)

    main.vet_only(max_per_source=1)

    assert not (tmp_path / "applications.csv").exists()
    output = tmp_path / "phase2_jobs.csv"
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["Company"] == "Acme"
    assert rows[0]["Reason"] == "AI-approved product company"


def test_remote_location_normalization():
    assert scraper._is_remote_location("Remote")
    assert scraper._is_remote_location("Work From Home")
    assert scraper._is_remote_location("WFH")
    assert not scraper._is_remote_location("Bengaluru")
