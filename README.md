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

## 🌐 Deployment Guide

### 1. Deploy Backend on Render (Render.com)

1. Push your repository to GitHub.
2. Log in to [Render Dashboard](https://dashboard.render.com/) and click **New +** -> **Web Service**.
3. Connect your GitHub repository: `OpportUnityHub-Smart-Opportunity-Tracker`.
4. Render will auto-detect `render.yaml` or fill in the settings:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Add your Environment Variables in Render:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI` (e.g. `https://your-render-app.onrender.com/api/auth/google/callback`)
   - `JWT_SECRET`
   - `TOKEN_ENCRYPTION_KEY`
6. Click **Deploy Web Service**. Your backend will be live at `https://your-render-backend.onrender.com`.

---

### 2. Deploy Frontend on Vercel (Vercel.com)

1. Log in to [Vercel Dashboard](https://vercel.com/) and click **Add New...** -> **Project**.
2. Import your GitHub repository: `OpportUnityHub-Smart-Opportunity-Tracker`.
3. Set **Root Directory** to `./` and **Output Directory** to `frontend`.
4. Update `vercel.json` rewrite rule to point to your Render backend URL:
   ```json
   {
     "version": 2,
     "outputDirectory": "frontend",
     "routes": [
       { "src": "/api/(.*)", "dest": "https://your-render-backend.onrender.com/api/$1" },
       { "src": "/(.*)", "dest": "/frontend/$1" }
     ]
   }
   ```
5. Click **Deploy**. Your frontend will be live on Vercel (`https://your-app.vercel.app`)!

---

## 💻 Git Push Commands

To push your latest changes to GitHub:

```bash
git init
git remote add origin https://github.com/kundurukarthik15-gif/OpportUnityHub-Smart-Opportunity-Tracker.git
git add .
git commit -m "Feat: Deploy ready configuration for Render backend and Vercel frontend"
git branch -M main
git push -u origin main --force
```
