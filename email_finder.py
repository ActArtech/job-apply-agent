"""
email_finder.py — Waterfall Email Discovery System.
Tries Hunter.io -> Apollo.io -> SMTP Ping Fallback to find a valid hiring manager email.
"""

import logging
import smtplib
import socket
import json
import dns.resolver
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from config import HUNTER_API_KEY, APOLLO_API_KEY, SNOV_API_KEY

log = logging.getLogger(__name__)

HUNTER_BASE = "https://api.hunter.io/v2"
APOLLO_BASE = "https://api.apollo.io/api/v1"


@dataclass
class Contact:
    email: str
    first_name: str
    last_name: str
    position: str
    confidence: int       # 0–100
    discovery_method: str # "Hunter.io", "Apollo.io", "SMTP Validation"
    linkedin_url: str = ""
    title: str = ""


def find_hiring_manager(company_domain: str, company_name: str = None, role_keywords: list[str] = None) -> Optional[Contact]:
    """
    Search for the most relevant engineering hiring contact at a company using a waterfall approach:
    Tier 1: Apollo.io People Search
    Tier 2: Search Engine Discovery (LinkedIn + Name)
    Tier 3: Hunter.io Email Finder (if name found)
    Tier 4: Generic Patterns + SMTP Validation (Fallback)
    """
    domain = company_domain.lower()
    name = company_name or domain.split('.')[0].capitalize()
    
    # 1. Tier 1: Apollo.io
    if APOLLO_API_KEY:
        log.info(f"Trying Apollo.io for {domain}")
        contact = _apollo_search(domain, role_keywords)
        if contact:
            return contact

    # 2. Tier 2: Search Engine Discovery (LinkedIn)
    log.info(f"Trying LinkedIn Discovery for {name}")
    linkedin_contact = _linkedin_search(domain, name)
    
    # 3. Tier 3: Hunter.io Email Finder (using name from Tier 2)
    if linkedin_contact and HUNTER_API_KEY:
        log.info(f"Trying Hunter.io Email Finder for {linkedin_contact.first_name} at {domain}")
        email = _hunter_email_finder(domain, linkedin_contact.first_name, linkedin_contact.last_name)
        if email:
            linkedin_contact.email = email
            linkedin_contact.discovery_method = "LinkedIn + Hunter"
            return linkedin_contact
    
    # If Tier 2 found a profile but we couldn't get an email, keep it and try to find email elsewhere?
    # For now, if we have a LinkedIn but no email, we continue to fallback but maybe we should return it?
    # Let's try Generic Fallback if we still have no email.
    
    # 4. Tier 4: SMTP Fallback
    log.info(f"Falling back to SMTP Ping for {domain}")
    contact = _smtp_fallback_search(domain)
    if contact:
        # If we had a LinkedIn from Tier 2, attach it to the generic contact
        if linkedin_contact:
            contact.linkedin_url = linkedin_contact.linkedin_url
        contact.discovery_method = "SMTP Validation"
        return contact

    # If even fallback failed, but we found a LinkedIn profile, return that with no email
    if linkedin_contact:
        linkedin_contact.discovery_method = "LinkedIn (No Email)"
        return linkedin_contact

    return None

def _score_contact(c: Contact, role_priority: list[str]) -> int:
    pos = c.position.lower()
    for i, kw in enumerate(role_priority):
        if kw in pos:
            return len(role_priority) - i   # higher = better
    return 0

def _get_role_priority():
    return [
        "engineering manager", "director of engineering", "vp engineering",
        "head of engineering", "software engineering manager",
        "cto", "chief technology officer", "founder", "co-founder",
        "technical recruiter", "head of talent", "talent acquisition", "recruiter"
    ]

def _linkedin_search(domain: str, company_name: str) -> Optional[Contact]:
    """
    Finds a likely hiring manager LinkedIn profile via Serper.dev (Google Search API) and extracts the name.
    """
    from config import SERPER_API_KEY
    if not SERPER_API_KEY:
        log.warning("SERPER_API_KEY not set. Skipping LinkedIn search.")
        return None

    search_query = f'site:linkedin.com/in "{company_name}" "Engineering Manager" OR "Founder" OR "CTO" OR "Director of Engineering"'
    
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = json.dumps({
        "q": search_query,
        "num": 5
    })
    
    try:
        resp = requests.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        
        results = resp.json().get("organic", [])
        if not results:
            log.info(f"No LinkedIn profiles found for {company_name} via Serper.")
            return None
            
        for result in results:
            link = result.get("link", "")
            title = result.get("title", "")
            
            if "linkedin.com/in/" in link:
                # Extract name: often the first few words of the title before a dash or pipe
                name_part = title.split('-')[0].split('|')[0].strip()
                parts = name_part.split()
                if len(parts) >= 2:
                    first = parts[0]
                    last = parts[-1]
                    return Contact(
                        email="", # Will be found by Hunter or SMTP later
                        first_name=first,
                        last_name=last,
                        position="Engineering Leader (Likely)",
                        confidence=70,
                        discovery_method="LinkedIn (Serper API)",
                        linkedin_url=link
                    )
                    
    except Exception as e:
        log.warning(f"Serper API search failed for {company_name}: {e}")
        
    return None

def _hunter_email_finder(domain: str, first_name: str, last_name: str) -> Optional[str]:
    """
    Uses Hunter.io's Email Finder endpoint to turn a name into an email.
    """
    try:
        resp = requests.get(
            f"{HUNTER_BASE}/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": HUNTER_API_KEY
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return data.get("email")
    except Exception as e:
        log.warning(f"Hunter Email Finder failed for {first_name} {last_name}: {e}")
    return None

def _hunter_search(domain: str, role_keywords: list[str] = None) -> Optional[Contact]:
    try:
        resp = requests.get(
            f"{HUNTER_BASE}/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 20},
            timeout=10,
        )
        if resp.status_code == 429:
            log.warning(f"Hunter.io rate limit hit for {domain}.")
            return None
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])

        contacts = []
        for e in emails:
            contacts.append(Contact(
                email=e.get("value", ""),
                first_name=e.get("first_name", ""),
                last_name=e.get("last_name", ""),
                position=e.get("position", ""),
                confidence=e.get("confidence", 0),
                discovery_method="",
                linkedin_url=e.get("linkedin", ""),
            ))
            
        if not contacts:
            return None
            
        contacts.sort(key=lambda c: (_score_contact(c, _get_role_priority()), c.confidence), reverse=True)
        return contacts[0]
        
    except Exception as e:
        log.warning(f"Hunter.io search failed for {domain}: {e}")
        return None


def _apollo_search(domain: str, role_keywords: list[str] = None) -> Optional[Contact]:
    """
    Search for people at a company via Apollo.io People Search.
    """
    try:
        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/json'
        }
        # Use our prioritized titles to search
        titles = _get_role_priority()
        
        data = {
            "api_key": APOLLO_API_KEY,
            "q_organization_domains": domain,
            "person_titles": titles,
            "page": 1,
            "per_page": 10
        }
        # Apollo's mixed_people/search works well for finding both email and social info
        resp = requests.post(f"{APOLLO_BASE}/mixed_people/search", headers=headers, json=data, timeout=15)
        
        if resp.status_code == 429:
            log.warning(f"Apollo.io rate limit hit for {domain}.")
            return None
        resp.raise_for_status()
        
        people = resp.json().get("people", [])
        contacts = []
        for p in people:
            email = p.get("email")
            if not email:
                continue
                
            contacts.append(Contact(
                email=email,
                first_name=p.get("first_name", ""),
                last_name=p.get("last_name", ""),
                position=p.get("title", ""),
                confidence=90, # Apollo verified is high confidence
                discovery_method="Apollo.io",
                linkedin_url=p.get("linkedin_url", "")
            ))
            
        if not contacts:
            return None
            
        # Sort by title priority
        contacts.sort(key=lambda c: _score_contact(c, titles), reverse=True)
        return contacts[0]
        
    except Exception as e:
        log.warning(f"Apollo.io search failed for {domain}: {e}")
        return None


def _smtp_fallback_search(domain: str) -> Optional[Contact]:
    """
    Generate common email patterns (e.g., founders) and verify via SMTP.
    Requires you to know at least one possible name, or guess generically.
    For demonstration, we'll try common prefixes.
    """
    prefixes = ["founders", "founder", "ceo", "careers", "jobs", "hiring", "engineering"]
    
    # Get MX record
    try:
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = sorted(records, key=lambda r: r.preference)[0].exchange.to_text()
    except Exception as e:
        log.warning(f"Could not find MX record for {domain}: {e}")
        return None

    # Test connection quickly before trying prefixes
    try:
        server = smtplib.SMTP(timeout=2)
        server.connect(mx_record, 25)
        server.quit()
    except Exception as e:
        log.warning(f"Port 25 blocked or MX unreachable for {domain}: {e}")
        return None

    for prefix in prefixes:
        test_email = f"{prefix}@{domain}"
        if _verify_email_smtp(test_email, mx_record):
            return Contact(
                email=test_email,
                first_name=prefix.capitalize(),
                last_name="",
                position="Hiring/Founding Team",
                confidence=50, # low confidence on actual identity, but email works
                discovery_method="",
                linkedin_url=""
            )
            
    return None


def _verify_email_smtp(email: str, mx_record: str) -> bool:
    """
    Ping the mail server to check if email address exists.
    """
    try:
        server = smtplib.SMTP(timeout=2)
        server.connect(mx_record, 25)
        server.helo(socket.getfqdn())
        server.mail("test@example.com") # Should ideally be your own domain
        code, message = server.rcpt(email)
        server.quit()
        
        # 250 means OK
        if code == 250:
            return True
        return False
    except Exception as e:
        log.debug(f"SMTP check failed for {email}: {e}")
        return False


def verify_email(email: str) -> bool:
    """
    Check if an email is deliverable. Uses Hunter if available, else SMTP ping.
    """
    if HUNTER_API_KEY:
        try:
            resp = requests.get(
                f"{HUNTER_BASE}/email-verifier",
                params={"email": email, "api_key": HUNTER_API_KEY},
                timeout=10,
            )
            data = resp.json().get("data", {})
            status = data.get("status", "")
            return status in ("valid", "accept_all")
        except:
            pass
            
    # Fallback to SMTP
    try:
        domain = email.split('@')[1]
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(sorted(records, key=lambda r: r.preference)[0].exchange)
        return _verify_email_smtp(email, mx_record)
    except:
        return True # fail open


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    contact = find_hiring_manager("razorpay.com")
    if contact:
        print(f"Found: {contact.first_name} {contact.last_name}")
        print(f"Email: {contact.email}")
        print(f"Role:  {contact.position}")
        print(f"Method: {contact.discovery_method}")
