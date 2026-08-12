"""
OpportUnity Hub — FastAPI Backend
Includes:
- Gmail API Synchronization Engine
- Supabase DB Integrations
- Background Scheduler running every 5 minutes
- AI Extraction and Classification Pipeline
- Google OAuth 2.0 Token Exchange & Encryption
- Mounted Static UI Frontend Files
"""
import os
import asyncio
from fastapi import FastAPI, BackgroundTasks, Query, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from backend import cache as cache_store
from backend.scraper import internshala, devpost, unstop, remotive
from backend.db import db

# Updated refactored imports
from backend.auth.routes import router as auth_router, get_current_user
from backend.email.auth_google import router as google_router
from backend.email.gmail_service import sync_user_gmail
from backend.email.scheduler import start_scheduler

app = FastAPI(title="OpportUnity Hub API", version="2.1.0")

@app.on_event("startup")
async def cleanup_unwanted_files():
    import os
    # Base directory of the workspace (one level up from backend/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    unwanted = [
        "applied.html",
        "auth.css",
        "dashboard.css",
        "dashboard.html",
        "dashboard.js",
        "data.js",
        "deadline-tracker.html",
        "email-sync.html",
        "global.css",
        "index.html",
        "landing.css",
        "landing.js",
        "login.html",
        "opportunities.html",
        "profile.html",
        "saved.html",
        "signup.html",
        "backend/auth_routes.py",
        "backend/crypto.py",
        "backend/gmail_service.py",
        "backend/auth_google.py",
        "backend/ai_engine.py",
        "backend/scheduler.py"
    ]
    
    deleted_count = 0
    for filename in unwanted:
        filepath = os.path.join(base_dir, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"[cleanup] Deleted deprecated file: {filepath}")
                deleted_count += 1
            except Exception as e:
                print(f"[cleanup] Failed to delete {filepath}: {e}")
    print(f"[cleanup] Cleanup finished. Deleted {deleted_count} files.")


# ── CORS — allow frontend origins ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Authentication and OAuth Routers
app.include_router(auth_router)
app.include_router(google_router)

# Start background sync loops
start_scheduler(app)

# In-memory store fallback of last scraped results
_last_results: list[dict] = []

import concurrent.futures

def _run_all_scrapers(filters: dict) -> list[dict]:
    results = []
    scrapers = [internshala, devpost, unstop, remotive]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        futures = {executor.submit(s.scrape, filters): s.__name__.split('.')[-1] for s in scrapers}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                results.extend(data)
                print(f"[main] Scraper {name}: {len(data)} results")
            except Exception as e:
                print(f"[main] Scraper {name} failed: {e}")
                
    return results

# ── Health Endpoint ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "OpportUnity Hub API",
        "version": "2.1.0",
        "supabase_connected": db.url != "" and db.key != ""
    }

# ── Gmail Sync & Status Endpoints ───────────────────────────────────────────

@app.post("/api/gmail/sync")
def trigger_gmail_sync(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Trigger email synchronization for the user and return imported count."""
    user_id = current_user["id"]
    gmail_acc = db.get_gmail_account_by_user(user_id)
    if not gmail_acc:
        accs = db.get_gmail_accounts()
        if accs:
            gmail_acc = accs[0]
            user_id = gmail_acc.get("user_id", user_id)
    if not gmail_acc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Gmail account linked. Please connect your Gmail first."
        )
    
    count, opps = sync_user_gmail(user_id)
    return {
        "message": f"Gmail scan complete. Processed {count} new opportunities.",
        "processed": count,
        "opportunities": opps
    }

@app.get("/api/gmail/status")
def get_gmail_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Check if the user has linked a Google Gmail account."""
    gmail_acc = db.get_gmail_account_by_user(current_user["id"])
    if gmail_acc:
        return {
            "connected": True,
            "email": gmail_acc["email"],
            "connected_at": gmail_acc["created_at"]
        }
    return {"connected": False}

@app.delete("/api/gmail/disconnect")
def disconnect_gmail(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Remove Gmail association and delete OAuth credentials."""
    user_id = current_user["id"]
    db.delete_gmail_account(user_id)
    db.log_email_sync(user_id, "SUCCESS", "Disconnected Google Gmail account association.")
    return {"message": "Gmail account disconnected successfully."}

# ── Opportunities Database Endpoints ──────────────────────────────────────────

@app.get("/api/opportunities")
def get_db_opportunities(
    category: Optional[str] = Query(None),
    organization: Optional[str] = Query(None),
    remote: Optional[bool] = Query(None),
    paid: Optional[bool] = Query(None),
    free: Optional[bool] = Query(None),
    upcoming: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    saved: Optional[bool] = Query(None),
    applied: Optional[bool] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieve structured opportunities from the database with advanced filters."""
    filters = {}
    if category:
        filters["category"] = category
    if organization:
        filters["organization"] = organization
    if remote is not None:
        filters["remote"] = remote
    if paid is not None:
        filters["paid"] = paid
    if free is not None:
        filters["free"] = free
    if upcoming is not None:
        filters["deadline_upcoming"] = upcoming
    if saved is not None:
        filters["saved"] = saved
    if applied is not None:
        filters["applied"] = applied

    opportunities_list = db.get_opportunities(current_user["id"], filters, search)
    
    # If user has connected a real Gmail account, exclude lingering demo mock items
    gmail_acc = db.get_gmail_account_by_user(current_user["id"])
    if gmail_acc and gmail_acc.get("encrypted_refresh_token") != "DEMO_REFRESH_TOKEN":
        demo_titles = {
            "Google STEP Internship 2026",
            "Microsoft Imagine Cup 2026",
            "Amazon ML Summer School 2026",
            "Uber HackTag 2026",
            "Tesla AI & Robotics Fellowship 2026"
        }
        opportunities_list = [o for o in opportunities_list if o.get("title") not in demo_titles]

    return {
        "count": len(opportunities_list),
        "opportunities": opportunities_list
    }

@app.put("/api/opportunities/{opp_id}/status")
def update_opp_status(
    opp_id: str,
    saved: Optional[bool] = None,
    applied: Optional[bool] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Toggle bookmark (saved) or applied statuses for an opportunity."""
    res = db.update_opportunity_status(
        opp_id=opp_id,
        user_id=current_user["id"],
        saved=saved,
        applied=applied
    )
    if not res:
        raise HTTPException(status_code=404, detail="Opportunity not found or unauthorized")
    return {"message": "Opportunity status updated successfully", "opportunity": res}

@app.delete("/api/opportunities/{opp_id}")
def delete_opportunity(
    opp_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Delete or dismiss an opportunity from the user's list."""
    res = db._delete("opportunities", {"id": opp_id, "user_id": current_user["id"]})
    return {"message": "Opportunity deleted successfully", "deleted": res}

class BulkActionRequest(BaseModel):
    opportunity_ids: List[str]
    action: str

@app.post("/api/opportunities/bulk-action")
def bulk_opportunity_action(
    req: BulkActionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Perform bulk updates (save, apply, delete) on multiple opportunities."""
    user_id = current_user["id"]
    processed = 0
    for opp_id in req.opportunity_ids:
        if req.action == "save":
            db.update_opportunity_status(opp_id, user_id, saved=True)
        elif req.action == "unsave":
            db.update_opportunity_status(opp_id, user_id, saved=False)
        elif req.action == "apply":
            db.update_opportunity_status(opp_id, user_id, applied=True)
        elif req.action == "unapply":
            db.update_opportunity_status(opp_id, user_id, applied=False)
        elif req.action == "delete":
            db._delete("opportunities", {"id": opp_id, "user_id": user_id})
        processed += 1
    return {"message": f"Bulk action '{req.action}' completed for {processed} items.", "processed": processed}

@app.get("/api/opportunities/stats")
def get_dashboard_stats(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get metrics and statistics for the dashboard UI."""
    return db.get_stats(current_user["id"])

# ── Notifications Endpoints ──────────────────────────────────────────────────

@app.get("/api/notifications")
def get_user_notifications(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Fetch recent notifications for the logged in user."""
    notifs = db.get_notifications(current_user["id"])
    return {"notifications": notifs}

@app.put("/api/notifications/read")
def mark_notifications_as_read(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Mark all notifications as read."""
    db.mark_notifications_read(current_user["id"])
    return {"message": "Notifications marked as read."}

# ── Web Scrapers Compatibility Route ───────────────────────

@app.post("/api/scrape")
def trigger_scrape(body: dict = None, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Scrapes opportunities concurrently, saves them into Supabase, and returns.
    """
    global _last_results
    body = body or {}
    filters = {
        "type":     body.get("type",     "all"),
        "domain":   body.get("domain",   "general"),
        "location": body.get("location", "all"),
    }

    # Run scrapers
    print(f"[main] Starting web scraping with filters: {filters}")
    raw_results = _run_all_scrapers(filters)
    if raw_results:
        _last_results = raw_results
    elif _last_results:
        raw_results = _last_results

    saved_count = 0
    db_working = True
    # Fast check: skip DB write attempts if Supabase URL/key is empty or invalid
    if not db.url or not db.key or "invalid" in db.key.lower():
        db_working = False

    if db_working:
        for raw in raw_results:
            try:
                title = raw.get("title", raw.get("role", "Opportunity"))
                org = raw.get("organization", raw.get("company", "Unknown"))
                deadline = raw.get("deadline", "N/A")
                app_link = raw.get("apply_link", raw.get("applyLink", ""))
                
                duplicate = db.check_duplicate_opportunity(
                    current_user["id"],
                    title,
                    org,
                    deadline,
                    app_link
                )
                
                if not duplicate:
                    def vc(val, max_len=250):
                        if val and isinstance(val, str) and len(val) > max_len:
                            return val[:max_len]
                        return val or "N/A"

                    mapped_data = {
                        "title":            vc(title),
                        "organization":     vc(org),
                        "category":         vc(raw.get("type", "General").capitalize(), 95),
                        "location":         vc(raw.get("location", "Remote")),
                        "stipend":          vc(raw.get("stipend", "N/A")),
                        "deadline":         deadline,
                        "application_link": raw.get("apply_link", raw.get("applyLink", "")),
                        "description":      raw.get("description", ""),
                        "source":           vc(raw.get("source", "unknown"), 95),
                        "skills_required":  [raw.get("domain", "general")] if raw.get("domain") else []
                    }
                    db.create_opportunity(current_user["id"], None, mapped_data)
                    saved_count += 1
            except Exception as db_err:
                print(f"[main] DB error during scraping save: {db_err}. Returning fresh scraped results directly.")
                db_working = False
                break

    # Clear cached details so fresh DB values reload
    cache_store.clear()

    opps = []
    if db_working:
        try:
            db_filters = {}
            if filters["type"] != "all" and filters["type"]:
                db_filters["category"] = filters["type"].capitalize()
            opps = db.get_opportunities(current_user["id"], db_filters)
        except Exception as fetch_err:
            print(f"[main] Failed to fetch DB opportunities: {fetch_err}")

    if not opps:
        opps = raw_results
    
    return JSONResponse({
        "source": "fresh_scraped_and_database",
        "count": len(opps),
        "opportunities": opps,
        "message": f"Scraped {len(raw_results)} results successfully."
    })

# ── Mount Frontend Static UI Files ───────────────────────────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    print(f"[main] Mounted static UI directory: {frontend_dir}")
else:
    print(f"[main] Static UI directory not found at: {frontend_dir}")
