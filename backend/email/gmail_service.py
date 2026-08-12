import base64
import email
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from backend.db import db
from backend.email.crypto import decrypt_token, encrypt_token
from backend.config import settings
from backend.email.ai_engine import classify_and_extract

logger = logging.getLogger("gmail_service")

REQUIRED_LABELS = ["Internship", "Hackathon", "Job", "Scholarship", "Workshop", "Important", "Saved", "Rejected", "Spam"]

def get_gmail_credentials(user_id: str) -> Optional[Credentials]:
    """Retrieve and decrypt stored credentials for the user."""
    account = db.get_gmail_account_by_user(user_id)
    if not account:
        logger.info(f"No Gmail account linked for user {user_id}")
        return None

    try:
        raw_rt = account.get("encrypted_refresh_token")
        raw_at = account.get("encrypted_access_token")
        
        decrypted_rt = decrypt_token(raw_rt) if (raw_rt and raw_rt != "DEMO_REFRESH_TOKEN") else None
        decrypted_at = decrypt_token(raw_at) if raw_at else None

        # If decrypted_rt is actually an access token (starts with ya29.), treat as access token
        if decrypted_rt and decrypted_rt.startswith("ya29."):
            if not decrypted_at:
                decrypted_at = decrypted_rt
            decrypted_rt = None

        if decrypted_rt:
            try:
                creds = Credentials(
                    token=decrypted_at,
                    refresh_token=decrypted_rt,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET,
                    scopes=account.get("scopes", [])
                )
                creds.refresh(Request())
                if creds.refresh_token and creds.refresh_token != decrypted_rt:
                    db.create_or_update_gmail_account(
                        user_id=user_id,
                        email=account["email"],
                        encrypted_refresh_token=encrypt_token(creds.refresh_token),
                        encrypted_access_token=encrypt_token(creds.token) if creds.token else raw_at,
                        scopes=account.get("scopes", [])
                    )
                    logger.info("Updated Google refresh token in database.")
                return creds
            except Exception as ref_err:
                logger.warning(f"Could not refresh Gmail credentials using refresh token: {ref_err}. Testing stored access token.")

        if decrypted_at:
            creds = Credentials(
                token=decrypted_at,
                scopes=account.get("scopes", [])
            )
            return creds

        return None
    except Exception as e:
        logger.error(f"Error restoring Gmail credentials for user {user_id}: {e}")
        db.log_email_sync(user_id, "FAILED", "Google credentials expired or invalid. Please reconnect.", str(e))
        return None

def clean_body_text(text: str) -> str:
    """Clean email text by removing signatures, unwanted formatting, tracking and duplicates."""
    if not text:
        return ""
        
    # Remove HTML tags if present
    text = re.sub(r"<[^>]+>", " ", text)
    
    # Remove carriage returns
    text = text.replace("\r", "\n")
    
    lines = text.split("\n")
    cleaned_lines = []
    
    # Simple signature & footer detector
    signature_markers = ["warm regards", "best regards", "kind regards", "thanks & regards", "sincerely", "thanks,", "thank you,", "sent from my"]
    
    for line in lines:
        line_strip = line.strip()
        
        # Skip empty lines or unsubscribe links
        if "unsubscribe" in line_strip.lower() or "opt out" in line_strip.lower():
            continue
            
        # Detect signatures and truncate further text
        if any(marker in line_strip.lower() for marker in signature_markers):
            break
            
        # Clean double spaces
        line_clean = re.sub(r"\s+", " ", line_strip)
        if line_clean:
            cleaned_lines.append(line_clean)
            
    return "\n".join(cleaned_lines).strip()

def get_message_content(service, message_id: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Fetch text, HTML bodies and attachment details from Gmail API."""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = msg.get("payload", {})
    parts = [payload]
    
    text_body = ""
    html_body = ""
    attachments = []
    
    # Traverse MIME parts recursively
    while parts:
        part = parts.pop()
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")
        
        # Check for inline or regular attachments
        filename = part.get("filename", "")
        attachment_id = part.get("body", {}).get("attachmentId", "")
        if filename and attachment_id:
            attachments.append({
                "filename": filename,
                "content_type": mime_type,
                "file_size": part.get("body", {}).get("size", 0),
                "attachment_id": attachment_id
            })

        if mime_type == "text/plain" and body_data:
            text_body += base64.urlsafe_b64decode(body_data.encode("UTF-8")).decode("UTF-8", errors="ignore")
        elif mime_type == "text/html" and body_data:
            html_body += base64.urlsafe_b64decode(body_data.encode("UTF-8")).decode("UTF-8", errors="ignore")
            
        part_list = part.get("parts", [])
        if part_list:
            parts.extend(part_list)
            
    # fallback if HTML only
    if not text_body and html_body:
        # Simple HTML tag stripper fallback
        text_body = clean_body_text(html_body)
    else:
        text_body = clean_body_text(text_body)
        
    return text_body, html_body, attachments

def ensure_gmail_labels(service) -> Dict[str, str]:
    """Ensure all required opportunity labels exist in Gmail, return dict of label_name -> label_id."""
    try:
        results = service.users().labels().list(userId="me").execute()
        existing_labels = results.get("labels", [])
        
        label_map = {l["name"]: l["id"] for l in existing_labels}
        
        for rlabel in REQUIRED_LABELS:
            # Gmail labels are case sensitive. Create under namespace 'Hub-LabelName'
            label_name = f"Hub-{rlabel}"
            if label_name not in label_map:
                try:
                    new_label = service.users().labels().create(
                        userId="me",
                        body={
                            "name": label_name,
                            "labelListVisibility": "labelShow",
                            "messageListVisibility": "show"
                        }
                    ).execute()
                    label_map[label_name] = new_label["id"]
                    logger.info(f"Created Gmail label: {label_name}")
                except Exception as e:
                    logger.error(f"Failed to create label {label_name}: {e}")
            else:
                label_map[rlabel] = label_map[label_name]
        return label_map
    except Exception as e:
        logger.error(f"Error ensuring Gmail labels: {e}")
        return {}

def apply_gmail_label(service, message_id: str, label_id: str):
    """Add a label to a Gmail message."""
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id], "removeLabelIds": ["UNREAD"]}
        ).execute()
    except Exception as e:
        logger.error(f"Failed to apply label {label_id} to message {message_id}: {e}")

def _sync_demo_gmail(user_id: str, email_addr: str) -> int:
    """Synchronize demo email opportunities for instant demo testing."""
    demo_emails = [
        {
            "title": "Google STEP Internship 2026",
            "organization": "Google",
            "category": "Internship",
            "location": "Bangalore / Remote",
            "stipend": "₹1,20,000/mo",
            "deadline": "2026-08-25",
            "application_link": "https://careers.google.com/students",
            "description": "Application invitation for Google STEP (Student Training in Engineering Program) Internship 2026.",
            "source": "gmail",
            "source_email": email_addr,
            "source_sender": "Google University Recruiting <jobs-noreply@google.com>",
            "skills_required": ["Python", "Data Structures", "Algorithms"]
        },
        {
            "title": "Microsoft Imagine Cup 2026",
            "organization": "Microsoft",
            "category": "Hackathon",
            "location": "Online / Global",
            "stipend": "$100,000 Grand Prize",
            "deadline": "2026-08-30",
            "application_link": "https://imaginecup.microsoft.com",
            "description": "You are invited to register for Microsoft Imagine Cup 2026 global developer hackathon.",
            "source": "gmail",
            "source_email": email_addr,
            "source_sender": "Microsoft Student Developer <imaginecup@microsoft.com>",
            "skills_required": ["Azure", "AI", "Cloud"]
        },
        {
            "title": "Amazon ML Summer School 2026",
            "organization": "Amazon",
            "category": "Workshop",
            "location": "Online / India",
            "stipend": "Free Certificate & Mentorship",
            "deadline": "2026-09-05",
            "application_link": "https://amazonmlsummerschool.com",
            "description": "Registration confirmed for Amazon Machine Learning Summer School 2026.",
            "source": "gmail",
            "source_email": email_addr,
            "source_sender": "Amazon University Programs <ml-school@amazon.com>",
            "skills_required": ["Machine Learning", "Deep Learning", "Python"]
        },
        {
            "title": "Uber HackTag 2026",
            "organization": "Uber",
            "category": "Hackathon",
            "location": "Hyderabad / Hybrid",
            "stipend": "₹5,000,000 Prize Pool",
            "deadline": "2026-09-10",
            "application_link": "https://uber.com/careers/hacktag",
            "description": "Official invitation to participate in Uber HackTag Engineering Challenge 2026.",
            "source": "gmail",
            "source_email": email_addr,
            "source_sender": "Uber Tech Talent <hacktag@uber.com>",
            "skills_required": ["Distributed Systems", "Backend", "Go"]
        },
        {
            "title": "Tesla AI & Robotics Fellowship 2026",
            "organization": "Tesla",
            "category": "Scholarship",
            "location": "Palo Alto / Remote",
            "stipend": "$12,000/mo Fellowship",
            "deadline": "2026-09-15",
            "application_link": "https://tesla.com/careers/fellowship",
            "description": "Selection notification for Tesla AI & Autonomous Systems Fellowship program.",
            "source": "gmail",
            "source_email": email_addr,
            "source_sender": "Tesla AI Team <robotics-fellowship@tesla.com>",
            "skills_required": ["Computer Vision", "PyTorch", "Robotics"]
        }
    ]

    synced_count = 0
    for opp_data in demo_emails:
        try:
            duplicate = db.check_duplicate_opportunity(
                user_id,
                opp_data["title"],
                opp_data["organization"],
                opp_data["deadline"],
                opp_data["application_link"]
            )
            if not duplicate:
                db.create_opportunity(user_id, None, opp_data)
                synced_count += 1
        except Exception as e:
            logger.error(f"Error creating demo opportunity: {e}")
            synced_count += 1

    db.log_email_sync(user_id, "SUCCESS", f"Synced {len(demo_emails)} opportunity emails from Gmail (Demo Account: {email_addr})")
    return len(demo_emails), demo_emails

def sync_user_gmail(user_id: str) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Sync unread/starred emails for a specific user.
    Classifies content using AI, deduplicates, saves into Supabase and updates Gmail labels.
    """
    account = db.get_gmail_account_by_user(user_id)
    if account and account.get("encrypted_refresh_token") == "DEMO_REFRESH_TOKEN":
        return _sync_demo_gmail(user_id, account.get("email", "kundurukarthik15@gmail.com"))

    creds = get_gmail_credentials(user_id)
    if not creds:
        return 0, []

    # Clean up any leftover demo opportunities for real Gmail user
    try:
        existing = db._query("opportunities", filters={"user_id": user_id}, limit=100)
        demo_titles = {
            "Google STEP Internship 2026",
            "Microsoft Imagine Cup 2026",
            "Amazon ML Summer School 2026",
            "Uber HackTag 2026",
            "Tesla AI & Robotics Fellowship 2026"
        }
        for opp in existing:
            if opp.get("title") in demo_titles:
                db._delete("opportunities", {"id": opp["id"]})
    except Exception as clean_err:
        logger.debug(f"Could not purge demo opportunities: {clean_err}")

    synced_opps = []
    try:
        service = build("gmail", "v1", credentials=creds)
        user_info = db.get_user_by_id(user_id)
        
        # 1. Fetch Labels
        label_map = ensure_gmail_labels(service)
        
        # 2. Query inbox: Read recent inbox emails (both read & unread). Skip spam and trash.
        query = "is:inbox -is:spam -is:trash"
        results = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
        messages = results.get("messages", [])
        
        if not messages:
            logger.info(f"No inbox emails found for user {user_id}")
            db.log_email_sync(user_id, "SUCCESS", "Scan complete: No inbox emails.")
            return 0, []
            
        processed_count = 0
        logger.info(f"Found {len(messages)} messages to process for user {user_id}")

        for msg_meta in messages:
            message_id = msg_meta["id"]
            thread_id = msg_meta["threadId"]
            
            # Check if an opportunity was already created for this email message
            existing_email = db.get_email_by_message_id(message_id)
            if existing_email:
                try:
                    existing_opp = db._get_one("opportunities", {"email_id": existing_email["id"]})
                    if existing_opp:
                        synced_opps.append(existing_opp)
                        continue
                except Exception:
                    pass

            # Fetch headers
            msg_detail = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
            headers = msg_detail.get("payload", {}).get("headers", [])
            
            subject = "No Subject"
            sender = "Unknown Sender"
            date_str = ""
            for h in headers:
                if h["name"].lower() == "subject":
                    subject = h["value"]
                elif h["name"].lower() == "from":
                    sender = h["value"]
                elif h["name"].lower() == "date":
                    date_str = h["value"]

            # Parse received date
            try:
                date_received = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                date_received = datetime.utcnow()

            # Retrieve text and HTML contents
            body, html, attachments = get_message_content(service, message_id)
            
            # 3. Classify and Extract details using AI Engine
            try:
                extracted = classify_and_extract(
                    subject=subject,
                    body=body,
                    user_profile=user_info,
                    sender=sender
                )
            except Exception as ai_err:
                logger.error(f"AI parsing failed for email {message_id}: {ai_err}")
                db.log_email_sync(user_id, "WARNING", f"AI extraction failed for email: {subject}", str(ai_err))
                continue

            classification = extracted.get("classification", "General")
            confidence = extracted.get("confidence", 0.5)

            # Store raw email trace
            if not existing_email:
                try:
                    new_email = db.create_email(
                        user_id=user_id,
                        message_id=message_id,
                        thread_id=thread_id,
                        sender=sender,
                        subject=subject,
                        body=body,
                        html=html,
                        date_received=date_received,
                        category=classification,
                        confidence=confidence
                    )
                except Exception as create_email_err:
                    logger.warning(f"Could not store raw email trace: {create_email_err}")
                    new_email = {"id": f"email-{message_id}"}
            else:
                new_email = existing_email

            # Link attachments if any
            for att in attachments:
                try:
                    db._post("attachments", {
                        "email_id": new_email["id"],
                        "filename": att["filename"],
                        "content_type": att["content_type"],
                        "file_size": att["file_size"],
                        "storage_url": None
                    })
                except Exception as att_err:
                    logger.error(f"Failed to record attachment {att['filename']}: {att_err}")

            # Check for security alert & system non-opportunity emails first
            security_phrases = [
                "security alert", "security notice", "sign-in", "signin", "login alert",
                "verification code", "2-step verification", "password reset", "account recovery",
                "access granted", "unusual activity", "verify your account", "confirm your email",
                "return request", "flipkart", "order od", "daily digest", "medium daily digest"
            ]
            sub_low = subject.lower()
            send_low = sender.lower()
            is_system_security = any(sp in sub_low for sp in security_phrases) or "no-reply@accounts.google.com" in send_low or "accounts-noreply" in send_low

            if is_system_security:
                logger.info(f"Skipping system security/non-opportunity email '{subject}'.")
                continue

            # Check if email is an opportunity email
            opp_keywords = [
                "internship", "hackathon", "job", "opportunity", "hiring", "unstop", "internshala",
                "devpost", "apply", "application", "scholarship", "competition", "contest", "career",
                "opening", "recruitment", "shortlist", "assessment", "round", "interview", "campus",
                "selection", "test", "challenge", "fellowship", "referral", "placement", "drive",
                "invitation", "workshop", "event", "program", "training", "offer",
                "congratulations", "selected", "register",
                "wellfound", "linkedin", "geeksforgeeks", "hackerrank", "codechef", "nptel", "coursera"
            ]
            combined_text = f"{subject} {sender} {body[:500]}".lower()
            is_opportunity_text = any(kw in combined_text for kw in opp_keywords)

            skip_categories = ["spam", "phishing", "shopping", "shipping", "finance", "social", "personal"]
            if classification.lower() in skip_categories or extracted.get("is_phishing_or_fake", False) or not is_opportunity_text:
                logger.info(f"Skipping saving non-opportunity email '{subject}' (type: '{classification}').")
                if classification.lower() == "spam" and "Hub-Spam" in label_map:
                    apply_gmail_label(service, message_id, label_map["Hub-Spam"])
                continue

            # 4. Duplicate Check
            title = extracted.get("title", subject)
            org = extracted.get("organization", "Unknown")
            deadline = extracted.get("deadline")
            app_link = extracted.get("application_link")
            
            try:
                duplicate = db.check_duplicate_opportunity(
                    user_id=user_id,
                    title=title,
                    organization=org,
                    deadline=deadline,
                    application_link=app_link
                )
            except Exception as dup_err:
                logger.warning(f"Check duplicate warning: {dup_err}")
                duplicate = None
            
            # Add source fields
            gmail_acct = db.get_gmail_account_by_user(user_id)
            source_email = gmail_acct["email"] if (gmail_acct and "email" in gmail_acct) else (user_info.get("email", "") if user_info else "")
            extracted["source_email"] = source_email
            extracted["source_sender"] = sender
            extracted["received_time"] = date_received.isoformat()

            if duplicate:
                logger.info(f"Duplicate opportunity detected for user {user_id}: '{title}' by '{org}'. Retaining for display.")
                synced_opps.append(duplicate if isinstance(duplicate, dict) else extracted)
                service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
                continue

            # 5. Save Opportunity
            try:
                opp = db.create_opportunity(user_id, new_email["id"], extracted)
            except Exception as create_err:
                logger.warning(f"Failed to write opportunity to DB: {create_err}. Retaining extracted data.")
                opp = extracted
                opp["id"] = f"opp-{message_id}"

            synced_opps.append(opp)
            processed_count += 1
            
            # Apply corresponding Gmail Label
            label_to_apply = "Hub-Important"
            if classification in REQUIRED_LABELS:
                label_to_apply = f"Hub-{classification}"
            
            if label_to_apply in label_map:
                apply_gmail_label(service, message_id, label_map[label_to_apply])
            else:
                service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()

            # 6. Trigger Notification Alerts
            if classification in ["Internship", "Hackathon", "Job"]:
                try:
                    db.create_notification(
                        user_id=user_id,
                        opportunity_id=opp.get("id"),
                        notif_type=f"NEW_{classification.upper()}",
                        message=f"New {classification} found: '{title}' at '{org}'!"
                    )
                except Exception:
                    pass

        # If no new items were processed, fetch existing email opportunities for display
        if not synced_opps:
            try:
                all_opps = db.get_opportunities(user_id)
                synced_opps = [o for o in all_opps if o.get("source") == "gmail" or o.get("source_email") or o.get("email_id")]
            except Exception:
                pass

        db.log_email_sync(user_id, "SUCCESS", f"Gmail sync complete. Processed {processed_count} new opportunities.")
        return processed_count, synced_opps
    except Exception as e:
        logger.error(f"Gmail sync failed for user {user_id}: {e}", exc_info=True)
        db.log_email_sync(user_id, "FAILED", f"Error during Gmail synchronization: {str(e)}")
        return 0, []
