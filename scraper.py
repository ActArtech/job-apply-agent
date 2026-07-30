"""
scraper.py — pulls jobs from Wellfound and YC's Work at a Startup board.

Run standalone to test:
    python scraper.py
"""

import html
import os
import time, random, re, json, logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Callable, Iterable, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import requests

from config import TARGET_ROLES, EXCLUDED_KEYWORDS

log = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

API_SOURCE_QUERIES = [
    "backend engineer",
    "frontend engineer",
    "full stack engineer",
    "python engineer",
    "react engineer",
]

WWR_PROGRAMMING_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
]

REMOTE_FIRST_SOURCES = {
    "himalayas",
    "remotive",
    "weworkremotely",
    "jobicy",
    "adzuna",
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "wellfound",
    "ycombinator",
}

INDIA_LOCATION_MARKERS = (
    "india",
    "bengaluru",
    "bangalore",
    "mumbai",
    "delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "hyderabad",
    "pune",
    "chennai",
    "kolkata",
    "ahmedabad",
)

FOREIGN_LOCATION_MARKERS = (
    "united states",
    "usa",
    "us only",
    "u.s.",
    "canada",
    "europe",
    "emea",
    "united kingdom",
    "uk",
    "london",
    "germany",
    "berlin",
    "france",
    "paris",
    "netherlands",
    "amsterdam",
    "singapore",
    "australia",
    "sydney",
    "san francisco",
    "new york",
    "california",
)

SERVICE_COMPANY_MARKERS = (
    "it services",
    "consulting",
    "consultancy",
    "staffing",
    "recruitment agency",
    "outsourcing",
    "outsourced",
    "dev shop",
    "development agency",
    "digital agency",
    "client projects",
    "implementation partner",
    "managed services",
    "systems integrator",
    "tcs",
    "infosys",
    "wipro",
    "cognizant",
    "accenture",
)


def _is_remote_location(text: str) -> bool:
    normalized = (text or "").lower()
    remote_markers = ("remote", "work from home", "wfh", "anywhere", "worldwide", "global")
    return any(marker in normalized for marker in remote_markers)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    stripped = BeautifulSoup(html.unescape(text), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", stripped).strip()


def _split_env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]


def _titleize_slug(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug or "").strip().title()


def _job_text(job: "Job") -> str:
    return " ".join([job.title, job.company, job.location, job.description]).lower()


def _looks_like_target_role(title: str, description: str = "", category: str = "") -> bool:
    haystack = " ".join([title or "", description or "", category or ""]).lower()
    if not haystack.strip():
        return False
    if any(keyword.lower() in haystack for keyword in EXCLUDED_KEYWORDS):
        return False
    return any(role.lower() in haystack for role in TARGET_ROLES)


def _company_region(job: "Job") -> str:
    text = _job_text(job)
    if any(marker in text for marker in INDIA_LOCATION_MARKERS):
        return "india"
    if job.source == "instahyre":
        return "india"
    if any(marker in text for marker in FOREIGN_LOCATION_MARKERS):
        return "foreign"
    return "unknown"


def _work_mode(job: "Job") -> str:
    text = _job_text(job)
    if job.remote or _is_remote_location(text):
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    if _company_region(job) in ("india", "foreign"):
        return "wfo"
    return "unknown"


def _is_service_company(job: "Job") -> bool:
    text = _job_text(job)
    return any(marker in text for marker in SERVICE_COMPANY_MARKERS)


def _is_management_role(job: "Job") -> bool:
    title = (job.title or "").lower()
    return bool(re.search(r"\b(manager|director|head of|vp|vice president|team leader)\b", title))


def _request_json(url: str, *, params: Optional[dict] = None) -> Optional[object]:
    response = requests.get(url, params=params, headers=HTTP_HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def _request_text(url: str, *, params: Optional[dict] = None) -> str:
    response = requests.get(url, params=params, headers=HTTP_HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def _items_from_payload(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("jobs", "results", "data", "content"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _append_unique(jobs: list["Job"], job: "Job", seen: set[str], max_jobs: int):
    if len(jobs) >= max_jobs:
        return
    if not _looks_like_target_role(job.title, job.description):
        return
    key = _job_key(job)
    if key in seen:
        return
    seen.add(key)
    jobs.append(job)


@dataclass
class Job:
    title: str
    company: str
    company_domain: str       # used to find email via Hunter.io
    location: str
    url: str
    description: str
    source: str               # "wellfound" | "ycombinator"
    remote: bool = False
    vetting_reason: str = ""
    region: str = ""
    work_mode: str = ""

    def is_relevant(self) -> bool:
        # We now rely 100% on the AI Vetter to filter jobs instead of naive keyword matching.
        return True

    def to_dict(self):
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Wellfound (formerly AngelList Talent)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_wellfound(max_jobs: int = 50) -> list[Job]:
    """
    Scrapes Wellfound job listings for software engineering roles using Playwright
    to bypass standard request blocks (like 403 Forbidden).
    """
    jobs = []
    role_query = "software+engineer"
    url = f"https://wellfound.com/role/software-engineer/india"

    log.info(f"Scraping Wellfound via Playwright: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Scroll to load more jobs
            for _ in range(5):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            
            html_content = page.content()
            browser.close()

        soup = BeautifulSoup(html_content, "html.parser")
        
        # Wellfound renders job cards with data attrs — grab the __NEXT_DATA__ JSON
        next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if not next_data_tag:
            log.warning("Wellfound: __NEXT_DATA__ not found; page structure may have changed.")
            return []

        data = json.loads(next_data_tag.string)
        # Navigate to job listings in the Next.js page props
        page_props = data.get("props", {}).get("pageProps", {})
        job_listings = (
            page_props
            .get("searchResults", {})
            .get("startupRoles", {})
            .get("edges", [])
        )

        for edge in job_listings[:max_jobs]:
            node = edge.get("node", {})
            startup = node.get("startup", {})
            company_name = startup.get("name", "")
            company_slug = startup.get("slug", "")
            title = node.get("title", "")
            location = node.get("locationNames", ["Remote"])[0]
            description = node.get("description", "")
            slug = node.get("slug", "")
            job_url = f"https://wellfound.com/jobs/{slug}"

            # Try to extract company domain from their site URL
            company_site = startup.get("companyUrl", "") or ""
            domain = _extract_domain(company_site) or f"{company_slug}.com"

            job = Job(
                title=title,
                company=company_name,
                company_domain=domain,
                location=location,
                url=job_url,
                description=description[:3000],   # cap for API cost
                source="wellfound",
                remote=_is_remote_location(location) or _is_remote_location(description),
            )
            
            if already_vetted(job.company, job.title, job.url):
                # Silently skip
                continue
                
            if job.is_relevant():
                jobs.append(job)

        log.info(f"Wellfound: found {len(jobs)} relevant jobs")
        _polite_delay()

    except Exception as e:
        log.error(f"Wellfound scrape failed: {e}")

    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# YC Work at a Startup  (workatastartup.com)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_yc(max_jobs: int = 50) -> list[Job]:
    """
    Scrapes YC's Work at a Startup job board using Playwright.
    Loops through multiple queries to bypass the unauthenticated 30-job limit.
    """
    jobs = []
    
    # Unauthenticated YC limits results to ~30 per query. 
    # We run multiple queries to gather a large sample space.
    queries = ["backend", "frontend", "full stack", "python", "react"]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            for q in queries:
                url = f"https://www.workatastartup.com/jobs?query={q.replace(' ', '%20')}&role=eng&remote=true&jobType=fulltime"
                log.info(f"Scraping YC via Playwright: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Scroll down
                for _ in range(15):
                    page.keyboard.press("End")
                    page.wait_for_timeout(500)
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                title_links = soup.find_all('a', class_='mr-5')
                for a in title_links:
                    try:
                        title = a.text.strip()
                        job_url = "https://www.workatastartup.com" + a['href']
                        parent = a.find_parent('div', class_='my-auto')
                        company_span = parent.find('span', class_='font-bold')
                        if not company_span:
                            continue
                        company = company_span.text.split('\xa0')[0].strip()
                        domain = f"{company.lower().replace(' ', '')}.com"
                        
                        job = Job(
                            title=title,
                            company=company,
                            company_domain=domain,
                            location="Remote",
                            url=job_url,
                            description="See JD URL",
                            source="ycombinator",
                            remote=True
                        )
                        if already_vetted(job.company, job.title, job.url):
                            continue
                        if job.is_relevant():
                            jobs.append(job)
                    except Exception as e:
                        continue
                        
                log.info(f"YC '{q}': found {len(title_links)} links.")
                _polite_delay()

            browser.close()
            
            log.info(f"YC total: found {len(jobs)} relevant jobs via fallback HTML parsing across all queries.")
            return jobs

    except Exception as e:
        log.error(f"YC scrape failed: {e}")

    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Fetch full JD from a job URL (for when listings show only a snippet)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_full_jd(job_url: str) -> Optional[str]:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(job_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            html_content = page.content()
            browser.close()
            
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove nav/footer noise
        for tag in soup(["nav", "footer", "header", "script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:5000]
    except Exception as e:
        log.warning(f"Could not fetch JD from {job_url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """https://razorpay.com/about  →  razorpay.com"""
    match = re.search(r"(?:https?://)?(?:www\.)?([^/\s]+)", url)
    return match.group(1).lower() if match else ""


def _polite_delay():
    time.sleep(random.uniform(2, 5))


from pathlib import Path

VETTED_FILE = ".vetted_cache.txt"

def load_vetted() -> set[str]:
    if Path(VETTED_FILE).exists():
        with open(VETTED_FILE) as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_vetted(company: str, role: str, url: str = ""):
    with open(VETTED_FILE, "a") as f:
        # Save both formats so we can check either
        f.write(f"{company.lower()}|{role.lower()}\n")
        if url:
            f.write(f"url:{url}\n")

def already_vetted(company: str, role: str, url: str = "") -> bool:
    vetted = load_vetted()
    if url and f"url:{url}" in vetted:
        return True
    return f"{company.lower()}|{role.lower()}" in vetted


def scrape_himalayas(max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    for query in API_SOURCE_QUERIES:
        if len(jobs) >= max_jobs:
            break
        try:
            payload = _request_json(
                "https://himalayas.app/jobs/api/search",
                params={
                    "q": query,
                    "employment_type": "Full Time",
                    "sort": "recent",
                    "worldwide": "true",
                },
            )
        except Exception as e:
            log.warning(f"Himalayas '{query}' scrape failed: {e}")
            continue

        for item in _items_from_payload(payload):
            if len(jobs) >= max_jobs:
                break
            title = item.get("title", "")
            company = item.get("companyName", "")
            url = item.get("applicationLink") or item.get("url") or item.get("guid", "")
            description = _strip_html(item.get("description") or item.get("excerpt", ""))
            restrictions = item.get("locationRestrictions") or []
            location = ", ".join(str(loc) for loc in restrictions if loc) or "Worldwide"
            category = ", ".join(item.get("category") or item.get("parentCategories") or [])

            _append_unique(
                jobs,
                Job(
                    title=title,
                    company=company,
                    company_domain="",
                    location=location,
                    url=url,
                    description=description[:3000],
                    source="himalayas",
                    remote=True,
                ),
                seen,
                max_jobs,
            )

    log.info(f"Himalayas: found {len(jobs)} jobs.")
    return jobs


def scrape_remotive(max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    try:
        payload = _request_json(
            "https://remotive.com/api/remote-jobs",
            params={"category": "software-dev", "limit": max_jobs},
        )
    except Exception as e:
        log.warning(f"Remotive scrape failed: {e}")
        return jobs

    for item in _items_from_payload(payload):
        if len(jobs) >= max_jobs:
            break
        description = _strip_html(item.get("description", ""))
        _append_unique(
            jobs,
            Job(
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                company_domain="",
                location=item.get("candidate_required_location") or "Remote",
                url=item.get("url", ""),
                description=description[:3000],
                source="remotive",
                remote=True,
            ),
            seen,
            max_jobs,
        )

    log.info(f"Remotive: found {len(jobs)} jobs.")
    return jobs


def scrape_wwr(max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    for feed_url in WWR_PROGRAMMING_FEEDS:
        if len(jobs) >= max_jobs:
            break
        try:
            xml_text = _request_text(feed_url)
            root = ET.fromstring(xml_text)
        except Exception as e:
            log.warning(f"We Work Remotely feed failed ({feed_url}): {e}")
            continue

        for item in root.findall(".//item"):
            if len(jobs) >= max_jobs:
                break
            raw_title = item.findtext("title") or ""
            if ":" in raw_title:
                company, title = [part.strip() for part in raw_title.split(":", 1)]
            else:
                company, title = "Unknown", raw_title.strip()
            description = _strip_html(item.findtext("description") or "")
            _append_unique(
                jobs,
                Job(
                    title=title,
                    company=company,
                    company_domain="",
                    location="Remote",
                    url=item.findtext("link") or "",
                    description=description[:3000],
                    source="weworkremotely",
                    remote=True,
                ),
                seen,
                max_jobs,
            )

    log.info(f"We Work Remotely: found {len(jobs)} jobs.")
    return jobs


def scrape_jobicy(max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    try:
        payload = _request_json(
            "https://jobicy.com/api/v2/remote-jobs",
            params={"count": min(max_jobs, 50), "tag": "python,react,nodejs,backend,frontend"},
        )
    except Exception as e:
        log.warning(f"Jobicy scrape failed: {e}")
        return jobs

    for item in _items_from_payload(payload):
        if len(jobs) >= max_jobs:
            break
        description = _strip_html(
            item.get("jobDescription") or item.get("description") or item.get("jobExcerpt", "")
        )
        _append_unique(
            jobs,
            Job(
                title=item.get("jobTitle") or item.get("title", ""),
                company=item.get("companyName") or item.get("company", ""),
                company_domain="",
                location=item.get("jobGeo") or item.get("location") or "Remote",
                url=item.get("url") or item.get("jobUrl") or "",
                description=description[:3000],
                source="jobicy",
                remote=True,
            ),
            seen,
            max_jobs,
        )

    log.info(f"Jobicy: found {len(jobs)} jobs.")
    return jobs


def scrape_adzuna(max_jobs: int = 50) -> list[Job]:
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        log.info("Adzuna: skipped because ADZUNA_APP_ID/ADZUNA_APP_KEY are not configured.")
        return []

    jobs: list[Job] = []
    seen: set[str] = set()
    countries = _split_env_list("ADZUNA_COUNTRIES") or ["in", "gb", "us"]

    for country in countries:
        if len(jobs) >= max_jobs:
            break
        try:
            payload = _request_json(
                f"https://api.adzuna.com/v1/api/jobs/{country.lower()}/search/1",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": "software engineer remote",
                    "results_per_page": min(max_jobs, 50),
                    "content-type": "application/json",
                },
            )
        except Exception as e:
            log.warning(f"Adzuna '{country}' scrape failed: {e}")
            continue

        for item in _items_from_payload(payload):
            if len(jobs) >= max_jobs:
                break
            company = item.get("company") or {}
            location = item.get("location") or {}
            description = _strip_html(item.get("description", ""))
            location_text = location.get("display_name", "") if isinstance(location, dict) else str(location)
            _append_unique(
                jobs,
                Job(
                    title=item.get("title", ""),
                    company=company.get("display_name", "") if isinstance(company, dict) else str(company),
                    company_domain="",
                    location=location_text or "Unknown",
                    url=item.get("redirect_url", ""),
                    description=description[:3000],
                    source="adzuna",
                    remote=_is_remote_location(location_text) or _is_remote_location(description),
                ),
                seen,
                max_jobs,
            )

    log.info(f"Adzuna: found {len(jobs)} jobs.")
    return jobs


def scrape_greenhouse(board_tokens: Iterable[str], max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    for board in board_tokens:
        if len(jobs) >= max_jobs:
            break
        try:
            payload = _request_json(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                params={"content": "true"},
            )
        except Exception as e:
            log.warning(f"Greenhouse '{board}' scrape failed: {e}")
            continue

        for item in _items_from_payload(payload):
            if len(jobs) >= max_jobs:
                break
            location = item.get("location") or {}
            location_text = location.get("name", "") if isinstance(location, dict) else str(location)
            description = _strip_html(item.get("content", ""))
            _append_unique(
                jobs,
                Job(
                    title=item.get("title", ""),
                    company=_titleize_slug(board),
                    company_domain="",
                    location=location_text or "Unknown",
                    url=item.get("absolute_url", ""),
                    description=description[:3000],
                    source="greenhouse",
                    remote=_is_remote_location(location_text) or _is_remote_location(description),
                ),
                seen,
                max_jobs,
            )

    return jobs


def scrape_lever(site_names: Iterable[str], max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    for site in site_names:
        if len(jobs) >= max_jobs:
            break
        try:
            payload = _request_json(
                f"https://api.lever.co/v0/postings/{site}",
                params={"mode": "json", "limit": min(max_jobs, 100)},
            )
        except Exception as e:
            log.warning(f"Lever '{site}' scrape failed: {e}")
            continue

        for item in _items_from_payload(payload):
            if len(jobs) >= max_jobs:
                break
            categories = item.get("categories") or {}
            location = categories.get("location", "") if isinstance(categories, dict) else ""
            description = _strip_html(item.get("descriptionPlain") or item.get("description", ""))
            _append_unique(
                jobs,
                Job(
                    title=item.get("text", ""),
                    company=_titleize_slug(site),
                    company_domain="",
                    location=location or "Unknown",
                    url=item.get("hostedUrl") or item.get("applyUrl") or "",
                    description=description[:3000],
                    source="lever",
                    remote=_is_remote_location(location) or _is_remote_location(description),
                ),
                seen,
                max_jobs,
            )

    return jobs


def scrape_ashby(board_names: Iterable[str], max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    for board in board_names:
        if len(jobs) >= max_jobs:
            break
        try:
            payload = _request_json(
                f"https://api.ashbyhq.com/posting-api/job-board/{board}",
                params={"includeCompensation": "false"},
            )
        except Exception as e:
            log.warning(f"Ashby '{board}' scrape failed: {e}")
            continue

        for item in _items_from_payload(payload):
            if len(jobs) >= max_jobs:
                break
            if item.get("isListed") is False:
                continue
            location = item.get("location", "")
            description = _strip_html(item.get("descriptionPlain") or item.get("descriptionHtml", ""))
            _append_unique(
                jobs,
                Job(
                    title=item.get("title", ""),
                    company=_titleize_slug(board),
                    company_domain="",
                    location=location or "Unknown",
                    url=item.get("jobUrl") or item.get("applicationUrl") or "",
                    description=description[:3000],
                    source="ashby",
                    remote=bool(item.get("isRemote")) or _is_remote_location(item.get("workplaceType", "")),
                ),
                seen,
                max_jobs,
            )

    return jobs


def scrape_smartrecruiters(company_identifiers: Iterable[str], max_jobs: int = 50) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()

    for company_id in company_identifiers:
        if len(jobs) >= max_jobs:
            break
        try:
            payload = _request_json(
                f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings",
                params={"q": "engineer", "limit": min(max_jobs, 100)},
            )
        except Exception as e:
            log.warning(f"SmartRecruiters '{company_id}' scrape failed: {e}")
            continue

        for item in _items_from_payload(payload):
            if len(jobs) >= max_jobs:
                break
            company = item.get("company") or {}
            location = item.get("location") or {}
            if isinstance(location, dict):
                location_text = ", ".join(
                    str(location.get(key, ""))
                    for key in ("city", "region", "country")
                    if location.get(key)
                )
                remote = bool(location.get("remote"))
            else:
                location_text = str(location)
                remote = _is_remote_location(location_text)
            _append_unique(
                jobs,
                Job(
                    title=item.get("name", ""),
                    company=company.get("name", _titleize_slug(company_id)) if isinstance(company, dict) else _titleize_slug(company_id),
                    company_domain="",
                    location=location_text or "Unknown",
                    url=item.get("applyUrl") or item.get("ref") or "",
                    description=_strip_html(item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""))[:3000]
                    if isinstance(item.get("jobAd"), dict)
                    else "",
                    source="smartrecruiters",
                    remote=remote,
                ),
                seen,
                max_jobs,
            )

    return jobs


def scrape_direct_ats(
    max_jobs: int = 50,
    greenhouse_boards: Optional[Iterable[str]] = None,
    lever_sites: Optional[Iterable[str]] = None,
    ashby_boards: Optional[Iterable[str]] = None,
    smartrecruiters_companies: Optional[Iterable[str]] = None,
) -> list[Job]:
    greenhouse_boards = list(greenhouse_boards) if greenhouse_boards is not None else _split_env_list("GREENHOUSE_BOARDS")
    lever_sites = list(lever_sites) if lever_sites is not None else _split_env_list("LEVER_SITES")
    ashby_boards = list(ashby_boards) if ashby_boards is not None else _split_env_list("ASHBY_BOARDS")
    smartrecruiters_companies = (
        list(smartrecruiters_companies)
        if smartrecruiters_companies is not None
        else _split_env_list("SMARTRECRUITERS_COMPANIES")
    )

    jobs: list[Job] = []
    for source_jobs in (
        scrape_greenhouse(greenhouse_boards, max_jobs),
        scrape_lever(lever_sites, max_jobs),
        scrape_ashby(ashby_boards, max_jobs),
        scrape_smartrecruiters(smartrecruiters_companies, max_jobs),
    ):
        jobs.extend(source_jobs)
        if len(jobs) >= max_jobs:
            break

    deduped: list[Job] = []
    seen: set[str] = set()
    for job in jobs:
        key = _job_key(job)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
        if len(deduped) >= max_jobs:
            break

    log.info(f"Direct ATS: found {len(deduped)} jobs.")
    return deduped

def scrape_instahyre(max_jobs: int = 50) -> list[Job]:
    """
    Scrapes Instahyre job board using Playwright.
    """
    jobs = []
    # Using generic tech queries common on Instahyre
    urls = [
        "https://www.instahyre.com/software-engineering-jobs/",
        "https://www.instahyre.com/python-jobs/",
        "https://www.instahyre.com/backend-developer-jobs/",
        "https://www.instahyre.com/full-stack-developer-jobs/"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            for url in urls:
                if len(jobs) >= max_jobs:
                    break
                    
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    _polite_delay()
                    
                    # Scroll to load dynamic jobs
                    for _ in range(5):
                        page.keyboard.press("End")
                        page.wait_for_timeout(500)
                    
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, "html.parser")
                    
                    # Target the job containers
                    job_cards = soup.select('div.employer-block')
                    
                    for card in job_cards:
                        if len(jobs) >= max_jobs:
                            break
                            
                        try:
                            # Extract data from the mobile-optimized block, which has separated elements
                            mobile_block = card.select_one('.employer-details-mobile')
                            if not mobile_block:
                                continue
                                
                            title_el = mobile_block.select_one('.employer-job-name .company-name')
                            company_el = mobile_block.select_one('.employer-company-name .company-name')
                            location_el = mobile_block.select_one('.employer-locations span')
                            
                            if not title_el or not company_el:
                                continue
                                
                            title = title_el.text.strip()
                            company = company_el.text.strip()
                            location = location_el.text.strip() if location_el else "Unknown"
                            
                            # Instahyre job link is typically on the outer 'a' tag
                            link_el = card.select_one('a#employer-profile-opportunity')
                            job_url = link_el['href'] if link_el and 'href' in link_el.attrs else url
                            if job_url.startswith('/'):
                                job_url = "https://www.instahyre.com" + job_url
                            
                            domain = _extract_domain(job_url)
                            remote = _is_remote_location(location)
                            
                            # Snippet from notes if available
                            notes_el = card.select_one('.employer-notes')
                            description = notes_el.text.strip() if notes_el else "Instahyre Job - see link for details."
                            
                            job = Job(
                                title=title,
                                company=company,
                                company_domain=domain,
                                location=location,
                                url=job_url,
                                description=description,
                                source="instahyre",
                                remote=remote
                            )
                            
                            if already_vetted(job.company, job.title, job.url):
                                continue
                                
                            if job.is_relevant():
                                jobs.append(job)
                                
                        except Exception as e:
                            log.debug(f"Error parsing Instahyre card: {e}")
                            continue
                            
                    log.info(f"Instahyre '{url}': found {len(job_cards)} job cards.")
                    _polite_delay()
                    
                except PlaywrightTimeoutError:
                    log.warning(f"Timeout loading Instahyre URL: {url}")
                except Exception as e:
                    log.error(f"Error scraping Instahyre URL {url}: {e}")
                finally:
                    page.close()
                    
            browser.close()
    except Exception as e:
        log.error(f"Playwright error in scrape_instahyre: {e}")
        
    return jobs

def _job_key(job: Job) -> str:
    if job.url:
        return f"url:{job.url.strip().lower()}"
    return f"title:{job.company.strip().lower()}|{job.title.strip().lower()}"


def _passes_phase1_filters(job: Job) -> tuple[bool, str]:
    if not job.company.strip():
        return False, "missing company"
    if not job.title.strip():
        return False, "missing title"

    if _is_management_role(job):
        return False, "management role"

    haystack = _job_text(job)
    for keyword in EXCLUDED_KEYWORDS:
        if keyword.lower() in haystack:
            return False, f"excluded keyword: {keyword}"

    if _is_service_company(job):
        return False, "service/consulting/staffing company signal"

    region = _company_region(job)
    work_mode = _work_mode(job)
    if region == "foreign" and work_mode != "remote":
        return False, "foreign job is not remote"
    if region == "unknown" and work_mode != "remote":
        return False, "unknown location is not remote"

    return True, f"deterministic filters passed: {region}/{work_mode}"


def get_all_jobs(max_per_source: int = 40) -> list[Job]:
    """Phase 1: scrape, normalize, dedupe, and deterministically filter jobs only."""
    source_functions: list[Callable[[int], list[Job]]] = [
        scrape_himalayas,
        scrape_remotive,
        scrape_wwr,
        scrape_jobicy,
        scrape_adzuna,
        scrape_direct_ats,
        scrape_instahyre,
    ]

    all_jobs: list[Job] = []
    for scrape_source in source_functions:
        try:
            source_jobs = scrape_source(max_per_source)
            all_jobs.extend(source_jobs)
        except Exception as e:
            log.warning(f"Phase 1 source failed: {scrape_source.__name__}: {e}")

    seen = set()
    gathered = []
    for job in all_jobs:
        key = _job_key(job)
        if key in seen:
            continue
        seen.add(key)

        keep, reason = _passes_phase1_filters(job)
        if not keep:
            log.info(f"Phase 1 skip: {job.company} - {job.title} -> {reason}")
            continue

        job.vetting_reason = reason
        gathered.append(job)

    log.info(f"Phase 1 gathered {len(gathered)} jobs after deterministic filtering.")
    return gathered


def get_vetted_jobs(max_per_source: int = 40) -> list[Job]:
    """Legacy AI-vetted flow for later application phases."""
    from job_vetter import vet_job

    gathered = get_all_jobs(max_per_source=max_per_source)
    vetted_jobs = []
    for i, job in enumerate(gathered):
        if already_vetted(job.company, job.title, job.url):
            log.info(f"Vetting [{i+1}/{len(gathered)}]: {job.company} - {job.title} -> Skip (Already vetted)")
            continue

        log.info(f"Vetting [{i+1}/{len(gathered)}]: {job.company} - {job.title}")
        jd = job.description
        if len(jd) < 500:
            log.info("  -> Short description — fetching full JD from URL...")
            full = fetch_full_jd(job.url)
            if full:
                jd = full
                job.description = jd

        is_approved, reason = vet_job(
            company=job.company,
            role=job.title,
            url=job.url,
            jd=jd,
        )

        if is_approved:
            log.info(f"  -> APPROVED: {reason}")
            job.vetting_reason = reason
            save_vetted(job.company, job.title, job.url)
            vetted_jobs.append(job)
        else:
            log.info(f"  -> REJECTED: {reason}")

    log.info(f"Total AI-approved jobs newly found: {len(vetted_jobs)}")
    return vetted_jobs


if __name__ == "__main__":
    import csv
    logging.basicConfig(level=logging.INFO)
    jobs = get_all_jobs(max_per_source=10)
    
    csv_file = "vetted_jobs.csv"
    try:
        with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Company", "Title", "Location", "Source", "URL", "Remote", "Reason"])
            for j in jobs:
                writer.writerow([
                    j.company,
                    j.title,
                    j.location,
                    j.source,
                    j.url,
                    "Yes" if j.remote else "No",
                    j.vetting_reason
                ])
        log.info(f"Successfully wrote {len(jobs)} vetted jobs to {csv_file}")
    except Exception as e:
        log.error(f"Failed to write vetted jobs to CSV: {e}")

    for j in jobs:
        print(f"[{j.source}] {j.company} — {j.title} ({j.location})")
        print(f"  {j.url}\n")
