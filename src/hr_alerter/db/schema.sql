-- hr_alerter database schema
-- All 6 tables for the Polish HR Job Market Alerter

CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                    -- 'pracuj.pl', 'nofluffjobs', 'linkedin'
    job_url TEXT UNIQUE NOT NULL,            -- URL of job posting
    job_title TEXT NOT NULL,                 -- e.g., "HR Manager"
    company_name_raw TEXT NOT NULL,          -- Raw name from posting
    company_id INTEGER,                      -- FK to companies table
    location TEXT,                            -- "Warszawa", "Krakow", etc.
    post_date DATE NOT NULL,                 -- When job was posted
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    job_description TEXT,                    -- Full JD text (for keyword analysis)
    seniority_level TEXT,                    -- 'junior', 'mid', 'senior', 'director', 'c-level'
    employment_type TEXT,                    -- 'full-time', 'contract', 'part-time'
    is_relevant BOOLEAN DEFAULT 1            -- False if excluded (recruitment, junior, etc.)
);

CREATE INDEX IF NOT EXISTS idx_company_name ON job_postings (company_name_raw);
CREATE INDEX IF NOT EXISTS idx_post_date ON job_postings (post_date);
CREATE INDEX IF NOT EXISTS idx_company_id ON job_postings (company_id);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_normalized TEXT UNIQUE NOT NULL,     -- "Samsung Electronics Polska"
    linkedin_url TEXT,                        -- Full LinkedIn company URL
    linkedin_id TEXT,                         -- LinkedIn company ID
    headcount_global INTEGER,                 -- Total employees worldwide
    headcount_poland INTEGER,                 -- Employees in Poland
    industry TEXT,                            -- "Technology", "Manufacturing", etc.
    is_icp_match BOOLEAN DEFAULT 0,           -- True if 200-5k employees
    is_existing_customer BOOLEAN DEFAULT 0,   -- True if already Lyra client
    last_enriched_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_name ON companies (name_normalized);
CREATE INDEX IF NOT EXISTS idx_icp ON companies (is_icp_match);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    linkedin_url TEXT UNIQUE,
    full_name TEXT,
    job_title TEXT,
    is_decision_maker BOOLEAN DEFAULT 0,      -- HR Director, CHRO, etc.

    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    signal_date DATE NOT NULL,
    signal_type TEXT NOT NULL,                 -- 'hiring_velocity', 'keyword_match', etc.
    signal_strength INTEGER,                  -- 0-100 score
    velocity_score INTEGER,                   -- Postings in last 30 days
    posting_count_7d INTEGER,                 -- Count in last 7 days
    posting_count_30d INTEGER,                -- Count in last 30 days
    posting_count_90d INTEGER,                -- Count in last 90 days
    has_director_role BOOLEAN,                -- Hiring C-level/Director
    has_wellbeing_keywords BOOLEAN,           -- JD mentions wellbeing
    multi_city_expansion BOOLEAN,             -- Hiring in 2+ cities
    final_score INTEGER,                      -- Composite score (0-100)
    lead_temperature TEXT,                    -- 'hot', 'warm', 'cold'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_signal_date ON signals (signal_date);
CREATE INDEX IF NOT EXISTS idx_lead_temperature ON signals (lead_temperature);
CREATE INDEX IF NOT EXISTS idx_final_score ON signals (final_score);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL,
    report_type TEXT NOT NULL,                 -- 'weekly_digest', 'instant_alert'
    recipient_email TEXT NOT NULL,
    hot_count INTEGER,
    warm_count INTEGER,
    sent_at DATETIME,
    email_subject TEXT,
    email_body TEXT
);

CREATE INDEX IF NOT EXISTS idx_report_date ON reports (report_date);

CREATE TABLE IF NOT EXISTS excluded_customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    domain TEXT,                               -- Company website domain
    reason TEXT,                               -- 'existing_customer', 'past_customer', 'competitor'
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
