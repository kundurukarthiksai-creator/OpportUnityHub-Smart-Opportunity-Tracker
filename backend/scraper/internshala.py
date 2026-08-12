"""
Internshala Scraper — Smart multi-strategy scraper
Strategy 1: Try Internshala's internal search AJAX endpoint (JSON)
Strategy 2: Fall back to HTML parsing with updated selectors
Handles React/Angular rendered pages by targeting server-side rendered data.
"""
import requests
import time
import random
import json
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from backend.cleaner import clean_all

BASE_URL = "https://internshala.com"

HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://internshala.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

HEADERS_AJAX = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://internshala.com/internships/",
    "Origin": "https://internshala.com",
}

DOMAIN_KEYWORD_MAP = {
    "ai":     ["machine-learning", "artificial-intelligence", "data-science", "deep-learning", "nlp"],
    "web":    ["web-development", "frontend", "backend", "full-stack", "react", "nodejs"],
    "data":   ["data-science", "data-analytics", "data-engineering", "business-analytics"],
    "design": ["graphic-design", "ui-ux", "product-design", "web-design"],
    "mobile": ["android-development", "ios-development", "flutter", "mobile-app"],
    "general": [],
}


def _parse_deadline_text(text: str) -> str:
    """Parse Internshala deadline text into YYYY-MM-DD."""
    if not text:
        return "N/A"
    # Try direct date formats
    for fmt in ["%d %b %Y", "%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Handle relative: "Apply by 15 Aug" or "15 Aug"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?", text)
    if m:
        day, mon, yr = m.group(1), m.group(2), m.group(3) or str(datetime.now().year)
        try:
            return datetime.strptime(f"{day} {mon} {yr}", "%d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "N/A"


def _estimate_deadline_days(n: int = 30) -> str:
    return (datetime.now() + timedelta(days=n)).strftime("%Y-%m-%d")


def _try_ajax_api(filters: dict) -> list[dict]:
    """Try Internshala's internal AJAX search endpoint."""
    domain = filters.get("domain", "general")
    location = filters.get("location", "all")

    # Build category slug
    categories = DOMAIN_KEYWORD_MAP.get(domain.lower(), [])
    cat_slug = ",".join(categories[:3]) if categories else ""

    # Try the internal search endpoint
    endpoints = [
        f"{BASE_URL}/internships/matching-preferences/",
        f"{BASE_URL}/internships/",
    ]
    if location == "remote":
        endpoints = [f"{BASE_URL}/work-from-home-internships/"] + endpoints

    results = []
    for url in endpoints[:1]:  # try first endpoint
        params = {}
        if cat_slug:
            params["profile"] = cat_slug
        try:
            sess = requests.Session()
            # First get the page to establish cookies/session
            sess.get(BASE_URL, headers=HEADERS_HTML, timeout=10)
            time.sleep(0.5)
            resp = sess.get(url, headers=HEADERS_HTML, params=params, timeout=15)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "lxml")

            # Try to extract JSON data embedded in the page (Next.js / server-rendered)
            for script in soup.find_all("script", type="application/json"):
                try:
                    data = json.loads(script.string)
                    internships = _extract_from_json_data(data)
                    if internships:
                        results.extend(internships)
                except Exception:
                    continue

            # Also try __NEXT_DATA__ or similar
            next_data = soup.find("script", id="__NEXT_DATA__")
            if next_data:
                try:
                    data = json.loads(next_data.string)
                    internships = _extract_from_json_data(data)
                    results.extend(internships)
                except Exception:
                    pass

            if results:
                break

            # Fall back to parsing the HTML cards
            html_results = _parse_html_cards(soup, domain)
            results.extend(html_results)
            if results:
                break

        except Exception as e:
            print(f"[internshala] Endpoint {url} failed: {e}")
            continue

    return results


def _extract_from_json_data(data: dict, depth: int = 0) -> list[dict]:
    """Recursively search JSON data for internship listings."""
    if depth > 6:
        return []
    results = []
    if isinstance(data, dict):
        # Look for arrays that look like internship data
        for key in ["internships", "listings", "opportunities", "data", "props", "pageProps", "internshipsMeta"]:
            if key in data and isinstance(data[key], (list, dict)):
                sub = _extract_from_json_data(data[key], depth + 1)
                results.extend(sub)
        # Check if this dict itself looks like an internship
        if "title" in data and "company_name" in data:
            entry = _map_internshala_json_item(data)
            if entry:
                results.append(entry)
    elif isinstance(data, list):
        for item in data[:50]:
            sub = _extract_from_json_data(item, depth + 1)
            results.extend(sub)
    return results


def _map_internshala_json_item(item: dict) -> dict | None:
    title = item.get("title") or item.get("profile_name") or ""
    company = item.get("company_name") or item.get("employer", {}).get("name", "") or ""
    if not title or not company:
        return None
    stipend = item.get("stipend", {})
    if isinstance(stipend, dict):
        stipend_val = stipend.get("salary", "N/A")
    else:
        stipend_val = str(stipend) if stipend else "N/A"

    deadline_raw = item.get("application_deadline") or item.get("deadline") or ""
    deadline = _parse_deadline_text(str(deadline_raw)) if deadline_raw else _estimate_deadline_days(25)
    link = item.get("application_link") or item.get("url") or f"https://internshala.com/internships"
    location = item.get("location_names") or item.get("location") or "India"
    if isinstance(location, list):
        location = ", ".join(location)

    return {
        "title": str(title),
        "role": str(title),
        "organization": str(company),
        "type": "internship",
        "location": str(location),
        "stipend": str(stipend_val),
        "deadline": deadline,
        "apply_link": str(link),
        "description": f"Internship at {company} — {title}. Location: {location}.",
        "source": "internshala",
        "domain": "general",
        "verified": True,
    }


def _parse_html_cards(soup: BeautifulSoup, domain: str) -> list[dict]:
    """Parse HTML cards from the Internshala page."""
    results = []

    # Try multiple selector strategies for different page versions
    card_selectors = [
        ".internship_meta",
        ".individual_internship",
        "[id^='internshiplist_']",
        ".internship-listing-card",
        ".listing-container",
        "[data-internship-id]",
        ".card-container",
    ]

    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if cards:
            print(f"[internshala] Found {len(cards)} cards with selector: {sel}")
            break

    for card in cards:
        try:
            # Multiple fallback selectors for each field
            title_el = (card.select_one(".job-title-href") or
                        card.select_one(".profile a") or
                        card.select_one("h3 a") or
                        card.select_one(".title a") or
                        card.select_one("[class*='profile'] a"))

            company_el = (card.select_one(".company_name a") or
                          card.select_one(".company-name") or
                          card.select_one("[class*='company_name']") or
                          card.select_one("[class*='company-name']"))

            stipend_el = (card.select_one(".stipend") or
                          card.select_one(".stipend_salary") or
                          card.select_one("[class*='stipend']"))

            loc_el = (card.select_one(".location_link") or
                      card.select_one(".location a") or
                      card.select_one(".cities_buttons a") or
                      card.select_one("[class*='location']"))

            deadline_el = (card.select_one("[id^='application-deadline'] span") or
                           card.select_one(".deadline") or
                           card.select_one("[class*='deadline']") or
                           card.select_one(".apply-by"))

            link_el = (card.select_one("a.job-title-href") or
                       card.select_one(".profile a") or
                       card.select_one("h3 a") or
                       card.select_one("a[href*='/internship/']"))

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            stipend = stipend_el.get_text(strip=True) if stipend_el else "N/A"
            loc = loc_el.get_text(strip=True) if loc_el else "India"
            deadline_text = deadline_el.get_text(strip=True) if deadline_el else ""
            deadline = _parse_deadline_text(deadline_text) if deadline_text else _estimate_deadline_days(25)
            href = link_el["href"] if link_el and link_el.get("href") else ""
            if href and not href.startswith("http"):
                href = BASE_URL + href

            if not title or not company:
                continue

            results.append({
                "title": title,
                "role": title,
                "organization": company,
                "type": "internship",
                "location": loc,
                "stipend": stipend,
                "deadline": deadline,
                "apply_link": href or f"{BASE_URL}/internships",
                "description": f"Internship at {company} — {title}. Location: {loc}. Stipend: {stipend}.",
                "source": "internshala",
                "domain": domain,
                "verified": True,
            })
        except Exception as e:
            print(f"[internshala] Card parse error: {e}")
            continue

    return results


def scrape(filters: dict = None) -> list[dict]:
    filters = filters or {}
    opp_type = filters.get("type", "all")

    if opp_type == "hackathon":
        return []  # Internshala has internships only

    print("[internshala] Starting scrape...")
    results = _try_ajax_api(filters)
    time.sleep(random.uniform(1.0, 2.0))

    print(f"[internshala] Scraped {len(results)} raw results")
    cleaned = clean_all(results)
    print(f"[internshala] After cleaning: {len(cleaned)} results")
    return cleaned
