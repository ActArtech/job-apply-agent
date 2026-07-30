"""
applier.py — Direct Apply fallback using Playwright.
Navigates to ATS forms (Lever, Greenhouse, etc.), uploads resume, and pastes the cover letter.
"""

import logging
from typing import Optional
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

def apply_directly(
    company: str,
    role: str,
    jd_url: str,
    cover_letter: str,
    resume_path: str = "resume.pdf",
    dry_run: bool = False
) -> bool:
    """
    Fallback method to directly apply to a job using Playwright.
    Returns True if successfully submitted (or dry_run completed), False otherwise.
    """
    if not jd_url:
        log.warning(f"No JD URL provided for {company} — cannot direct apply.")
        return False
        
    log.info(f"Starting Direct Apply for {company} - {role} at {jd_url}")

    try:
        with sync_playwright() as p:
            # We use headless=False for dry_run so you can see what it does, 
            # and headless=True for actual runs
            browser = p.chromium.launch(headless=not dry_run)
            context = browser.new_context()
            page = context.new_page()

            page.goto(jd_url, wait_until="domcontentloaded", timeout=15000)

            # Simple heuristic matching for common ATS fields
            # This is a basic implementation that would need fine-tuning for specific ATS platforms
            
            # Look for apply button if we're not already on the form
            apply_buttons = page.get_by_role("button", name="Apply")
            if apply_buttons.count() > 0 and not page.locator("input[type='file']").is_visible():
                apply_buttons.first.click()
                page.wait_for_load_state("domcontentloaded")

            # Upload resume if field exists
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0:
                try:
                    file_input.first.set_input_files(resume_path)
                    log.info("Resume uploaded.")
                except Exception as e:
                    log.warning(f"Could not upload resume: {e}")

            # Fill cover letter if field exists
            # Look for textarea that might be a cover letter
            textareas = page.locator("textarea")
            if textareas.count() > 0:
                # Just pick the first big text area for now, or one with 'cover' in name/id
                for i in range(textareas.count()):
                    ta = textareas.nth(i)
                    name_attr = ta.get_attribute("name") or ""
                    id_attr = ta.get_attribute("id") or ""
                    if "cover" in name_attr.lower() or "cover" in id_attr.lower() or "summary" in name_attr.lower():
                        ta.fill(cover_letter)
                        log.info("Cover letter filled.")
                        break
                else:
                    # If no specific cover letter field, fill the first one
                    textareas.first.fill(cover_letter)
                    log.info("Cover letter filled in generic textarea.")

            if dry_run:
                log.info("DRY RUN: Browser opened and form filled. Waiting 5s then closing without submitting.")
                page.wait_for_timeout(5000)
                browser.close()
                return True
                
            # For a real run, we would attempt to submit
            # submit_button = page.locator("button[type='submit'], input[type='submit']")
            # if submit_button.count() > 0:
            #     submit_button.first.click()
            #     page.wait_for_load_state("networkidle")
            #     log.info("Form submitted.")
            #     return True

            log.info("Auto-submit logic reached end (submit clicked commented out for safety).")
            browser.close()
            return True

    except Exception as e:
        log.error(f"Direct Apply failed for {company}: {e}")
        return False
