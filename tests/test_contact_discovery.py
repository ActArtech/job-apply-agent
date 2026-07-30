import logging
from email_finder import find_hiring_manager

def test_contact_discovery():
    logging.basicConfig(level=logging.INFO)
    domain = "razorpay.com"
    company_name = "Razorpay"
    print(f"\n--- Testing Contact Discovery for {company_name} ({domain}) ---")
    
    contact = find_hiring_manager(domain, company_name)
    
    if contact:
        print(f"✅ Found Contact:")
        print(f"   Name: {contact.first_name} {contact.last_name}")
        print(f"   Email: {contact.email}")
        print(f"   Role: {contact.position}")
        print(f"   LinkedIn: {contact.linkedin_url}")
        print(f"   Method: {contact.discovery_method}")
    else:
        print(f"❌ No contact found for {domain}")

if __name__ == "__main__":
    test_contact_discovery()
