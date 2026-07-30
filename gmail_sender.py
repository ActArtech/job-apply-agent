"""
gmail_sender.py — send cold emails via Gmail API (OAuth2).

First-time setup:
1. Go to console.cloud.google.com → New Project
2. Enable Gmail API
3. OAuth 2.0 → Desktop app → Download JSON → save as credentials.json
4. Run `python gmail_sender.py --auth` once to generate token.json

After that, sending is fully automated.
"""

import base64, json, logging, os, time, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import (
    MY_NAME, MY_EMAIL,
    GMAIL_CREDENTIALS,
    MAX_EMAILS_PER_DAY,
    DELAY_BETWEEN_EMAILS,
)

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_FILE = "token.json"

# Simple daily counter stored in a local JSON file
COUNTER_FILE = ".send_counter.json"


def get_gmail_service():
    """Authenticate and return Gmail API service object."""
    creds = None

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    to_name: str = "",
    dry_run: bool = False,
) -> bool:
    """
    Send a plain-text cold email.

    Args:
        to_email:  recipient's email address
        subject:   email subject line
        body:      plain text email body
        to_name:   recipient's name for the To: header (optional)
        dry_run:   if True, print the email but don't actually send it

    Returns:
        True if sent successfully, False otherwise.
    """
    if not _check_daily_limit():
        log.warning(f"Daily limit of {MAX_EMAILS_PER_DAY} emails reached. Skipping {to_email}.")
        return False

    if dry_run:
        print(f"\n{'─'*60}")
        print(f"DRY RUN — would send to: {to_email}")
        print(f"Subject: {subject}")
        print(f"\n{body}")
        print(f"{'─'*60}\n")
        return True

    try:
        service = get_gmail_service()
        message = _build_message(to_email, subject, body, to_name)
        service.users().messages().send(userId="me", body=message).execute()
        _increment_counter()
        log.info(f"Email sent to {to_email} — Subject: {subject}")
        _polite_delay()
        return True

    except HttpError as e:
        log.error(f"Gmail API error sending to {to_email}: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error sending to {to_email}: {e}")
        return False


def send_followup(
    to_email: str,
    to_name: str,
    company: str,
    role: str,
    original_subject: str,
    dry_run: bool = False,
) -> bool:
    """Send a short follow-up email referencing the original outreach."""
    first_name = to_name.split()[0] if to_name else "there"
    subject = f"Re: {original_subject}"
    body = f"""Hi {first_name},

Just wanted to follow up on my note from a few days ago about the {role} role at {company}.

I'm still very interested and would love to find 20 minutes to connect if you think there could be a fit.

Best,
{MY_NAME}
{MY_EMAIL}"""

    return send_email(to_email, subject, body, to_name, dry_run=dry_run)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_message(to_email: str, subject: str, body: str, to_name: str = "") -> dict:
    msg = MIMEMultipart("alternative")
    msg["From"]    = f"{MY_NAME} <{MY_EMAIL}>"
    msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def _check_daily_limit() -> bool:
    counter = _load_counter()
    today = _today_str()
    return counter.get(today, 0) < MAX_EMAILS_PER_DAY


def _increment_counter():
    counter = _load_counter()
    today = _today_str()
    counter[today] = counter.get(today, 0) + 1
    with open(COUNTER_FILE, "w") as f:
        json.dump(counter, f)


def _load_counter() -> dict:
    if Path(COUNTER_FILE).exists():
        with open(COUNTER_FILE) as f:
            return json.load(f)
    return {}


def _today_str() -> str:
    from datetime import date
    return date.today().isoformat()


def _polite_delay():
    delay = random.uniform(*DELAY_BETWEEN_EMAILS)
    log.info(f"Waiting {delay:.0f}s before next send...")
    time.sleep(delay)


# ─────────────────────────────────────────────────────────────────────────────
# CLI — run with --auth to set up OAuth, or --test for a dry run
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if "--auth" in sys.argv:
        get_gmail_service()
        print("Auth complete. token.json saved.")

    elif "--test" in sys.argv:
        send_email(
            to_email="test@example.com",
            subject="Test cold email",
            body="Hi,\n\nThis is a test.\n\nBest,\nSohaib",
            dry_run=True,
        )
