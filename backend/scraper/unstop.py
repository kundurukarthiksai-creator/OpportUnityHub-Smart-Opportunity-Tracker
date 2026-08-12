"""
Unstop Scraper — Real competitions & internships
Strategy 1: Use Unstop's public API endpoint (JSON)
Strategy 2: Fall back to HTML parsing
Unstop uses Angular but exposes API endpoints we can call.
"""
import requests
import time
import random
import re
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from backend.cleaner import clean_all

BASE_URL = "https://unstop.com"

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://unstop.com",
    "Referer": "https://unstop.com/competitions",
    "Content-Type": "application/json",
}

HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://unstop.com/",
}


def _parse_date(date_str: str) -> str:
    """Parse various date formats into YYYY-MM-DD."""
    if not date_str:
        return "N/A"
    # ISO format from API
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(str(date_str)[:19], fmt[:len(str(date_str)[:19])]).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return "N/A"


def _estimate_deadline(n: int = 25) -> str:
    return (datetime.now() + timedelta(days=n)).strftime("%Y-%m-%d")


def _try_unstop_api(filters: dict) -> list[dict]:
    """Try Unstop's API endpoints."""
    opp_type = filters.get("type", "all")
    results = []

    # Unstop API endpoints (discovered from network analysis)
    api_configs = []

    if opp_type in ("all", "hackathon"):
        api_configs.append({
            "url": "https://unstop.com/api/public/opportunity/search-result",
            "params": {
                "opportunity": "competitions",
                "per_page": 30,
                "oppstatus": "open",
                "page": 1,
            }
        })

    if opp_type in ("all", "internship"):
        api_configs.append({
            "url": "https://unstop.com/api/public/opportunity/search-result",
            "params": {
                "opportunity": "internships",
                "per_page": 30,
                "oppstatus": "open",
                "page": 1,
            }
        })

    for config in api_configs:
        try:
            resp = requests.get(
                config["url"],
                headers=HEADERS_API,
                params=config["params"],
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get("data", {}).get("data", []) or
                         data.get("data", []) or
                         data.get("results", []) or
                         data.get("opportunities", []))

                if items:
                    for item in items:
                        entry = _map_unstop_item(item, config["params"].get("opportunity", "competitions"))
                        if entry:
                            results.append(entry)
                    print(f"[unstop] Got {len(items)} items from API for {config['params'].get('opportunity')}")
        except Exception as e:
            print(f"[unstop] API failed: {e}")

    return results


def _map_unstop_item(item: dict, category: str) -> dict | None:
    """Map an Unstop API item to our standard format."""
    title = (item.get("title") or item.get("name") or
             item.get("competition_name") or item.get("internship_name") or "")
    org = (item.get("organisation", {}) if isinstance(item.get("organisation"), dict) else {})
    company = (org.get("name") or item.get("organisation_name") or
               item.get("company_name") or "Unstop")

    if not title:
        return None

    # Deadline
    deadline_raw = (item.get("application_deadline") or item.get("deadline") or
                    item.get("end_date") or item.get("last_date") or "")
    deadline = _parse_date(str(deadline_raw)[:10]) if deadline_raw else _estimate_deadline()

    # Prize/stipend
    prize = item.get("prize_money") or item.get("stipend") or item.get("reward") or "N/A"
    if isinstance(prize, (int, float)) and prize > 0:
        prize = f"₹{int(prize):,}"
    elif not prize or prize == 0:
        prize = "N/A"

    # Link extraction
    raw_link = (item.get("public_url") or item.get("share_url") or 
                item.get("opportunity_url") or item.get("reg_url") or 
                item.get("url") or "")
    
    if raw_link and str(raw_link).startswith("http"):
        link = str(raw_link)
    elif raw_link:
        clean_path = str(raw_link).lstrip("/")
        link = f"{BASE_URL}/{clean_path}"
    else:
        slug = str(item.get("slug") or item.get("seo_url") or "").strip()
        if slug:
            clean_slug = slug.lstrip("/")
            if clean_slug.startswith("p/") or clean_slug.startswith("o/") or clean_slug.startswith("competitions/") or clean_slug.startswith("internships/"):
                link = f"{BASE_URL}/{clean_slug}"
            else:
                link = f"{BASE_URL}/p/{clean_slug}"
        else:
            link = f"{BASE_URL}/competitions" if category == "competitions" else f"{BASE_URL}/internships"

    opp_type_val = "hackathon" if category == "competitions" else "internship"
    location = item.get("city") or item.get("location") or "India / Remote"

    return {
        "title": str(title),
        "role": str(title),
        "organization": str(company),
        "type": opp_type_val,
        "location": str(location),
        "stipend": str(prize),
        "deadline": deadline,
        "apply_link": link,
        "description": f"{opp_type_val.capitalize()} on Unstop: {title} by {company}.",
        "source": "unstop",
        "domain": "general",
        "verified": True,
    }


def _try_html_scrape(filters: dict) -> list[dict]:
    """Fall back to HTML scraping for Unstop."""
    opp_type = filters.get("type", "all")
    results = []

    urls = []
    if opp_type in ("all", "hackathon"):
        urls.append(("hackathon", f"{BASE_URL}/competitions"))
    if opp_type in ("all", "internship"):
        urls.append(("internship", f"{BASE_URL}/internships"))

    for category, url in urls:
        try:
            resp = requests.get(url, headers=HEADERS_HTML, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Try to extract from JSON-LD or embedded script data
            for script in soup.find_all("script"):
                src = script.string or ""
                if "opportunities" in src.lower() or "competition" in src.lower():
                    # Look for JSON array
                    matches = re.findall(r'\{[^{}]*?"title"[^{}]*?\}', src)
                    for m in matches[:10]:
                        try:
                            item = json.loads(m)
                            entry = _map_unstop_item(item, "competitions" if category == "hackathon" else "internships")
                            if entry:
                                results.append(entry)
                        except Exception:
                            pass

            # Try card selectors
            card_selectors = [
                ".opportunity-card",
                ".card--opportunity",
                "article",
                "[class*='card']",
                ".listing-card",
                ".opportunity",
            ]
            cards = []
            for sel in card_selectors:
                cards = soup.select(sel)
                if len(cards) > 3:
                    print(f"[unstop] Found {len(cards)} HTML cards with: {sel}")
                    break

            for card in cards[:20]:
                try:
                    title_el = (card.select_one("h2") or card.select_one("h3") or
                                card.select_one(".title") or card.select_one("[class*='title']"))
                    company_el = (card.select_one(".company") or card.select_one(".org-name") or
                                  card.select_one("[class*='company']") or card.select_one("[class*='org']"))
                    prize_el = (card.select_one(".prize") or card.select_one("[class*='prize']") or
                                card.select_one("[class*='stipend']") or card.select_one(".reward"))
                    deadline_el = (card.select_one("time") or card.select_one("[class*='deadline']") or
                                   card.select_one("[class*='date']"))
                    link_el = card.find("a", href=True)

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else "Unstop"
                    prize = prize_el.get_text(strip=True) if prize_el else "N/A"
                    deadline_text = deadline_el.get_text(strip=True) if deadline_el else ""
                    deadline = _parse_date(deadline_text) if deadline_text else _estimate_deadline()
                    href = link_el["href"] if link_el else url
                    if href and not href.startswith("http"):
                        href = BASE_URL + href

                    if not title:
                        continue

                    results.append({
                        "title": title,
                        "role": title,
                        "organization": company,
                        "type": category,
                        "location": "India / Remote",
                        "stipend": prize,
                        "deadline": deadline,
                        "apply_link": href,
                        "description": f"{category.capitalize()} on Unstop: {title} by {company}.",
                        "source": "unstop",
                        "domain": "general",
                        "verified": True,
                    })
                except Exception as e:
                    print(f"[unstop] HTML card error: {e}")
                    continue

        except Exception as e:
            print(f"[unstop] HTML fetch error for {url}: {e}")

    return results


def scrape(filters: dict = None) -> list[dict]:
    filters = filters or {}
    print("[unstop] Starting scrape...")

    # Try API first
    results = _try_unstop_api(filters)

    if not results:
        print("[unstop] API empty, trying HTML scrape...")
        results = _try_html_scrape(filters)

    time.sleep(random.uniform(0.8, 1.5))
    print(f"[unstop] Total raw results: {len(results)}")
    cleaned = clean_all(results)
    print(f"[unstop] After cleaning: {len(cleaned)} results")
    return cleaned
