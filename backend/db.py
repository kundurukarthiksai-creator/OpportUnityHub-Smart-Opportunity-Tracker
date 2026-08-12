import httpx
import logging
import threading
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.config import settings

logger = logging.getLogger("db")

class SupabaseDB:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY
        self._local = threading.local()
        
        if not self.url or not self.key:
            logger.error("Supabase URL or Key not set. DB client will fail.")

    @property
    def client(self):
        if not hasattr(self._local, "client") or self._local.client is None:
            if not self.url or not self.key:
                return None
            try:
                from supabase import create_client
                self._local.client = create_client(self.url, self.key)
                self._local.is_sdk = True
                logger.info(f"Supabase client initialized via official SDK (thread {threading.get_ident()}).")
            except ImportError:
                self._local.client = httpx.Client(
                    headers={
                        "apikey": self.key,
                        "Authorization": f"Bearer {self.key}",
                        "Content-Type": "application/json"
                    }
                )
                self._local.is_sdk = False
                logger.info(f"Supabase SDK not installed. HTTP REST client initialized (thread {threading.get_ident()}).")
        return self._local.client

    @property
    def is_sdk(self) -> bool:
        if not hasattr(self._local, "is_sdk"):
            # Trigger client property initialization
            _ = self.client
        return getattr(self._local, "is_sdk", False)

    def _format_db_error(self, operation: str, table: str, error: Exception):
        err_msg = str(error)
        if "Invalid API key" in err_msg or "invalid api key" in err_msg.lower():
            if not getattr(self, "_invalid_key_logged", False):
                logger.info("⚡ Supabase API key invalid. Running Opportunity Hub in resilient local memory mode.")
                self._invalid_key_logged = True
            self._use_memory_only = True
        elif "getaddrinfo failed" in err_msg or "11001" in err_msg or "Name or service not known" in err_msg:
            if not getattr(self, "_conn_error_logged", False):
                logger.warning(f"DB Connection Warning: Cannot resolve host '{self.url}'. Using local memory mode.")
                self._conn_error_logged = True
            self._use_memory_only = True
        else:
            logger.debug(f"{operation} on {table} failed: {error}")

    @property
    def memory_store(self) -> Dict[str, List[Dict[str, Any]]]:
        if not hasattr(self, "_mem_store") or self._mem_store is None:
            self._mem_store = self._load_memory_db()
        return self._mem_store

    def _load_memory_db(self) -> Dict[str, List[Dict[str, Any]]]:
        import json, os
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".local_db.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    db_data = json.load(f)
                    sec_kws = ["security alert", "sign-in", "signin", "verification code", "password reset", "return request", "flipkart"]
                    if "opportunities" in db_data:
                        db_data["opportunities"] = [
                            o for o in db_data["opportunities"]
                            if not any(k in (o.get("title") or "").lower() for k in sec_kws)
                        ]
                    if "emails" in db_data:
                        db_data["emails"] = [
                            e for e in db_data["emails"]
                            if not any(k in (e.get("subject") or "").lower() for k in sec_kws)
                        ]
                    return db_data
            except Exception as e:
                logger.debug(f"Error loading local_db.json: {e}")
        return {}

    def _save_memory_db(self):
        import json, os
        try:
            file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".local_db.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(getattr(self, "_mem_store", {}), f, indent=2)
        except Exception as e:
            logger.debug(f"Error saving local_db.json: {e}")

    def _post(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a row into the database, with memory fallback on DB errors."""
        import uuid
        data_copy = dict(data)
        if "id" not in data_copy or not data_copy["id"]:
            data_copy["id"] = f"{table[:4]}-{uuid.uuid4().hex[:10]}"

        if not getattr(self, "_use_memory_only", False):
            if self.is_sdk:
                try:
                    res = self.client.table(table).insert(data).execute()
                    inserted = res.data[0] if res.data else data_copy
                    self.memory_store.setdefault(table, []).append(inserted)
                    self._save_memory_db()
                    return inserted
                except Exception as e:
                    self._format_db_error("SDK Insert into", table, e)
            else:
                try:
                    url = f"{self.url}/rest/v1/{table}"
                    headers = {**self.client.headers, "Prefer": "return=representation"}
                    res = self.client.post(url, json=data, headers=headers)
                    if res.status_code < 400:
                        inserted = res.json()[0] if res.json() else data_copy
                        self.memory_store.setdefault(table, []).append(inserted)
                        self._save_memory_db()
                        return inserted
                except Exception as e:
                    self._format_db_error("HTTP Insert into", table, e)

        # Fallback to memory store so application never crashes
        self.memory_store.setdefault(table, []).append(data_copy)
        self._save_memory_db()
        return data_copy

    def _get_one(self, table: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get a single row matching criteria, checking memory store on fallback."""
        if not getattr(self, "_use_memory_only", False):
            if self.is_sdk:
                try:
                    query = self.client.table(table).select("*")
                    for k, v in filters.items():
                        query = query.eq(k, v)
                    res = query.execute()
                    if res.data:
                        return res.data[0]
                except Exception as e:
                    self._format_db_error("SDK Fetch from", table, e)
            else:
                try:
                    url = f"{self.url}/rest/v1/{table}"
                    params = {k: f"eq.{v}" for k, v in filters.items()}
                    res = self.client.get(url, params=params)
                    if res.status_code < 400 and res.json():
                        return res.json()[0]
                except Exception as e:
                    self._format_db_error("HTTP Fetch from", table, e)

        # Search memory store
        items = self.memory_store.get(table, [])
        for item in items:
            if all(item.get(k) == v for k, v in filters.items()):
                return item
        return None

    def _query(self, table: str, select: str = "*", filters: Dict[str, Any] = None, order_by: str = None, order_desc: bool = True, limit: int = 500) -> List[Dict[str, Any]]:
        """Query multiple rows, checking memory store on fallback."""
        filters = filters or {}
        if not getattr(self, "_use_memory_only", False):
            if self.is_sdk:
                try:
                    q = self.client.table(table).select(select)
                    for k, v in filters.items():
                        q = q.eq(k, v)
                    if order_by:
                        q = q.order(order_by, desc=order_desc)
                    if limit:
                        q = q.limit(limit)
                    res = q.execute()
                    if res.data:
                        return res.data
                except Exception as e:
                    self._format_db_error("SDK Query on", table, e)
            else:
                try:
                    url = f"{self.url}/rest/v1/{table}"
                    params = {"select": select}
                    for k, v in filters.items():
                        params[k] = f"eq.{v}"
                    if order_by:
                        params["order"] = f"{order_by}.{'desc' if order_desc else 'asc'}"
                    if limit:
                        params["limit"] = str(limit)
                    res = self.client.get(url, params=params)
                    if res.status_code < 400 and res.json():
                        return res.json()
                except Exception as e:
                    self._format_db_error("HTTP Query on", table, e)

        # Search memory store
        items = self.memory_store.get(table, [])
        matched = []
        for item in items:
            if all(item.get(k) == v for k, v in filters.items()):
                matched.append(item)
        return matched[:limit] if limit else matched

    def _update(self, table: str, filters: Dict[str, Any], data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Update rows matching filters, fallback to memory store."""
        updated_items = []
        if not getattr(self, "_use_memory_only", False):
            if self.is_sdk:
                try:
                    q = self.client.table(table).update(data)
                    for k, v in filters.items():
                        q = q.eq(k, v)
                    res = q.execute()
                    if res.data:
                        updated_items = res.data
                except Exception as e:
                    self._format_db_error("SDK Update on", table, e)
        else:
            try:
                url = f"{self.url}/rest/v1/{table}"
                params = {k: f"eq.{v}" for k, v in filters.items()}
                headers = {**self.client.headers, "Prefer": "return=representation"}
                res = self.client.patch(url, json=data, params=params, headers=headers)
                if res.status_code < 400 and res.json():
                    updated_items = res.json()
            except Exception as e:
                self._format_db_error("HTTP Update on", table, e)

        # Also update memory store
        items = self.memory_store.get(table, [])
        for item in items:
            if all(item.get(k) == v for k, v in filters.items()):
                item.update(data)
                if item not in updated_items:
                    updated_items.append(item)
        self._save_memory_db()
        return updated_items

    def _delete(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Delete rows matching filters, fallback to memory store."""
        deleted_items = []
        if not getattr(self, "_use_memory_only", False):
            if self.is_sdk:
                try:
                    q = self.client.table(table).delete()
                    for k, v in filters.items():
                        q = q.eq(k, v)
                    res = q.execute()
                    if res.data:
                        deleted_items = res.data
                except Exception as e:
                    self._format_db_error("SDK Delete on", table, e)
            else:
                try:
                    url = f"{self.url}/rest/v1/{table}"
                    params = {k: f"eq.{v}" for k, v in filters.items()}
                    headers = {**self.client.headers, "Prefer": "return=representation"}
                    res = self.client.delete(url, params=params, headers=headers)
                    if res.status_code < 400 and res.json():
                        deleted_items = res.json()
                except Exception as e:
                    self._format_db_error("HTTP Delete on", table, e)

        # Also remove from memory store
        items = self.memory_store.get(table, [])
        remaining = [item for item in items if not all(item.get(k) == v for k, v in filters.items())]
        self.memory_store[table] = remaining
        self._save_memory_db()
        return deleted_items

    # ── User Functions ──────────────────────────────────────────
    def create_user(self, email: str, name: str, password_hash: str, university: str = None, branch: str = None, year: str = None) -> Dict[str, Any]:
        return self._post("users", {
            "email": email,
            "name": name,
            "password_hash": password_hash,
            "university": university,
            "branch": branch,
            "year": year
        })

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self._get_one("users", {"email": email})

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._get_one("users", {"id": user_id})

    # ── Gmail Auth Functions ────────────────────────────────────
    def create_or_update_gmail_account(self, user_id: str, email: str, encrypted_refresh_token: str, scopes: List[str], encrypted_access_token: str = None) -> Dict[str, Any]:
        data = {
            "id": f"gmail-{user_id}",
            "user_id": user_id,
            "email": email,
            "encrypted_refresh_token": encrypted_refresh_token,
            "scopes": scopes,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        if encrypted_access_token:
            data["encrypted_access_token"] = encrypted_access_token
        
        existing = self._get_one("gmail_accounts", {"user_id": user_id})
        if existing:
            updated = self._update("gmail_accounts", {"id": existing["id"]}, data)
            return updated[0] if updated else data
        else:
            return self._post("gmail_accounts", data)

    def get_gmail_accounts(self) -> List[Dict[str, Any]]:
        return self._query("gmail_accounts")

    def get_gmail_account_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._get_one("gmail_accounts", {"user_id": user_id})

    def delete_gmail_account(self, user_id: str) -> List[Dict[str, Any]]:
        return self._delete("gmail_accounts", {"user_id": user_id})

    # ── Email Processing Cache ──────────────────────────────────
    def create_email(self, user_id: str, message_id: str, thread_id: str, sender: str, subject: str, body: str, html: str, date_received: datetime, category: str, confidence: float) -> Dict[str, Any]:
        return self._post("emails", {
            "user_id": user_id,
            "message_id": message_id,
            "thread_id": thread_id,
            "sender": sender[:255] if sender and len(sender) > 255 else sender,
            "subject": subject[:255] if subject and len(subject) > 255 else subject,
            "body": body,
            "html": html,
            "date_received": date_received.isoformat(),
            "category": category[:100] if category and len(category) > 100 else category,
            "confidence": confidence,
            "processed": True
        })

    def get_email_by_message_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        return self._get_one("emails", {"message_id": message_id})

    # ── Opportunity Functions ───────────────────────────────────
    def create_opportunity(self, user_id: str, email_id: Optional[str], data: Dict[str, Any]) -> Dict[str, Any]:
        # Maps the AI output keys into Database columns
        db_data = {
            "user_id": user_id,
            "email_id": email_id,
            "title": data.get("title", "Opportunity"),
            "organization": data.get("organization", "Unknown"),
            "category": data.get("category", "General"),
            "eligibility": data.get("eligibility"),
            "location": data.get("location", "Remote"),
            "remote": data.get("remote", True) if isinstance(data.get("remote"), bool) else ("remote" in str(data.get("location", "")).lower()),
            "stipend": data.get("stipend", "N/A"),
            "salary": data.get("salary", "N/A"),
            "prize": data.get("prize", "N/A"),
            "registration_fee": data.get("registration_fee", "Free"),
            "skills_required": data.get("skills_required", []),
            "technology": data.get("technology", []),
            "experience_level": data.get("experience_level", "All Levels"),
            "application_link": data.get("application_link"),
            "official_website": data.get("official_website"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "attachment_links": data.get("attachment_links", []),
            "description": data.get("description", ""),
            "benefits": data.get("benefits"),
            "certificate_available": data.get("certificate_available", False),
            "source_email": data.get("source_email"),
            "source_sender": data.get("source_sender") or data.get("source"),
            "received_time": data.get("received_time"),
            "confidence": data.get("confidence", 1.0),
            "similarity_score": data.get("similarity_score", 0.0),
            "duration": data.get("duration"),
        }

        # ── Truncate all VARCHAR(255) fields to prevent DB overflow errors ──
        # Schema: title(255), organization(255), location(255), stipend(255),
        #         salary(255), prize(255), registration_fee(255), source_email(255),
        #         source_sender(255), experience_level(100), category(100), duration(100)
        VARCHAR_LIMITS = {
            "title": 250,
            "organization": 250,
            "location": 250,
            "stipend": 250,
            "salary": 250,
            "prize": 250,
            "registration_fee": 250,
            "source_email": 250,
            "source_sender": 250,
            "experience_level": 95,
            "category": 95,
            "duration": 95,
            "email": 250,
            "phone": 45,
        }
        for field, max_len in VARCHAR_LIMITS.items():
            val = db_data.get(field)
            if val and isinstance(val, str) and len(val) > max_len:
                db_data[field] = val[:max_len]

        # Parse deadlines and dates safely
        for dkey in ["deadline", "event_date", "start_date", "end_date"]:
            val = data.get(dkey)
            if val and val != "N/A" and val != "":
                try:
                    # check if format is already YYYY-MM-DD
                    datetime.strptime(val[:10], "%Y-%m-%d")
                    db_data[dkey] = val[:10]
                except ValueError:
                    # Don't set if it doesn't match standard date format
                    pass
        
        return self._post("opportunities", db_data)

    def check_duplicate_opportunity(self, user_id: str, title: str, organization: str, deadline: Optional[str], application_link: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Check database or memory store for duplicates using Title, Organization, Deadline or Application Link safely.
        """
        if not title and not application_link:
            return None

        clean_org = (organization or "").strip().lower()
        clean_title = (title or "").strip().lower()
        
        # 1. Match by exact application link if present (ignoring generic links)
        if application_link and "opportunityhub.com" not in application_link and len(application_link) > 12:
            res = self._query("opportunities", filters={"user_id": user_id, "application_link": application_link}, limit=1)
            if res:
                return res[0]

        # 2. Match by organization + title (only if org is known and specific)
        if clean_title and clean_org and clean_org != "unknown":
            opps = self._query("opportunities", filters={"user_id": user_id}, limit=100)
            for opp in opps:
                db_org = (opp.get("organization") or "").strip().lower()
                db_title = (opp.get("title") or "").strip().lower()
                
                if db_org and db_org != "unknown" and db_org == clean_org and db_title == clean_title:
                    db_dl = str(opp.get("deadline") or "")[:10]
                    target_dl = str(deadline or "")[:10]
                    if target_dl and db_dl and target_dl != "N/A" and db_dl != "N/A":
                        if db_dl == target_dl:
                            return opp
                    elif not target_dl and not db_dl:
                        return opp
        return None

    def get_opportunities(self, user_id: str, filters: Dict[str, Any] = None, search: str = None) -> List[Dict[str, Any]]:
        """Retrieve opportunities with rich filtering and search options, falling back to memory_store on DB error."""
        filters = filters or {}
        results = []

        if self.is_sdk:
            try:
                q = self.client.table("opportunities").select("*").eq("user_id", user_id)
                for k, v in filters.items():
                    if k == "remote" and isinstance(v, bool):
                        q = q.eq("remote", v)
                    elif k == "paid":
                        if v:
                            q = q.neq("stipend", "N/A").neq("stipend", "Free").neq("stipend", "-")
                        else:
                            q = q.or_("stipend.eq.N/A,stipend.eq.Free,stipend.eq.-")
                    elif k == "free":
                        if v:
                            q = q.eq("registration_fee", "Free")
                        else:
                            q = q.neq("registration_fee", "Free")
                    elif k == "deadline_upcoming" and v:
                        q = q.gte("deadline", datetime.utcnow().date().isoformat())
                    elif k not in ["saved", "applied"]:
                        q = q.eq(k, v)

                if search:
                    s_term = f"%{search}%"
                    q = q.or_(f"title.ilike.{s_term},description.ilike.{s_term},organization.ilike.{s_term}")

                res = q.order("created_at", desc=True).limit(500).execute()
                if res.data:
                    results = res.data
            except Exception as e:
                self._format_db_error("SDK get_opportunities", "opportunities", e)
        else:
            try:
                params = {"user_id": f"eq.{user_id}", "order": "created_at.desc"}
                url = f"{self.url}/rest/v1/opportunities"
                res = self.client.get(url, params=params)
                if res.status_code < 400 and res.json():
                    results = res.json()
            except Exception as e:
                self._format_db_error("HTTP get_opportunities", "opportunities", e)

        if not results:
            mem_items = self.memory_store.get("opportunities", [])
            user_items = [o for o in mem_items if o.get("user_id") == user_id]
            filtered = []
            for item in user_items:
                match = True
                for k, v in filters.items():
                    if k == "remote" and item.get("remote") != v:
                        match = False
                    elif k == "category" and item.get("category") != v:
                        match = False
                    elif k == "organization" and item.get("organization") != v:
                        match = False
                if search and match:
                    s_low = search.lower()
                    title_match = s_low in (item.get("title") or "").lower()
                    org_match = s_low in (item.get("organization") or "").lower()
                    match = title_match or org_match
                if match:
                    filtered.append(item)
            results = filtered

        return results

    def get_opportunity_by_id(self, opp_id: str) -> Optional[Dict[str, Any]]:
        return self._get_one("opportunities", {"id": opp_id})

    def update_opportunity_status(self, opp_id: str, user_id: str, saved: Optional[bool] = None, applied: Optional[bool] = None) -> Dict[str, Any]:
        data = {}
        if saved is not None:
            data["saved"] = saved
        if applied is not None:
            data["applied"] = applied
        data["updated_at"] = datetime.utcnow().isoformat()
        
        updated = self._update("opportunities", {"id": opp_id, "user_id": user_id}, data)
        return updated[0] if updated else {}

    # ── Notification Functions ──────────────────────────────────
    def create_notification(self, user_id: str, opportunity_id: Optional[str], notif_type: str, message: str) -> Dict[str, Any]:
        return self._post("notifications", {
            "user_id": user_id,
            "opportunity_id": opportunity_id,
            "type": notif_type,
            "message": message,
            "read": False
        })

    def get_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        return self._query("notifications", filters={"user_id": user_id}, order_by="created_at", order_desc=True, limit=50)

    def mark_notifications_read(self, user_id: str) -> List[Dict[str, Any]]:
        return self._update("notifications", {"user_id": user_id, "read": False}, {"read": True})

    # ── Log Functions ───────────────────────────────────────────
    def log_email_sync(self, user_id: str, status: str, message: str, error_details: str = None) -> Dict[str, Any]:
        try:
            return self._post("email_logs", {
                "user_id": user_id,
                "status": status,
                "message": message,
                "error_details": error_details
            })
        except Exception as e:
            logger.warning(f"Could not write email log to DB: {e}")
            return {}

    def log_automation_run(self, job_name: str, status: str, records_processed: int = 0, error_message: str = None) -> Dict[str, Any]:
        try:
            return self._post("automation_logs", {
                "job_name": job_name,
                "status": status,
                "records_processed": records_processed,
                "error_message": error_message
            })
        except Exception as e:
            logger.warning(f"Could not write automation log to DB: {e}")
            return {}

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Fetch statistics for the user dashboard."""
        opps = self._query("opportunities", select="id,category,saved,applied", filters={"user_id": user_id}, limit=1000)
        
        total = len(opps)
        internships = sum(1 for o in opps if o["category"].lower() == "internship")
        hackathons = sum(1 for o in opps if o["category"].lower() == "hackathon")
        jobs = sum(1 for o in opps if o["category"].lower() == "job")
        scholarships = sum(1 for o in opps if o["category"].lower() == "scholarship")
        competitions = sum(1 for o in opps if o["category"].lower() == "competition")
        saved = sum(1 for o in opps if o["saved"])
        applied = sum(1 for o in opps if o["applied"])

        return {
            "total": total,
            "internships": internships,
            "hackathons": hackathons,
            "jobs": jobs,
            "scholarships": scholarships,
            "competitions": competitions,
            "saved": saved,
            "applied": applied
        }

db = SupabaseDB()
