-- Supabase PostgreSQL Schema for OpportUnity Hub
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    university VARCHAR(255),
    branch VARCHAR(255),
    year VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. GMAIL ACCOUNTS TABLE (Encrypted credentials)
CREATE TABLE IF NOT EXISTS gmail_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    encrypted_refresh_token TEXT NOT NULL,
    scopes TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_gmail UNIQUE (user_id, email)
);

-- 3. EMAILS TABLE (Cache processed emails to avoid duplicate work)
CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    thread_id VARCHAR(255) NOT NULL,
    sender VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT,
    html TEXT,
    date_received TIMESTAMP WITH TIME ZONE NOT NULL,
    category VARCHAR(100),
    confidence FLOAT DEFAULT 1.0,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. OPPORTUNITIES TABLE
CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_id UUID REFERENCES emails(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    organization VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    eligibility TEXT,
    location VARCHAR(255),
    remote BOOLEAN DEFAULT FALSE,
    deadline DATE,
    event_date DATE,
    start_date DATE,
    end_date DATE,
    duration VARCHAR(100),
    stipend VARCHAR(255),
    salary VARCHAR(255),
    prize VARCHAR(255),
    registration_fee VARCHAR(255),
    skills_required TEXT[],
    technology TEXT[],
    experience_level VARCHAR(100),
    application_link TEXT,
    official_website TEXT,
    email VARCHAR(255),
    phone VARCHAR(50),
    attachment_links TEXT[],
    description TEXT,
    benefits TEXT,
    certificate_available BOOLEAN DEFAULT FALSE,
    source_email VARCHAR(255),
    source_sender VARCHAR(255),
    received_time TIMESTAMP WITH TIME ZONE,
    confidence FLOAT DEFAULT 1.0,
    similarity_score FLOAT DEFAULT 0.0,
    saved BOOLEAN DEFAULT FALSE,
    applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. ATTACHMENTS TABLE
CREATE TABLE IF NOT EXISTS attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    file_size INT,
    storage_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. EMAIL LOGS TABLE (Debug & Audit logs for email parsing)
CREATE TABLE IF NOT EXISTS email_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL, -- e.g., 'SUCCESS', 'FAILED', 'WARNING'
    message TEXT NOT NULL,
    error_details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. NOTIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE CASCADE,
    type VARCHAR(100) NOT NULL, -- e.g., 'NEW_INTERNSHIP', 'DEADLINE_URGENT'
    message TEXT NOT NULL,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. AUTOMATION LOGS TABLE
CREATE TABLE IF NOT EXISTS automation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL, -- e.g., 'RUNNING', 'COMPLETED', 'FAILED'
    run_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    records_processed INT DEFAULT 0,
    error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_opportunities_user ON opportunities(user_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_deadline ON opportunities(deadline);
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id) WHERE read = FALSE;

-- Row Level Security (RLS) policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE gmail_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Creating basic policies: users can access only their own rows
CREATE POLICY user_self_policy ON users FOR ALL TO public USING (auth.uid() = id);
CREATE POLICY gmail_self_policy ON gmail_accounts FOR ALL TO public USING (auth.uid() = user_id);
CREATE POLICY emails_self_policy ON emails FOR ALL TO public USING (auth.uid() = user_id);
CREATE POLICY opportunities_self_policy ON opportunities FOR ALL TO public USING (auth.uid() = user_id);
CREATE POLICY notifications_self_policy ON notifications FOR ALL TO public USING (auth.uid() = user_id);
