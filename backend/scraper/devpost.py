"""
Devpost Scraper — Real hackathon data
Strategy 1: Use Devpost's public search API (JSON endpoint)
Strategy 2: Fall back to HTML card parsing
"""
import requests
import time
import random
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from backend.cleaner import clean_all

BASE_URL = "https://devpost.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://devpost.com/hackathons",
}

HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://devpost.com/",
}


def _parse_devpost_date(text: str) -> str:
    """Parse Devpost date strings."""
    if not text:
        return "N/A"
    text = text.strip()
    # "Jul 30, 2025" or "July 30, 2025"
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d %b %Y"]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try to extract date numbers
    m = re.search(r"(\w+ \d{1,2},?\s*\d{4})", text)
    if m:
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"]:
            try:
                return datetime.strptime(m.group(1).replace(",", ""), fmt.replace(",", "")).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return "N/A"


def _estimate_deadline_days(n: int = 30) -> str:
    return (datetime.now() + timedelta(days=n)).strftime("%Y-%m-%d")


def _try_devpost_api(filters: dict) -> list[dict]:
    """Try Devpost's internal search API endpoint."""
    location = filters.get("location", "all")
    results = []

    # Devpost has a search API endpoint
    api_urls = [
        "https://devpost.com/hackathons.json",
        "https://devpost.com/api/hackathons.json",
    ]

    params = {
        "challenge_type[]": "all",
        "open_to[]": "public",
        "status[]": "upcoming",
        "page": 1,
        "per_page": 30,
        "order_by": "deadline",
        "sort_by": "submission-deadline",
    }
    if location == "remote":
        params["online_only"] = "true"

    for api_url in api_urls:
        try:
            resp = requests.get(api_url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                hackathons = data.get("hackathons", [])
                if hackathons:
                    for h in hackathons:
                        entry = _map_devpost_api_item(h)
                        if entry:
                            results.append(entry)
                    print(f"[devpost] Got {len(results)} hackathons from API: {api_url}")
                    return results
        except Exception as e:
            print(f"[devpost] API {api_url} failed: {e}")
            continue

    return results


def _map_devpost_api_item(h: dict) -> dict | None:
    title = h.get("title") or h.get("hackathon_name") or ""
    if not title:
        return None

    url = h.get("url") or h.get("link") or ""
    prize = h.get("prize_amount") or h.get("prize") or "N/A"
    if isinstance(prize, (int, float)):
        prize = f"${prize:,}"

    # Get deadline
    deadline_raw = (h.get("submission_period_dates") or
                    h.get("deadline") or
                    h.get("end_date") or "")
    deadline = "N/A"
    if deadline_raw:
        # "Jun 28, 2025 – Jul 28, 2025" → take end date
        if "–" in str(deadline_raw) or "-" in str(deadline_raw):
            parts = re.split(r"[–-]", str(deadline_raw))
            deadline = _parse_devpost_date(parts[-1].strip())
        else:
            deadline = _parse_devpost_date(str(deadline_raw))

    if deadline == "N/A":
        deadline = _estimate_deadline_days(21)

    org = h.get("displayed_location", {})
    if isinstance(org, dict):
        loc = org.get("location") or "Online"
    else:
        loc = str(org) if org else "Online"

    online = h.get("online_only") or h.get("online") or False
    if online:
        loc = "Online / Remote"

    organizer = h.get("organization_name") or h.get("organizer") or "Devpost"
    themes = h.get("themes", [])
    theme_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in themes[:3]]

    return {
        "title": title,
        "role": title,
        "organization": organizer,
        "type": "hackathon",
        "location": loc,
        "stipend": str(prize),
        "deadline": deadline,
        "apply_link": url if url.startswith("http") else f"{BASE_URL}{url}",
        "description": f"Hackathon: {title}. Prize: {prize}. Themes: {', '.join(theme_names) or 'Open'}. Register on Devpost.",
        "source": "devpost",
        "domain": "general",
        "verified": True,
    }


def _try_html_scrape(filters: dict) -> list[dict]:
    """Scrape Devpost HTML page."""
    location = filters.get("location", "all")
    params = {
        "challenge_type[]": "all",
        "open_to[]": "public",
        "status[]": "upcoming",
    }
    if location == "remote":
        params["online_only"] = "true"

    results = []
    try:
        resp = requests.get(
            f"{BASE_URL}/hackathons",
            headers=HTML_HEADERS,
            params=params,
            timeout=20
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[devpost] HTML fetch error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # Try many card selectors
    card_selectors = [
        "article.hackathon-tile",
        ".challenge-listing",
        ".hackathon-tile",
        "[data-challenge-id]",
        ".hackathon-card",
        ".tile",
        "li.hackathon",
    ]
    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if cards:
            print(f"[devpost] Found {len(cards)} HTML cards with: {sel}")
            break

    if not cards:
        # Try to find any JSON embedded
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "hackathon" in script.string.lower() and "title" in script.string.lower():
                try:
                    # Look for JSON array
                    m = re.search(r'\[\s*\{.*?"title".*?\}\s*\]', script.string, re.DOTALL)
                    if m:
                        data = json.loads(m.group(0))
                        for item in data[:20]:
                            entry = _map_devpost_api_item(item)
                            if entry:
                                results.append(entry)
                except Exception:
                    pass

    for card in cards:
        try:
            title_el = (card.select_one("h2") or card.select_one("h3") or
                        card.select_one(".hackathon-title") or card.select_one(".title"))
            prize_el = (card.select_one(".prize-amount") or card.select_one(".amount") or
                        card.select_one(".prize") or card.select_one("[class*='prize']"))
            deadline_el = (card.select_one("time") or card.select_one(".deadline") or
                           card.select_one("[class*='deadline']") or card.select_one(".submission-period"))
            link_el = card.find("a", href=True)
            loc_el = (card.select_one(".location") or card.select_one("[class*='location']") or
                      card.select_one(".online-tag"))

            title = title_el.get_text(strip=True) if title_el else ""
            prize = prize_el.get_text(strip=True) if prize_el else "N/A"
            loc = loc_el.get_text(strip=True) if loc_el else "Online"
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"):
                href = BASE_URL + href

            # Parse deadline
            deadline = "N/A"
            if deadline_el:
                deadline_text = deadline_el.get("datetime", "") or deadline_el.get_text(strip=True)
                if deadline_text:
                    deadline = _parse_devpost_date(deadline_text[:10] if len(deadline_text) > 10 else deadline_text)
            if deadline == "N/A":
                deadline = _estimate_deadline_days(21)

            if not title:
                continue

            results.append({
                "title": title,
                "role": title,
                "organization": "Devpost",
                "type": "hackathon",
                "location": loc or "Online",
                "stipend": prize,
                "deadline": deadline,
                "apply_link": href or BASE_URL,
                "description": f"Hackathon: {title}. Prize: {prize}. Register on Devpost.",
                "source": "devpost",
                "domain": "general",
                "verified": True,
            })
        except Exception as e:
            print(f"[devpost] HTML card parse error: {e}")
            continue

    return results


import json

def scrape(filters: dict = None) -> list[dict]:
    filters = filters or {}
    opp_type = filters.get("type", "all")

    if opp_type == "internship":
        return []  # Devpost is hackathons only

    print("[devpost] Starting scrape...")

    # Try JSON API first (most reliable)
    results = _try_devpost_api(filters)

    if not results:
        # Fall back to HTML scraping
        print("[devpost] API returned nothing, trying HTML scrape...")
        results = _try_html_scrape(filters)

    time.sleep(random.uniform(0.8, 1.5))
    print(f"[devpost] Total raw results: {len(results)}")
    cleaned = clean_all(results)
    print(f"[devpost] After cleaning: {len(cleaned)} results")
    return cleaned
