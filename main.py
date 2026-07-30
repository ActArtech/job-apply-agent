"""
main.py — orchestrates the full job application pipeline.

Usage:
    # Run the full automated pipeline (scrape → tailor → find email → send)
    python main.py run

    # Dry run — see what would be sent without actually sending
    python main.py run --dry-run
    
    # Run only email discoveries
    python main.py run --email-only
    
    # Run only direct applies
    python main.py run --direct-only

    # Apply to a single job manually (paste JD interactively)
    python main.py apply

    # Send follow-ups for applications with no reply in 5+ days
    python main.py followup

    # Just print pending follow-ups without sending
    python main.py followup --dry-run
"""

import argparse, json, logging, sys, time
from pathlib import Path

from config import MY_NAME
from scraper import (
    get_all_jobs,
    get_vetted_jobs,
    fetch_full_jd,
    _company_region,
    _work_mode,
)
from ai_engine import generate_application
from email_finder import find_hiring_manager, verify_email
from gmail_sender import send_email, send_followup
from applier import apply_directly
from tracker import (
    ensure_header_row, log_application,
    get_pending_followups, mark_followup_sent,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("apply.log"),
    ],
)
log = logging.getLogger(__name__)

# Skip companies already applied to (persisted in a local text file)
APPLIED_FILE = ".applied.txt"

def load_applied() -> set[str]:
    if Path(APPLIED_FILE).exists():
        with open(APPLIED_FILE) as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_applied(company: str, role: str):
    with open(APPLIED_FILE, "a") as f:
        f.write(f"{company.lower()}|{role.lower()}\n")

def already_applied(company: str, role: str) -> bool:
    applied = load_applied()
    return f"{company.lower()}|{role.lower()}" in applied


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline: scrape → tailor → find email/direct apply → send → track
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(dry_run: bool = False, min_match_score: int = 60, email_only: bool = False, direct_only: bool = False):
    log.info(f"{'DRY RUN — ' if dry_run else ''}Starting pipeline. min_match={min_match_score}%")
    ensure_header_row()

    jobs = get_vetted_jobs(max_per_source=40)
    log.info(f"Found {len(jobs)} relevant jobs total")

    applied_count = 0

    for job in jobs:
        if already_applied(job.company, job.title):
            log.info(f"Skip (already applied): {job.company} — {job.title}")
            continue

        log.info(f"\n{'='*55}\n{job.company} — {job.title}\n{job.url}")

        jd = job.description

        # 2. Determine Application Method
        contact = None
        to_email = None
        to_name = ""
        discovery_method = ""
        linkedin_url = ""
        
        if not direct_only and job.company_domain:
            contact = find_hiring_manager(job.company_domain, job.company)
            
        if contact:
            to_email = contact.email
            to_name = f"{contact.first_name} {contact.last_name}".strip()
            discovery_method = contact.discovery_method
            linkedin_url = contact.linkedin_url
            
        if to_email and verify_email(to_email):
            method = "email"
        else:
            method = "direct"
            
        if method == "email" and direct_only:
            log.info("Email found, but --direct-only specified. Falling back to direct apply.")
            method = "direct"
            
        if method == "direct" and email_only:
            log.info("No email found, and --email-only specified. Skipping.")
            continue
            
        if method == "direct" and not job.url:
            log.warning("No JD URL for direct apply. Skipping.")
            continue

        # 3. Generate tailored package
        pkg = generate_application(
            company=job.company,
            role=job.title,
            jd=jd,
            hiring_manager=to_name,
        )

        if not pkg:
            log.warning(f"AI generation failed for {job.company}. Skipping.")
            continue

        if pkg.match_score < min_match_score:
            log.info(f"Low match ({pkg.match_score}% < {min_match_score}%) — skipping {job.company}.")
            continue

        # Generate custom PDF
        try:
            from pdf_generator import generate_pdf
            import shutil
            
            # Use safe filename
            safe_company = "".join([c for c in job.company if c.isalpha() or c.isdigit() or c==' ']).replace(' ', '_')
            custom_pdf_path = f"resume_{safe_company}.pdf"
            
            if shutil.which("pdflatex"):
                pdf_path, page_count = generate_pdf(pkg, custom_pdf_path)
                
                if page_count > 1:
                    log.info(f"Resume is {page_count} pages. Doing a second pass to compact Technical Skills...")
                    skills = pkg.tailored_skills
                    compacted = {}
                    if "Languages" in skills and "Frontend" in skills:
                        compacted["Lang & Frontend"] = skills["Languages"] + skills["Frontend"]
                    else:
                        if "Languages" in skills: compacted["Languages"] = skills["Languages"]
                        if "Frontend" in skills: compacted["Frontend"] = skills["Frontend"]
                        
                    devops_key = "DevOps / Cloud" if "DevOps / Cloud" in skills else "Cloud & DevOps" if "Cloud & DevOps" in skills else None
                    if "Backend" in skills and devops_key:
                        compacted["Backend & DevOps"] = skills["Backend"] + skills[devops_key]
                    else:
                        if "Backend" in skills: compacted["Backend"] = skills["Backend"]
                        if devops_key: compacted[devops_key] = skills[devops_key]
                        
                    if "Databases" in skills:
                        compacted["Databases"] = skills["Databases"]
                        
                    for k, v in skills.items():
                        if k not in ["Languages", "Frontend", "Backend", "DevOps / Cloud", "Cloud & DevOps", "Databases"]:
                            compacted[k] = v
                            
                    pkg.tailored_skills = compacted
                    pdf_path, page_count = generate_pdf(pkg, custom_pdf_path)
                    log.info(f"Re-compiled. New page count: {page_count}")
                    
                log.info(f"Successfully generated custom PDF at {pdf_path}")
            else:
                log.warning("pdflatex not found on system. Using default resume.pdf")
                pdf_path = "resume.pdf"
        except Exception as e:
            log.warning(f"Failed to generate custom PDF for {job.company}: {e}. Falling back to default resume.pdf")
            pdf_path = "resume.pdf"

        # 4. Apply
        success = False
        outcome = ""
        
        if method == "email":
            success = send_email(
                to_email=to_email,
                subject=pkg.email_subject,
                body=pkg.email_body,
                to_name=to_name,
                dry_run=dry_run,
            )
            outcome = f"Cold Emailed via {discovery_method}"
        else:
            # For direct apply, we use the generated email body as the cover letter
            success = apply_directly(
                company=job.company,
                role=job.title,
                jd_url=job.url,
                cover_letter=pkg.full_email(), # Or pkg.email_body
                resume_path=pdf_path,
                dry_run=dry_run
            )
            outcome = "Auto-Applied (Direct)"

        # 5. Track in Google Sheets
        if success:
            log_application(
                company=job.company,
                role=job.title,
                jd_url=job.url,
                hiring_manager=to_name,
                their_email=to_email or "N/A",
                match_score=pkg.match_score,
                outcome=outcome,
                email_subject=pkg.email_subject,
                email_sent=(method == "email" and not dry_run),
                notes=f"keywords: {', '.join(pkg.keywords_matched[:5])}",
                linkedin_url=linkedin_url
            )
            if not dry_run:
                save_applied(job.company, job.title)
            applied_count += 1

        log.info(f"Applied: {applied_count} so far")

    log.info(f"\nPipeline done. Sent {applied_count} applications.")


# ─────────────────────────────────────────────────────────────────────────────
# Manual apply: one job at a time (paste JD interactively)
# ─────────────────────────────────────────────────────────────────────────────

def manual_apply(dry_run: bool = False):
    print("\n── Manual Application ──")
    company   = input("Company name: ").strip()
    role      = input("Role title:   ").strip()
    hm_name   = input("Hiring manager name (Enter to skip): ").strip()
    hm_email  = input("Their email (Enter to search Hunter.io): ").strip()
    why       = input("Why this company? (Enter to skip): ").strip()

    print("\nPaste the full job description. Press Enter twice when done:")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    jd = "\n".join(lines).strip()

    if not jd:
        print("No JD provided. Exiting.")
        return

    # Find email if not provided
    to_email = hm_email
    to_name  = hm_name
    discovery_method = "Manual"
    linkedin_url = ""
    
    if not to_email:
        domain = input("Company domain (e.g. razorpay.com): ").strip()
        if domain:
            contact = find_hiring_manager(domain, company)
            if contact:
                to_email = contact.email
                to_name  = f"{contact.first_name} {contact.last_name}".strip()
                discovery_method = contact.discovery_method
                linkedin_url = contact.linkedin_url
                print(f"Found: {to_name} <{to_email}> ({contact.position}) via {discovery_method}")

    if not to_email:
        print("No email found. You can still generate the content and send manually or direct apply.")

    # Generate
    pkg = generate_application(company, role, jd, hm_name or to_name, why)
    if not pkg:
        print("Generation failed.")
        return

    print(f"\n── Result ──")
    print(f"Match score: {pkg.match_score}%")
    print(f"Keywords matched: {', '.join(pkg.keywords_matched)}")
    print(f"\n── Tailored Bullets ──{pkg.resume_bullets_text()}")
    print(f"\n── Cold Email ──\n{pkg.full_email()}")

    if to_email:
        confirm = input(f"\nSend to {to_email}? [y/N]: ").strip().lower()
        if confirm == "y":
            sent = send_email(to_email, pkg.email_subject, pkg.email_body, to_name, dry_run=dry_run)
            if sent:
                ensure_header_row()
                log_application(
                    company=company, 
                    role=role, 
                    jd_url="", 
                    hiring_manager=to_name, 
                    their_email=to_email, 
                    match_score=pkg.match_score, 
                    outcome=f"Cold Emailed via {discovery_method}",
                    email_subject=pkg.email_subject,
                    linkedin_url=linkedin_url
                )
                save_applied(company, role)
                print("Sent and logged!")


# ─────────────────────────────────────────────────────────────────────────────
# Follow-ups
# ─────────────────────────────────────────────────────────────────────────────

def run_followups(dry_run: bool = False):
    pending = get_pending_followups()
    if not pending:
        print("No follow-ups due.")
        return

    print(f"\n{len(pending)} follow-ups due:\n")
    for p in pending:
        print(f"  {p['company']} — {p['role']} ({p['days_ago']} days ago) → {p['their_email']}")

    if not dry_run:
        confirm = input("\nSend all follow-ups? [y/N]: ").strip().lower()
        if confirm != "y":
            return

    for p in pending:
        sent = send_followup(
            to_email=p["their_email"],
            to_name=p["hiring_manager"],
            company=p["company"],
            role=p["role"],
            original_subject=p["email_subject"],
            dry_run=dry_run,
        )
        if sent and not dry_run:
            mark_followup_sent(p["row_number"])


import csv
# ─────────────────────────────────────────────────────────────────────────────
# Phase CSV outputs
# ─────────────────────────────────────────────────────────────────────────────

def write_jobs_csv(csv_file: str, jobs):
    try:
        with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Company",
                "Title",
                "Location",
                "Work Mode",
                "Company Region",
                "Source",
                "URL",
                "Remote",
                "Company Domain",
                "Description",
                "Reason",
            ])
            for job in jobs:
                writer.writerow([
                    job.company,
                    job.title,
                    job.location,
                    _work_mode(job),
                    _company_region(job),
                    job.source,
                    job.url,
                    "Yes" if job.remote else "No",
                    job.company_domain,
                    job.description,
                    job.vetting_reason
                ])
        log.info(f"\nSuccessfully wrote {len(jobs)} jobs to {csv_file}")
    except Exception as e:
        log.error(f"Failed to write jobs to CSV: {e}")


def scrape_only(max_per_source: int = 40):
    log.info("Starting scrape-only mode (Phase 1 gather only)...")
    
    jobs = get_all_jobs(max_per_source=max_per_source)
    if not jobs:
        log.info("No phase 1 jobs found.")
        return

    write_jobs_csv("phase1_jobs.csv", jobs)


def vet_only(max_per_source: int = 40):
    log.info("Starting Phase 2 vet-only mode (AI vetting, no apply/send)...")

    jobs = get_vetted_jobs(max_per_source=max_per_source)
    if not jobs:
        log.info("No phase 2 AI-approved jobs found.")
        return

    write_jobs_csv("phase2_jobs.csv", jobs)

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f"{MY_NAME}'s automated job application system"
    )
    sub = parser.add_subparsers(dest="command")

    scrape_p = sub.add_parser("scrape-only", help="Scrape phase 1 jobs into CSV without applying")
    scrape_p.add_argument("--max", type=int, default=100, help="Max jobs per source to scrape")

    vet_p = sub.add_parser("vet-only", help="Run Phase 2 AI vetting into CSV without applying")
    vet_p.add_argument("--max", type=int, default=100, help="Max jobs per source to scrape before vetting")

    phase2_csv_p = sub.add_parser("phase2-csv", help="Alias for vet-only CSV output")
    phase2_csv_p.add_argument("--max", type=int, default=100, help="Max jobs per source to scrape before vetting")

    run_p = sub.add_parser("run", help="Full automated pipeline")
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--min-match", type=int, default=60, help="Min match score 0-100 (default 60)")
    run_p.add_argument("--email-only", action="store_true", help="Only send emails, skip direct apply")
    run_p.add_argument("--direct-only", action="store_true", help="Only do direct applies, skip emails")

    apply_p = sub.add_parser("apply", help="Apply to a single job manually")
    apply_p.add_argument("--dry-run", action="store_true")

    followup_p = sub.add_parser("followup", help="Send follow-ups for no-reply applications")
    followup_p.add_argument("--dry-run", action="store_true")

    phase1_p = sub.add_parser("phase1", help="Run isolated Phase 1 into artifacts/applications")
    phase1_p.add_argument("--max", type=int, default=20)

    phase2_p = sub.add_parser("phase2", help="Run isolated Phase 2 (Vet)")
    phase2_p.add_argument("--max", type=int, default=20)

    phase3_p = sub.add_parser("phase3", help="Generate artifacts for one curated job")
    phase3_p.add_argument("--job-id", required=True)

    phase3_all_p = sub.add_parser("phase3-all", help="Generate artifacts for all approved curated jobs")
    phase3_all_p.add_argument("--limit", type=int, default=20)

    sub.add_parser("dashboard-export", help="Export dashboard job list")

    args = parser.parse_args()

    def print_phase_result(result):
        print(json.dumps(result, ensure_ascii=False))

    if args.command == "scrape-only":
        scrape_only(max_per_source=args.max)
    elif args.command in {"vet-only", "phase2-csv"}:
        vet_only(max_per_source=args.max)
    elif args.command == "run":
        run_pipeline(
            dry_run=args.dry_run, 
            min_match_score=args.min_match,
            email_only=args.email_only,
            direct_only=args.direct_only
        )
    elif args.command == "apply":
        manual_apply(dry_run=args.dry_run)
    elif args.command == "followup":
        run_followups(dry_run=args.dry_run)
    elif args.command == "phase1":
        from phase_runner import run_phase1
        print_phase_result(run_phase1(max_per_source=args.max))
    elif args.command == "phase2":
        from phase_runner import run_phase2
        print_phase_result(run_phase2(max_per_source=args.max))
    elif args.command == "phase3":
        from phase_runner import run_phase3
        print_phase_result(run_phase3(job_id=args.job_id))
    elif args.command == "phase3-all":
        from phase_runner import run_phase3_all
        print_phase_result(run_phase3_all(limit=args.limit))
    elif args.command == "dashboard-export":
        from artifact_store import ArtifactStore
        store = ArtifactStore()
        print_phase_result(store.list_jobs())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
