"""
tracker.py — log and update job applications in Google Sheets.

Sheet columns: Date | Company | Role | JD URL | Hiring Manager | Their Email |
               Match Score | Email Sent? | Email Subject | Follow-up Sent? | Response | Notes

Setup:
1. Create a Google Sheet and copy its ID from the URL
2. Enable Google Sheets API in console.cloud.google.com (same project as Gmail)
3. The same credentials.json + token.json work for both APIs
   — just add the Sheets scope (done automatically here)
4. Set GOOGLE_SHEET_ID in config.py or as env var
"""

import logging
from datetime import date
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pathlib import Path

from config import GOOGLE_SHEET_ID, GMAIL_CREDENTIALS, SHEET_COLUMNS

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]
TOKEN_FILE = "token.json"


def _get_sheets_service():
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
    return build("sheets", "v4", credentials=creds)


def ensure_header_row():
    """Create the header row if the sheet is empty."""
    if not GOOGLE_SHEET_ID:
        log.warning("GOOGLE_SHEET_ID not set — skipping tracker initialization.")
        return
        
    try:
        svc = _get_sheets_service()
        result = svc.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="Sheet1!A1:M1",
        ).execute()

        if not result.get("values"):
            svc.spreadsheets().values().update(
                spreadsheetId=GOOGLE_SHEET_ID,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body={"values": [SHEET_COLUMNS]},
            ).execute()
            log.info("Header row created in Google Sheet.")
    except Exception as e:
        log.error(f"Failed to ensure header row: {e}")


def log_application(
    company: str,
    role: str,
    jd_url: str,
    hiring_manager: str,
    their_email: str,
    match_score: int,
    outcome: str,
    email_subject: str,
    email_sent: bool = True,
    notes: str = "",
    linkedin_url: str = "",
) -> Optional[int]:
    """
    Append a new application row to a local CSV and Google Sheets.
    Returns the row number that was written to Google Sheets, or None.
    """
    row = [
        date.today().isoformat(),      # Date
        company,                        # Company
        role,                           # Role
        jd_url,                         # JD URL
        hiring_manager,                 # Hiring Manager
        their_email,                    # Their Email
        linkedin_url,                   # LinkedIn URL
        f"{match_score}%",             # Match Score
        outcome,                        # Outcome
        "Yes" if email_sent else "No", # Email Sent?
        email_subject,                  # Email Subject
        "No",                           # Follow-up Sent? (default No)
        "",                             # Response (blank until they reply)
        notes,                          # Notes
    ]

    # ALWAYS log locally to CSV
    import csv
    csv_file = "applications.csv"
    file_exists = Path(csv_file).exists()
    try:
        with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(SHEET_COLUMNS)
            writer.writerow(row)
        log.info(f"Logged locally to {csv_file}")
    except Exception as e:
        log.error(f"Failed to write to local CSV: {e}")

    # THEN log to Google Sheets if configured
    if not GOOGLE_SHEET_ID:
        log.warning("GOOGLE_SHEET_ID not set — skipping Google Sheets tracker.")
        return None

    try:
        svc = _get_sheets_service()
        result = svc.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="Sheet1!A:N",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        updated_range = result.get("updates", {}).get("updatedRange", "")
        row_num = _parse_row_number(updated_range)
        log.info(f"Logged to Google Sheet row {row_num}: {company} — {role}")
        return row_num

    except Exception as e:
        log.error(f"Failed to log to Google Sheet: {e}")
        return None


def mark_followup_sent(row_number: int):
    """Update the Follow-up Sent? column for a given row."""
    if not GOOGLE_SHEET_ID or not row_number:
        return
    try:
        svc = _get_sheets_service()
        # Column L = Follow-up Sent? (index 11)
        svc.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"Sheet1!L{row_number}",
            valueInputOption="RAW",
            body={"values": [["Yes"]]},
        ).execute()
        log.info(f"Marked follow-up sent for row {row_number}")
    except Exception as e:
        log.error(f"Failed to mark follow-up: {e}")


def mark_response_received(row_number: int, response_type: str):
    """
    Update the Response column.
    response_type: "Positive" | "Rejection" | "No reply" | "Ghosted"
    """
    if not GOOGLE_SHEET_ID or not row_number:
        return
    try:
        svc = _get_sheets_service()
        # Column M = Response (index 12)
        svc.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"Sheet1!M{row_number}",
            valueInputOption="RAW",
            body={"values": [[response_type]]},
        ).execute()
        log.info(f"Logged response '{response_type}' for row {row_number}")
    except Exception as e:
        log.error(f"Failed to log response: {e}")


def get_pending_followups(days_threshold: int = 5) -> list[dict]:
    """
    Return rows where email was sent, follow-up not yet sent,
    and it's been >= days_threshold days.
    """
    if not GOOGLE_SHEET_ID:
        return []

    try:
        from datetime import datetime, timedelta
        svc = _get_sheets_service()
        result = svc.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="Sheet1!A:N",
        ).execute()

        rows = result.get("values", [])
        if len(rows) <= 1:
            return []   # only header or empty

        pending = []
        cutoff = datetime.now() - timedelta(days=days_threshold)

        for i, row in enumerate(rows[1:], start=2):   # skip header, 1-indexed
            if len(row) < 12:
                row += [""] * (12 - len(row))

            sent_date_str = row[0]
            email_sent    = row[9]
            followup_sent = row[11] if len(row) > 11 else "No"
            response      = row[12] if len(row) > 12 else ""

            if email_sent != "Yes" or followup_sent == "Yes" or response:
                continue

            try:
                sent_date = datetime.fromisoformat(sent_date_str)
                if sent_date <= cutoff:
                    pending.append({
                        "row_number": i,
                        "company":         row[1],
                        "role":            row[2],
                        "hiring_manager":  row[4],
                        "their_email":     row[5],
                        "email_subject":   row[10],
                        "days_ago":        (datetime.now() - sent_date).days,
                    })
            except ValueError:
                continue

        log.info(f"Found {len(pending)} applications due for follow-up")
        return pending

    except Exception as e:
        log.error(f"Failed to fetch pending follow-ups: {e}")
        return []


def _parse_row_number(updated_range: str) -> Optional[int]:
    """'Sheet1!A42:L42' → 42"""
    import re
    match = re.search(r"(\d+):", updated_range)
    return int(match.group(1)) if match else None
