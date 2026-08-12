import json
import re
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from backend.config import settings

logger = logging.getLogger("ai_engine")

# Categories required by the prompt
CATEGORIES = [
    "Internship", "Job", "Hackathon", "Scholarship", "Competition",
    "Workshop", "Conference", "Webinar", "Certification", "Course",
    "Networking Event", "Career Fair", "Open Source Program", "Campus Hiring",
    "Placement", "Research Opportunity", "Bootcamp", "Volunteer Opportunity",
    "Startup Program", "Fellowship", "Incubator", "Accelerator", "Event",
    "General", "Spam", "Promotion", "Shipping", "Shopping", "Finance",
    "Social", "Updates", "Personal", "Unknown"
]

SYSTEM_PROMPT = f"""
You are a Senior AI Agent for 'Opportunity Hub'. Your task is to analyze the following email subject and body, classify it, and extract structured metadata.

CLASSIFICATION:
Classify the email into exactly ONE of the following categories:
{", ".join(CATEGORIES)}

INFORMATION EXTRACTION:
Extract the following attributes from the email:
1. Title (Name of the internship/job/hackathon etc.)
2. Organization (Company, College, or organizer)
3. Category (Exactly one of the classifications above)
4. Eligibility (Who can apply, branch, GPA, year, degrees, etc.)
5. Location (City, country, or WFH details)
6. Remote (Boolean: true if remote/WFH/virtual, false if offline/in-person)
7. Application Deadline (Date, converted to YYYY-MM-DD. If natural language like "Tomorrow" or "Next Friday", convert it based on the current date: {{current_date}})
8. Event Date (Date, converted to YYYY-MM-DD if applicable)
9. Start Date (Date, converted to YYYY-MM-DD if applicable)
10. End Date (Date, converted to YYYY-MM-DD if applicable)
11. Duration (e.g. "3 Months", "6 Weeks")
12. Stipend (Stipend info, e.g. "50,000/mo", "Unpaid", or "N/A")
13. Salary (CTC or base salary, e.g. "12 LPA", "N/A")
14. Prize (Prizes for hackathons/competitions, e.g. "$15,000 pool", "MacBook", "N/A")
15. Registration Fee (e.g. "Free", "$10", "N/A")
16. Skills Required (List of strings, e.g. ["Python", "Machine Learning"])
17. Technology (List of tools/technologies mentioned, e.g. ["Docker", "Supabase"])
18. Experience Level (e.g. "Entry-level", "0-2 years", "Senior")
19. Application Link (Direct application link. Try to find links to Google Forms, Devpost, Unstop, Internshala, LinkedIn, etc. Ignore tracking, social share, or unsubscribe links)
20. Official Website (Domain/website of the organization)
21. Email (Contact email mentioned)
22. Phone (Contact phone number)
23. Attachment Links (List of links that look like PDF attachments or flyers)
24. Description (A short 2-3 sentence summary of the opportunity)
25. Benefits (e.g. "Free food", "Flexible hours")
26. Certificate Available (Boolean: true if certificate/letter of recommendation is explicitly mentioned, false otherwise)

BONUS FEATURES:
- Estimate Difficulty: "Easy", "Medium", "Hard" (based on required skills and experience).
- Calculate Application Urgency: "Low", "Medium", "High" (based on deadline proximity).
- Detect Fake/Phishing: Boolean indicating if this is a suspicious/phishing/scam email.
- Rank relevance (1 to 10): Based on matching the candidate's profile (Branch: {{user_branch}}, Year: {{user_year}}, University: {{user_university}}).

OUTPUT FORMAT:
Return ONLY a valid JSON object. No pre-amble, no backticks (e.g. no ```json). Format:
{{
  "classification": "Internship",
  "confidence": 0.95,
  "title": "Software Engineer Intern",
  "organization": "Google",
  "deadline": "YYYY-MM-DD",
  "event_date": "YYYY-MM-DD",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "duration": "3 Months",
  "location": "Bangalore",
  "remote": false,
  "eligibility": "B.Tech/Dual Degree 3rd or 4th year CS students",
  "stipend": "1,00,000/month",
  "salary": "N/A",
  "prize": "N/A",
  "registration_fee": "Free",
  "skills_required": ["Python", "Data Structures", "Algorithms"],
  "technology": ["Git", "GCP"],
  "experience_level": "Entry-level",
  "application_link": "https://careers.google.com/jobs/...",
  "official_website": "https://google.com",
  "email": "internship-support@google.com",
  "phone": "",
  "attachment_links": [],
  "description": "Google is hiring Software Engineering interns for Bangalore office to work on core cloud platform.",
  "benefits": "Free meals, health insurance",
  "certificate_available": true,
  "difficulty": "Hard",
  "urgency": "Medium",
  "is_phishing_or_fake": false,
  "tags": ["SDE", "Google", "Bangalore"],
  "relevance_rank": 9
}}
"""

def parse_natural_deadline(deadline_str: str, base_date: datetime) -> str:
    """Fallback natural language deadline parser using local Python logic."""
    if not deadline_str:
        return "N/A"
    
    dl_lower = deadline_str.lower().strip()
    
    # Check for direct formats first
    iso_match = re.search(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b", dl_lower)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"
        
    if "today" in dl_lower:
        return base_date.strftime("%Y-%m-%d")
    elif "tomorrow" in dl_lower:
        return (base_date + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "day after tomorrow" in dl_lower:
        return (base_date + timedelta(days=2)).strftime("%Y-%m-%d")
    elif "within 3 days" in dl_lower or "in 3 days" in dl_lower:
        return (base_date + timedelta(days=3)).strftime("%Y-%m-%d")
    elif "next friday" in dl_lower:
        # Calculate days until next Friday
        days_ahead = 4 - base_date.weekday() # Friday is 4
        if days_ahead <= 0: # Already Friday or past
            days_ahead += 7
        return (base_date + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    elif "within 1 week" in dl_lower or "next week" in dl_lower:
        return (base_date + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Try parsing month names e.g. "Apply Before 30 July"
    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12
    }
    
    for mname, mnum in months.items():
        if mname in dl_lower:
            # Look for a number near the month
            day_match = re.search(r"\b(\d{1,2})\b", dl_lower)
            if day_match:
                day = int(day_match.group(1))
                year = base_date.year
                # If target month is earlier in current year, assume next year
                if mnum < base_date.month:
                    year += 1
                try:
                    return datetime(year, mnum, day).strftime("%Y-%m-%d")
                except ValueError:
                    pass
    return "N/A"

def extract_links(text: str) -> list[str]:
    """Helper to extract direct useful links from email text body."""
    links = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', text)
    filtered = []
    
    # Skip tracking/social/unsubscribe links
    skip_keywords = [
        "unsubscribe", "optout", "facebook.com", "twitter.com", "linkedin.com/sharing",
        "doubleclick", "adservice", "google-analytics", "clickmeter", "sendgrid",
        "mailchimp", "newsletter", "share", "instagram.com"
    ]
    
    for link in links:
        link_clean = link.rstrip('.,;()[]"\'')
        if not any(skip in link_clean.lower() for skip in skip_keywords):
            filtered.append(link_clean)
            
    return list(set(filtered))

# ── AI Engine Main Entrypoint ───────────────────────────────────

_working_gemini_config = None  # Tuple of (sdk_type, model_name)
_gemini_disabled_until = 0

def classify_and_extract(subject: str, body: str, user_profile: dict = None, sender: str = "") -> dict:
    """
    Main pipeline entrypoint.
    Runs OpenAI/Gemini to extract details. Fallbacks to regex parser if no API key is available.
    """
    global _working_gemini_config, _gemini_disabled_until

    current_date = datetime.utcnow().strftime("%Y-%m-%d")
    user_branch = user_profile.get("branch", "General") if user_profile else "Computer Science"
    user_year = user_profile.get("year", "3rd Year") if user_profile else "3rd Year"
    user_univ = user_profile.get("university", "IIT Delhi") if user_profile else "IIT Delhi"

    # Inject variables into system prompt
    prompt = SYSTEM_PROMPT.replace("{current_date}", current_date)\
                           .replace("{user_branch}", user_branch)\
                           .replace("{user_year}", user_year)\
                           .replace("{user_university}", user_univ)
    
    prompt += f"\n\nSENDER: {sender}\nSUBJECT: {subject}\nEMAIL BODY:\n{body}\n"

    # 1. Try Gemini API
    now = time.time()
    api_key = (settings.GEMINI_API_KEY or "").strip()
    is_placeholder_key = not api_key or api_key.lower().startswith("your-")

    if settings.AI_PROVIDER == "gemini" and api_key and now >= _gemini_disabled_until and not is_placeholder_key:
        # Fast-path: try previously successful working model config
        if _working_gemini_config:
            sdk_type, m_name = _working_gemini_config
            try:
                if sdk_type == "genai":
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    res = client.models.generate_content(model=m_name, contents=prompt)
                    return _clean_and_parse_json(res.text)
                elif sdk_type == "generativeai":
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(m_name)
                    response = model.generate_content(prompt)
                    return _clean_and_parse_json(response.text)
            except Exception as cached_err:
                logger.debug(f"Cached Gemini config {_working_gemini_config} failed: {cached_err}. Resetting cache.")
                _working_gemini_config = None

        # Check modern google-genai SDK first
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            for m_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]:
                try:
                    logger.debug(f"Executing classification via Google GenAI SDK ({m_name})...")
                    res = client.models.generate_content(model=m_name, contents=prompt)
                    parsed = _clean_and_parse_json(res.text)
                    _working_gemini_config = ("genai", m_name)
                    return parsed
                except Exception as m_err:
                    logger.debug(f"Google GenAI SDK model {m_name} failed: {m_err}")
        except Exception:
            pass

        # Fallback to legacy google.generativeai package
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            for m_name in ["gemini-1.5-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash"]:
                try:
                    logger.debug(f"Executing classification via Gemini API ({m_name})...")
                    model = genai.GenerativeModel(m_name)
                    response = model.generate_content(prompt)
                    parsed = _clean_and_parse_json(response.text)
                    _working_gemini_config = ("generativeai", m_name)
                    return parsed
                except Exception as m_err:
                    logger.debug(f"Gemini model {m_name} failed: {m_err}")
            raise Exception("All Gemini model variants failed or API key invalid.")
        except Exception as e:
            if not getattr(classify_and_extract, "_gemini_err_logged", False):
                logger.info(f"Gemini API key inactive/invalid. Using smart rule-based extraction engine.")
                classify_and_extract._gemini_err_logged = True
            _gemini_disabled_until = now + 300  # Disable Gemini attempts for 5 mins to avoid slowdowns

    # 2. Try OpenAI API
    if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.lower().startswith("your-"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.debug("Executing classification via OpenAI API...")
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional JSON backend extractor."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            logger.debug(f"OpenAI API execution failed: {e}. Falling back to Rule-Based parsing.")

    # 3. Fallback: Pure Rule-Based Engine
    if not getattr(classify_and_extract, "_rule_fallback_logged", False):
        logger.info("⚡ Running fast rule-based opportunity extraction for emails.")
        classify_and_extract._rule_fallback_logged = True

    return _rule_based_fallback(subject, body, current_date, sender=sender)

def _clean_and_parse_json(response_text: str) -> dict:
    """Clean markdown-wrapped JSON strings if any and return python dict."""
    cleaned = response_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    return json.loads(cleaned)

def _rule_based_fallback(subject: str, body: str, current_date: str, sender: str = "") -> dict:
    """Smart Rule-Based parsing for real email opportunities when AI key is missing."""
    text = f"{subject}\n{body}"
    low_text = text.lower()
    low_subject = subject.lower()
    low_sender = sender.lower()

    # Detect Google account security alert emails
    if "security alert" in low_subject or "you allowed" in low_subject or "google account" in low_subject:
        return {
            "classification": "Personal",
            "confidence": 0.99,
            "title": subject,
            "organization": "Google",
            "is_phishing_or_fake": False,
            "description": "Security notification email."
        }

    # 1. Determine Organization
    org = "Unknown"
    if "internshala" in low_sender or "internshala" in low_subject:
        org = "Internshala"
    elif "wellfound" in low_sender or "angel.co" in low_sender or "wellfound" in low_subject:
        org = "Wellfound"
    elif "unstop" in low_sender or "dare2compete" in low_sender:
        org = "Unstop"
    elif "linkedin" in low_sender or "linkedin" in low_subject:
        org = "LinkedIn"
    elif "google" in low_sender or "google" in low_subject:
        org = "Google"
    elif "microsoft" in low_sender or "microsoft" in low_subject:
        org = "Microsoft"
    elif "amazon" in low_sender or "amazon" in low_subject:
        org = "Amazon"
    elif "geeksforgeeks" in low_sender:
        org = "GeeksforGeeks"

    if org == "Unknown":
        org_match = re.search(r"\bat\s+([A-Z][a-zA-Z0-9\s&]{1,25})\b", subject)
        if org_match:
            org = org_match.group(1).strip()
        else:
            org_match = re.search(r"([A-Z][a-zA-Z0-9\s&]{1,25})\s+(is hiring|announces|invites|update)", text)
            if org_match:
                org = org_match.group(1).strip()

    # 2. Determine Category
    category = "General"
    confidence = 0.85

    if any(k in low_text for k in ["internship", "intern", "stipend"]):
        category = "Internship"
    elif any(k in low_text for k in ["hackathon", "coding challenge", "contest", "prize pool"]):
        category = "Hackathon"
    elif any(k in low_text for k in ["job", "hiring", "sde", "full-time", "opening", "career"]):
        category = "Job"
    elif any(k in low_text for k in ["scholarship", "fellowship", "grant"]):
        category = "Scholarship"
    elif any(k in low_text for k in ["workshop", "webinar", "bootcamp", "training", "course", "certification"]):
        category = "Workshop"
    elif any(k in low_text for k in ["shortlisted", "selected", "assessment", "interview", "application status"]):
        category = "Internship"

    # 3. Clean Title
    clean_title = re.sub(r'^(update|fwd|re|notice|alert):\s*', '', subject, flags=re.IGNORECASE).strip()
    if not clean_title:
        clean_title = subject

    # 4. Extract Deadline
    deadline = "N/A"
    deadline_words = re.findall(r"(?:deadline|before|last date|expiry|close|apply by)\s*:?\s*([^\n,]{3,30})", low_text)
    if deadline_words:
        deadline = parse_natural_deadline(deadline_words[0], datetime.strptime(current_date, "%Y-%m-%d"))

    # 5. Extract links
    all_links = extract_links(text)
    app_link = all_links[0] if all_links else "https://opportunityhub.com/apply"
    
    # 6. Location & Remote
    remote = "remote" in low_text or "work from home" in low_text or "wfh" in low_text
    location = "Remote" if remote else "On-site"
    
    # 7. Salary & stipend
    stipend = "N/A"
    st_match = re.search(r"(?:stipend|salary|pay)\s*:?\s*(?:Rs\.?|INR|₹|\$)\s*([\d,\+kmK\/\s]+)", low_text)
    if st_match:
        stipend = st_match.group(1).strip().upper()

    skills = ["Problem Solving", "Communication"]
    skills_map = ["python", "javascript", "react", "node", "sql", "java", "cpp", "aws", "docker"]
    for sk in skills_map:
        if sk in low_text:
            skills.append(sk.upper())

    # Build response dictionary
    return {
        "classification": category,
        "confidence": confidence,
        "title": clean_title,
        "organization": org,
        "deadline": deadline,
        "event_date": "N/A",
        "start_date": "N/A",
        "end_date": "N/A",
        "duration": "3-6 Months" if category == "Internship" else "N/A",
        "location": location,
        "remote": remote,
        "eligibility": "Open to candidates",
        "stipend": stipend,
        "salary": "N/A",
        "prize": "N/A",
        "registration_fee": "Free",
        "skills_required": list(set(skills)),
        "technology": list(set(skills[2:])),
        "experience_level": "Entry-level",
        "application_link": app_link,
        "official_website": f"https://{org.lower().replace(' ', '')}.com" if org != "Unknown" else "https://opportunityhub.com",
        "email": "support@opportunityhub.com",
        "phone": "",
        "attachment_links": [],
        "description": f"Imported from Gmail inbox. Subject: {clean_title}",
        "benefits": "Mentorship, career opportunity",
        "certificate_available": "certificate" in low_text,
        "difficulty": "Medium",
        "urgency": "High" if deadline != "N/A" else "Low",
        "is_phishing_or_fake": False,
        "tags": [category, org],
        "relevance_rank": 8
    }
