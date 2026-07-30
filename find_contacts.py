import csv
import logging
from email_finder import find_hiring_manager
import os
from dotenv import load_dotenv

# Load the env variables explicitly
load_dotenv()

logging.basicConfig(level=logging.WARNING)

def run():
    print(f"APOLLO_API_KEY loaded: {bool(os.environ.get('APOLLO_API_KEY'))}")
    print("Reading vetted_jobs.csv...")
    try:
        with open("vetted_jobs.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            jobs = list(reader)
    except FileNotFoundError:
        print("No vetted_jobs.csv found.")
        return

    print(f"Found {len(jobs)} jobs. Running Apollo search...")
    for job in jobs:
        company = job["Company"]
        # Guess domain
        domain = f"{company.lower().replace(' ', '').replace('.','').replace('-','')}.com"
        
        print(f"\nTarget: {company} (Domain: {domain})")
        contact = find_hiring_manager(domain, company)
        
        if contact:
            print(f"  ✅ SUCCESS ({contact.discovery_method})")
            print(f"     Name:     {contact.first_name} {contact.last_name}")
            print(f"     Title:    {contact.position}")
            print(f"     Email:    {contact.email}")
            print(f"     LinkedIn: {contact.linkedin_url}")
        else:
            print(f"  ❌ No contact found.")

if __name__ == "__main__":
    run()
