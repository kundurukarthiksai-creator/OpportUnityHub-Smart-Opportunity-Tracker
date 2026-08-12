"""
Debug script to inspect connected Gmail account and run sync_user_gmail
Run with: python debug_gmail_sync.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.db import db
from backend.email.gmail_service import sync_user_gmail, get_gmail_credentials
from googleapiclient.discovery import build

def debug_sync():
    print("=" * 60)
    print("GMAIL SYNC DEBUGGER")
    print("=" * 60)

    # 1. Fetch users from DB
    users = db._query("users", limit=10)
    print(f"Found {len(users)} users in database:")
    for u in users:
        print(f"  • User ID: {u['id']} | Email: {u['email']} | Name: {u['name']}")

    if not users:
        print("❌ No users found!")
        return

    # Use the first user or find user with linked gmail
    for user in users:
        user_id = user["id"]
        gmail_acc = db.get_gmail_account_by_user(user_id)
        if gmail_acc:
            print(f"\n✅ Found linked Gmail account for user {user['email']}:")
            print(f"   Gmail Address: {gmail_acc.get('email')}")
            print(f"   Created At:    {gmail_acc.get('created_at')}")

            # Test credentials
            print("\n🔑 Testing Google Credentials & Refresh Token...")
            creds = get_gmail_credentials(user_id)
            if not creds:
                print("❌ Failed to restore Google Credentials! Refresh token may be invalid/expired.")
                continue
            
            print("✅ Successfully restored & refreshed Google Credentials!")
            
            # Query messages directly
            service = build("gmail", "v1", credentials=creds)
            query = "is:inbox -is:spam -is:trash"
            res = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
            messages = res.get("messages", [])
            print(f"\n📧 Found {len(messages)} messages in Gmail inbox with query '{query}':")
            
            for i, m in enumerate(messages[:10]):
                msg_detail = service.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
                headers = msg_detail.get("payload", {}).get("headers", [])
                subj = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
                print(f"   [{i+1}] {subj[:50]} | From: {sender[:40]} | ID: {m['id']}")

            print("\n🚀 Running sync_user_gmail()...")
            count = sync_user_gmail(user_id)
            print(f"✅ sync_user_gmail() finished! Processed {count} opportunities.")

            # Check opportunities table
            opps = db._query("opportunities", filters={"user_id": user_id}, limit=50)
            email_opps = [o for o in opps if o.get("source_email") or o.get("email_id")]
            print(f"\n📊 User now has {len(opps)} total opportunities in DB ({len(email_opps)} from email):")
            for o in email_opps[:5]:
                print(f"   • {o.get('title')} @ {o.get('organization')} | deadline={o.get('deadline')}")

            break

if __name__ == "__main__":
    debug_sync()
