# 🚀 OpportUnity Hub — Smart Opportunity Tracker

> Full-stack AI-powered career opportunity tracking platform for students and developers. Automatically syncs Gmail inboxes, scrapes top opportunity portals (Internshala, Devpost, Unstop, Remotive), and organizes internships, hackathons, and job applications.

---

## ✨ Features

- 📧 **Automated Gmail Inbox Sync**: Scans your Gmail inbox for internships, job offers, and hackathon invitations with AI and rule-based parsing.
- 🛡️ **Smart Security & Spam Filtering**: Automatically filters out security alerts, OTP verification emails, and non-opportunity notifications.
- 🕸️ **Multi-Source Live Scrapers**: Real-time scrapers for Internshala, Devpost, Unstop, and Remotive.
- 🔒 **User Isolation & JWT Authentication**: Multi-tenant architecture with encrypted tokens and isolated account storage.
- 💾 **Resilient Storage Engine**: Works seamlessly with Supabase Cloud DB as well as local persistent offline storage (`.local_db.json`).
- ⚡ **Full Stack Production Ready**: Built for deployment on Web, Android (PWA/Capacitor), and iOS.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.13, FastAPI, Uvicorn, Pydantic, Httpx, Google OAuth 2.0, Google GenAI / OpenAI SDKs
- **Database**: Supabase PostgREST / Python SDK with Local Memory & Disk Persistence
- **Frontend**: Responsive Modern HTML5, Vanilla JavaScript, CSS Glassmorphism

---

## 🚀 Quick Start

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/kundurukarthik15-gif/OpportUnityHub-Smart-Opportunity-Tracker.git
cd OpportUnityHub-Smart-Opportunity-Tracker

python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 3. Environment Setup
Copy `.env.example` to `.env` and populate your Google OAuth Client ID & Secret:
```bash
cp .env.example .env
```

### 4. Run Backend Server
```bash
python -m uvicorn backend.main:app --reload --port 8000
```
Open your browser to: **`http://localhost:8000/email-sync.html`** or **`http://localhost:8000/index.html`**.

---

## 💻 Git Push Commands

To push your latest changes to GitHub:

```bash
git init
git remote add origin https://github.com/kundurukarthik15-gif/OpportUnityHub-Smart-Opportunity-Tracker.git
git add .
git commit -m "Feat: Complete full-stack email sync, security filtering, user isolation, and persistent DB"
git branch -M main
git push -u origin main --force
```
