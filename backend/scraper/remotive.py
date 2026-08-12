"""
Remotive API Client — WORKING FREE PUBLIC API
Uses Remotive's free public JSON API (no scraping needed).
https://remotive.com/api/remote-jobs
Returns real remote jobs and internships.
"""
import requests
from datetime import datetime, timedelta
from backend.cleaner import clean_all

API_URL = "https://remotive.com/api/remote-jobs"
HEADERS = {
    "User-Agent": "OpportUnityHub/2.0 (student opportunity aggregator)",
    "Accept": "application/json",
}

# Map our domain filters to Remotive categories
DOMAIN_CATEGORY_MAP = {
    "ai":     ["machine-learning", "data-science"],
    "web":    ["software-dev"],
    "data":   ["data-science", "data-engineering"],
    "design": ["design"],
    "mobile": ["mobile-app"],
    "general": [],  # fetch all when general
}

# All Remotive categories to fetch when domain = general
ALL_CATEGORIES = [
    "software-dev", "customer-support", "design", "finance",
    "data-science", "devops-sysadmin", "marketing", "product",
    "mobile-app", "writing",
]


def _estimate_deadline(pub_date_str: str) -> str:
    """Remote jobs are open ~30 days from posting. Use that as estimated deadline."""
    if not pub_date_str:
        return "N/A"
    try:
        pub = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
        deadline = pub + timedelta(days=30)
        return deadline.strftime("%Y-%m-%d")
    except Exception:
        return "N/A"


def scrape(filters: dict = None) -> list[dict]:
    filters  = filters or {}
    domain   = filters.get("domain", "general")
    opp_type = filters.get("type", "all")

    if opp_type == "hackathon":
        return []  # Remotive has jobs/internships only

    # Decide which categories to fetch
    categories = DOMAIN_CATEGORY_MAP.get(domain.lower(), [])
    if not categories:
        categories = ALL_CATEGORIES[:5]  # fetch top 5 categories when general

    results = []
    seen_ids = set()

    for category in categories:
        params = {"category": category, "limit": 20}
        try:
            resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[remotive] API error for category {category}: {e}")
            continue

        jobs = data.get("jobs", [])
        for job in jobs:
            job_id = job.get("id")
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title     = job.get("title", "")
            company   = job.get("company_name", "")
            pub_date  = job.get("publication_date", "")
            url       = job.get("url", "")
            salary    = job.get("salary", "") or ""
            job_type  = job.get("job_type", "") or ""
            location  = job.get("candidate_required_location", "Remote") or "Remote"
            tags      = job.get("tags", [])
            desc      = job.get("description", "")

            if not title or not company:
                continue

            # Determine if internship or job
            title_lower = title.lower()
            is_intern = any(kw in title_lower for kw in ["intern", "trainee", "graduate", "junior", "entry"])
            opp_category = "internship" if is_intern else "job"

            # Filter by type if requested
            if opp_type == "internship" and not is_intern:
                continue

            # Stipend display
            stipend = salary if salary else (job_type.replace("_", " ").title() if job_type else "N/A")

            # Estimated deadline = pub_date + 30 days
            deadline = _estimate_deadline(pub_date)

            results.append({
                "title":        title,
                "role":         title,
                "organization": company,
                "type":         opp_category,
                "location":     location,
                "stipend":      stipend,
                "deadline":     deadline,
                "apply_link":   url,
                "description":  f"Remote {opp_category} at {company}. Location: {location}. Tags: {', '.join(tags[:5])}.",
                "source":       "remotive",
                "domain":       domain,
                "verified":     True,
            })

    print(f"[remotive] Fetched {len(results)} real jobs from API")
    return clean_all(results)
