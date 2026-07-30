import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import collections

def test_instahyre_selectors():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        url = "https://www.instahyre.com/software-engineering-jobs/"
        
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
            
        html = page.content()
        browser.close()

    with open('instahyre_debug.html', 'w') as f:
        f.write(html)
        
    print("Wrote instahyre_debug.html")

if __name__ == "__main__":
    test_instahyre_selectors()
