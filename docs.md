Polish HR Job Market Alerter - Technical Specification
Table of Contents

Project Overview
System Architecture
Data Schema
Scraping Strategy
Enrichment & Matching
Scoring Algorithm
Delivery Mechanism
Implementation Timeline
Deployment & Operations
Testing & Validation


1. Project Overview
1.1 Purpose
Automatically monitor Polish job boards for HR hiring activity and identify companies expanding their HR departments - a strong buying signal for Lyra Polska's wellbeing/EAP services.
1.2 Core Value Proposition

Input: Job postings from Polish job boards
Processing: Detect hiring velocity, match to companies, score by ICP fit
Output: Weekly report of "hot" companies to target for outreach

1.3 Success Metrics

Coverage: Monitor 500+ new HR job postings per week
Accuracy: 90%+ match rate (job posting → correct company)
Quality: 80%+ of "hot" signals match Jagoda's ICP
Speed: Weekly report delivered by Monday 8am Polish time

1.4 Key Constraints

Budget: Use free tiers where possible (SQLite, free APIs)
Timeline: 3-day build for MVP demo on Thursday Feb 13
Maintenance: Low-touch - scraper should run autonomously
Handoff: Jagoda needs zero technical setup (just receives emails)


2. System Architecture
2.1 High-Level Architecture
┌─────────────────────────────────────────────────────────────┐
│                     COORDINATOR AGENT                        │
│  (Orchestrates daily scraping & weekly report generation)   │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Pracuj.pl│  │NoFluff   │  │LinkedIn  │
│ Scraper  │  │Jobs      │  │Jobs      │
│          │  │Scraper   │  │Scraper   │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │
     └─────────────┼─────────────┘
                   ▼
         ┌─────────────────┐
         │   SQLite DB     │
         │  (job_postings) │
         └────────┬─────────┘
                  │
     ┌────────────┼────────────┐
     │            │            │
     ▼            ▼            ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Company  │  │Headcount│  │Contact  │
│Matcher  │  │Checker  │  │Finder   │
│Agent    │  │Agent    │  │Agent    │
└────┬────┘  └────┬────┘  └────┬────┘
     │            │            │
     └────────────┼────────────┘
                  ▼
         ┌─────────────────┐
         │   Enriched DB   │
         │   (companies)   │
         └────────┬─────────┘
                  │
     ┌────────────┼────────────┐
     │            │            │
     ▼            ▼            ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Velocity │  │Scoring  │  │Filter   │
│Analyzer │  │Agent    │  │Agent    │
└────┬────┘  └────┬────┘  └────┬────┘
     │            │            │
     └────────────┼────────────┘
                  ▼
         ┌─────────────────┐
         │   Signals DB    │
         │   (hot leads)   │
         └────────┬─────────┘
                  │
     ┌────────────┼────────────┐
     │            │            │
     ▼            ▼            ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Email    │  │HubSpot  │  │Slack    │
│Composer │  │Updater  │  │Alerter  │
└─────────┘  └─────────┘  └─────────┘
2.2 Agent Roles & Responsibilities
Coordinator Agent

Schedule: Runs daily at 2am Polish time
Responsibilities:

Triggers scraper agents in parallel
Monitors completion status
Handles errors/retries
Triggers enrichment after scraping completes
Generates weekly report every Monday


Tools: Cron job + orchestration logic

Scraper Agents (3 parallel agents)
Pracuj.pl Scraper

Target: https://www.pracuj.pl/praca?
Search params: Keywords: "HR", "People & Culture", "Wellbeing", "kadry"
Extracts: Job title, company name, location, post date, URL
Rate limit: 1 request/2 seconds
Output: Raw job postings to DB

NoFluffJobs Scraper

Target: https://nofluffjobs.com/pl/jobs/hr
Search params: Category: HR
Extracts: Same as Pracuj.pl
Rate limit: 1 request/2 seconds
Output: Raw job postings to DB

LinkedIn Jobs Scraper (Optional - Phase 2)

Target: https://www.linkedin.com/jobs/search/?keywords=HR&location=Poland
Challenge: Requires authentication, anti-scraping measures
Decision: Skip for MVP, add later if needed

Enrichment Agents
Company Matcher Agent

Input: Company name from job posting (e.g., "Samsung Electronics Polska Sp. z o.o.")
Process:

Normalize company name (remove "Sp. z o.o.", "S.A.", etc.)
Search LinkedIn via Clay API or manual search
Match to LinkedIn company URL
Extract company LinkedIn ID


Output: Matched company record with LinkedIn URL
Fallback: If no match, mark as "unmatched" for manual review

Headcount Checker Agent

Input: LinkedIn company URL
Process:

Scrape LinkedIn company page "About" section
Extract employee count (global)
If available, extract Poland-specific headcount
Flag companies in 200-5,000 range


Output: Company headcount data
Alternative: Use Clay's "Company Headcount" enrichment

Contact Finder Agent

Input: Company LinkedIn URL + job title
Process:

Search LinkedIn for HR Director/CHRO at company
Extract profile URL
Store for outreach targeting


Output: Decision-maker contact info
Tool: Clay's "Find People at Company" enrichment

Analysis Agents
Velocity Analyzer Agent

Input: All job postings for a company in last 90 days
Process:

Count HR postings per company
Calculate posting frequency (roles/day)
Identify spikes (3+ in 30 days = hot)
Detect patterns (multi-city, seniority mix)


Output: Velocity score (0-100)

Scoring Agent

Input: Company data + velocity score + ICP criteria
Process: Calculate composite score (see Section 6)
Output: Final lead score (0-100)

Filter Agent

Input: Scored companies
Process:

Check ICP fit (job titles, company size)
Exclude existing Lyra customers
Exclude recruitment-only roles
Rank by score


Output: Filtered list of hot/warm/cold leads

Output Agents
Email Composer Agent

Schedule: Monday 6am Polish time
Process:

Pull hot/warm leads from DB
Format into email template
Send to Jagoda's email


Tool: SendGrid API or SMTP

HubSpot Updater Agent (Optional - Phase 2)

Process:

Create/update company records
Create/update contact records
Set custom properties (signal score, velocity)
Create tasks for sales team


Tool: HubSpot API

Slack Alerter Agent (Optional - Phase 2)

Process: Send instant alerts for ultra-hot signals (5+ postings in 7 days)
Tool: Slack webhook


3. Data Schema
3.1 Database Choice: SQLite
Rationale:

✅ Zero setup (file-based)
✅ Sufficient for 1,000s of records
✅ Easy to backup/transfer
✅ No hosting costs
✅ Can migrate to PostgreSQL later if needed

Location: /data/hr_alerter.db
3.2 Tables
job_postings
sqlCREATE TABLE job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- 'pracuj.pl', 'nofluffjobs', 'linkedin'
    job_url TEXT UNIQUE NOT NULL,      -- URL of job posting
    job_title TEXT NOT NULL,           -- e.g., "HR Manager"
    company_name_raw TEXT NOT NULL,    -- Raw name from posting
    company_id INTEGER,                -- FK to companies table
    location TEXT,                     -- "Warszawa", "Kraków", etc.
    post_date DATE NOT NULL,           -- When job was posted
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    job_description TEXT,              -- Full JD text (for keyword analysis)
    seniority_level TEXT,              -- 'junior', 'mid', 'senior', 'director', 'c-level'
    employment_type TEXT,              -- 'full-time', 'contract', 'part-time'
    is_relevant BOOLEAN DEFAULT 1,     -- False if excluded (recruitment, junior, etc.)
    
    INDEX idx_company_name (company_name_raw),
    INDEX idx_post_date (post_date),
    INDEX idx_company_id (company_id)
);
companies
sqlCREATE TABLE companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_normalized TEXT UNIQUE NOT NULL, -- "Samsung Electronics Polska"
    linkedin_url TEXT,                    -- Full LinkedIn company URL
    linkedin_id TEXT,                     -- LinkedIn company ID
    headcount_global INTEGER,             -- Total employees worldwide
    headcount_poland INTEGER,             -- Employees in Poland
    industry TEXT,                        -- "Technology", "Manufacturing", etc.
    is_icp_match BOOLEAN DEFAULT 0,       -- True if 200-5k employees
    is_existing_customer BOOLEAN DEFAULT 0, -- True if already Lyra client
    last_enriched_at DATETIME,
    
    INDEX idx_name (name_normalized),
    INDEX idx_icp (is_icp_match)
);
contacts
sqlCREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    linkedin_url TEXT UNIQUE,
    full_name TEXT,
    job_title TEXT,
    is_decision_maker BOOLEAN DEFAULT 0,  -- HR Director, CHRO, etc.
    
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
signals
sqlCREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    signal_date DATE NOT NULL,
    signal_type TEXT NOT NULL,         -- 'hiring_velocity', 'keyword_match', etc.
    signal_strength INTEGER,           -- 0-100 score
    velocity_score INTEGER,            -- Postings in last 30 days
    posting_count_7d INTEGER,          -- Count in last 7 days
    posting_count_30d INTEGER,         -- Count in last 30 days
    posting_count_90d INTEGER,         -- Count in last 90 days
    has_director_role BOOLEAN,         -- Hiring C-level/Director
    has_wellbeing_keywords BOOLEAN,    -- JD mentions wellbeing
    multi_city_expansion BOOLEAN,      -- Hiring in 2+ cities
    final_score INTEGER,               -- Composite score (0-100)
    lead_temperature TEXT,             -- 'hot', 'warm', 'cold'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (company_id) REFERENCES companies(id),
    INDEX idx_signal_date (signal_date),
    INDEX idx_lead_temperature (lead_temperature),
    INDEX idx_final_score (final_score)
);
reports
sqlCREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL,
    report_type TEXT NOT NULL,         -- 'weekly_digest', 'instant_alert'
    recipient_email TEXT NOT NULL,
    hot_count INTEGER,
    warm_count INTEGER,
    sent_at DATETIME,
    email_subject TEXT,
    email_body TEXT,
    
    INDEX idx_report_date (report_date)
);
excluded_customers
sqlCREATE TABLE excluded_customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    domain TEXT,                       -- Company website domain
    reason TEXT,                       -- 'existing_customer', 'past_customer', 'competitor'
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
3.3 Sample Queries
Get hot companies for this week:
sqlSELECT 
    c.name_normalized,
    c.linkedin_url,
    s.posting_count_7d,
    s.posting_count_30d,
    s.final_score,
    s.has_director_role,
    s.has_wellbeing_keywords
FROM signals s
JOIN companies c ON s.company_id = c.id
WHERE s.signal_date >= date('now', '-7 days')
  AND s.lead_temperature = 'hot'
  AND c.is_existing_customer = 0
ORDER BY s.final_score DESC;
Calculate velocity for a company:
sqlSELECT 
    company_id,
    COUNT(*) as total_postings,
    COUNT(CASE WHEN post_date >= date('now', '-7 days') THEN 1 END) as last_7d,
    COUNT(CASE WHEN post_date >= date('now', '-30 days') THEN 1 END) as last_30d,
    COUNT(CASE WHEN seniority_level IN ('director', 'c-level') THEN 1 END) as senior_roles
FROM job_postings
WHERE company_id = ?
  AND is_relevant = 1
GROUP BY company_id;

4. Scraping Strategy
4.1 Target Websites
Pracuj.pl

URL Pattern: https://www.pracuj.pl/praca?q={keyword}&pn={page}
Keywords: "HR", "kadry", "People Culture", "Wellbeing", "zasoby ludzkie"
Pagination: Pages 1-10 (covers ~250 jobs)
HTML Structure:

Job cards: div.listing__item
Title: h2.offer-details__title-link
Company: h3.company-name
Location: span.offer-labels__item--location
Date: span.offer-labels__item--date
URL: a.offer-details__title-link[href]



Sample Scraping Code:
pythonimport requests
from bs4 import BeautifulSoup
import time

def scrape_pracuj(keyword, max_pages=10):
    jobs = []
    base_url = "https://www.pracuj.pl/praca"
    
    for page in range(1, max_pages + 1):
        params = {'q': keyword, 'pn': page}
        response = requests.get(base_url, params=params)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        job_cards = soup.find_all('div', class_='listing__item')
        
        for card in job_cards:
            try:
                title_elem = card.find('h2', class_='offer-details__title-link')
                company_elem = card.find('h3', class_='company-name')
                location_elem = card.find('span', class_='offer-labels__item--location')
                date_elem = card.find('span', class_='offer-labels__item--date')
                
                job = {
                    'source': 'pracuj.pl',
                    'job_title': title_elem.text.strip() if title_elem else None,
                    'company_name_raw': company_elem.text.strip() if company_elem else None,
                    'location': location_elem.text.strip() if location_elem else None,
                    'post_date': parse_date(date_elem.text.strip()) if date_elem else None,
                    'job_url': title_elem.find('a')['href'] if title_elem else None,
                }
                
                jobs.append(job)
            except Exception as e:
                print(f"Error parsing job card: {e}")
                continue
        
        time.sleep(2)  # Rate limiting
    
    return jobs
NoFluffJobs

URL Pattern: https://nofluffjobs.com/pl/jobs/hr?page={page}
Pagination: Pages 1-5
HTML Structure:

Job cards: a.posting-list-item
Title: h3.posting-title__position
Company: span.posting-title__company-name
Location: span.posting-details__item--location
URL: a.posting-list-item[href]



Note: NoFluffJobs may require JavaScript rendering. If BeautifulSoup fails, use Playwright:
pythonfrom playwright.sync_api import sync_playwright

def scrape_nofluff_js(max_pages=5):
    jobs = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        for page_num in range(1, max_pages + 1):
            page.goto(f'https://nofluffjobs.com/pl/jobs/hr?page={page_num}')
            page.wait_for_selector('a.posting-list-item')
            
            job_cards = page.query_selector_all('a.posting-list-item')
            
            for card in job_cards:
                job = {
                    'source': 'nofluffjobs',
                    'job_title': card.query_selector('h3').inner_text(),
                    'company_name_raw': card.query_selector('span.company').inner_text(),
                    'job_url': card.get_attribute('href'),
                }
                jobs.append(job)
            
            time.sleep(2)
        
        browser.close()
    
    return jobs
4.2 Keyword Strategy
Primary Keywords (Polish):

"HR Director" / "Dyrektor HR"
"People & Culture" / "Kultura organizacyjna"
"Wellbeing Manager" / "Kierownik ds. wellbeing"
"HR Business Partner" / "Partner biznesowy HR"
"Employee Experience"
"Zasoby ludzkie"

Exclusion Keywords (auto-filter):

"Talent Acquisition" / "Rekrutacja"
"Recruiter" / "Rekruter"
"Junior HR"
"Praktykant HR" (HR Intern)
"Specjalista HR" (unless in larger company)

4.3 Anti-Scraping Measures
Pracuj.pl:

✅ No CAPTCHA (as of Feb 2026)
✅ No login required
⚠️ Rate limit: 1 request/2 seconds
⚠️ User-Agent rotation recommended

NoFluffJobs:

⚠️ JavaScript-rendered (needs Playwright)
✅ No login required
⚠️ Rate limit: 1 request/2 seconds

Best Practices:
python# Rotate User-Agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
]

headers = {
    'User-Agent': random.choice(USER_AGENTS),
    'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
}

# Add delays
time.sleep(random.uniform(2, 4))

# Respect robots.txt
# Check: https://www.pracuj.pl/robots.txt
4.4 Data Normalization
Company Name Cleaning:
pythondef normalize_company_name(raw_name):
    """
    Samsung Electronics Polska Sp. z o.o.
    → Samsung Electronics Polska
    """
    # Remove legal suffixes
    suffixes = [
        'Sp. z o.o.', 'S.A.', 'Sp. z o. o.',
        'Spółka z ograniczoną odpowiedzialnością',
        'Spółka Akcyjna',
    ]
    
    name = raw_name.strip()
    for suffix in suffixes:
        name = name.replace(suffix, '')
    
    return name.strip()
Date Parsing:
pythondef parse_date(date_str):
    """
    "2 dni temu" → 2026-02-06
    "wczoraj" → 2026-02-07
    "dzisiaj" → 2026-02-08
    """
    today = datetime.date.today()
    
    if 'dzisiaj' in date_str.lower():
        return today
    elif 'wczoraj' in date_str.lower():
        return today - datetime.timedelta(days=1)
    elif 'dni temu' in date_str.lower():
        days = int(date_str.split()[0])
        return today - datetime.timedelta(days=days)
    else:
        # Try parsing as date: "08.02.2026"
        return datetime.datetime.strptime(date_str, '%d.%m.%Y').date()

5. Enrichment & Matching
5.1 Company Matching Strategy
Goal: Match "Samsung Electronics Polska Sp. z o.o." → LinkedIn company URL
Approach:
Option A: Clay API (Recommended for MVP)
python# Use Clay's "Find Company" enrichment
import requests

def match_company_clay(company_name):
    """
    Uses Clay API to find LinkedIn company URL
    """
    clay_api_key = os.getenv('CLAY_API_KEY')
    
    response = requests.post(
        'https://api.clay.com/v1/enrichment/company/find',
        headers={'Authorization': f'Bearer {clay_api_key}'},
        json={
            'company_name': company_name,
            'location': 'Poland',
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        return {
            'linkedin_url': data.get('linkedin_url'),
            'headcount': data.get('employee_count'),
            'industry': data.get('industry'),
        }
    
    return None
Option B: Manual LinkedIn Search (Fallback)
pythonfrom playwright.sync_api import sync_playwright

def search_linkedin_company(company_name):
    """
    Search LinkedIn for company, extract URL
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        # LinkedIn company search
        search_url = f'https://www.linkedin.com/search/results/companies/?keywords={company_name}'
        page.goto(search_url)
        page.wait_for_selector('.entity-result__title-text')
        
        # Get first result
        first_result = page.query_selector('a.app-aware-link')
        linkedin_url = first_result.get_attribute('href') if first_result else None
        
        browser.close()
        return linkedin_url
Matching Confidence Score:
pythondef calculate_match_confidence(raw_name, linkedin_name):
    """
    Compare job posting name vs LinkedIn name
    Return confidence score 0-100
    """
    # Simple fuzzy matching
    from difflib import SequenceMatcher
    
    raw_normalized = normalize_company_name(raw_name).lower()
    linkedin_normalized = linkedin_name.lower()
    
    ratio = SequenceMatcher(None, raw_normalized, linkedin_normalized).ratio()
    
    return int(ratio * 100)

# Example:
# "Samsung Electronics Polska" vs "Samsung Electronics Poland"
# → 85% confidence (good match)
5.2 Headcount Enrichment
Option A: LinkedIn Scraping
pythondef get_headcount_linkedin(linkedin_url):
    """
    Scrape LinkedIn company page for headcount
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f'{linkedin_url}/about')
        
        # Look for employee count in "About" section
        # Pattern: "201-500 employees" or "1,001-5,000 employees"
        about_text = page.inner_text('.org-page-details__definition')
        
        # Parse headcount range
        headcount = parse_headcount_range(about_text)
        
        browser.close()
        return headcount
Option B: Clay API
python# Clay's "Company Headcount" enrichment
def get_headcount_clay(linkedin_url):
    response = requests.post(
        'https://api.clay.com/v1/enrichment/company/headcount',
        headers={'Authorization': f'Bearer {clay_api_key}'},
        json={'linkedin_url': linkedin_url}
    )
    
    return response.json().get('employee_count')
Polish Headcount Detection:
pythondef get_poland_headcount(linkedin_url):
    """
    Scrape LinkedIn 'People' tab filtered by Poland
    URL: {company_url}/people/?keywords=polska
    
    Returns: Approximate count of employees in Poland
    """
    # This is what Jagoda mentioned she does manually
    poland_url = f'{linkedin_url}/people/?keywords=polska'
    
    # Scrape the results count
    # Example: "About 450 results" → return 450
    pass  # Implement scraping logic
5.3 Contact Finding
Goal: Find HR Director/CHRO at target company
Clay API Method:
pythondef find_hr_contacts(company_linkedin_url):
    """
    Find HR decision-makers at company
    """
    response = requests.post(
        'https://api.clay.com/v1/enrichment/people/search',
        headers={'Authorization': f'Bearer {clay_api_key}'},
        json={
            'company_linkedin_url': company_linkedin_url,
            'job_titles': [
                'HR Director',
                'CHRO',
                'Chief People Officer',
                'Dyrektor HR',
                'VP of HR',
            ],
            'location': 'Poland',
            'seniority': ['director', 'vp', 'c-level'],
        }
    )
    
    return response.json().get('people', [])

6. Scoring Algorithm
6.1 Signal Components
Each company gets scored on 5 dimensions:

Hiring Velocity (40 points max)
Seniority Mix (20 points max)
ICP Fit (20 points max)
Content Signals (10 points max)
Recency (10 points max)

Total Score: 0-100
6.2 Velocity Scoring
pythondef calculate_velocity_score(company_id):
    """
    Score based on hiring frequency
    """
    postings_7d = count_postings(company_id, days=7)
    postings_30d = count_postings(company_id, days=30)
    postings_90d = count_postings(company_id, days=90)
    
    # Scoring thresholds
    if postings_7d >= 3:
        return 40  # Ultra hot - hiring NOW
    elif postings_30d >= 5:
        return 35  # Very hot
    elif postings_30d >= 3:
        return 30  # Hot
    elif postings_30d >= 2:
        return 20  # Warm
    elif postings_90d >= 2:
        return 10  # Lukewarm
    else:
        return 0   # Cold
6.3 Seniority Mix Scoring
pythondef calculate_seniority_score(company_id):
    """
    Score based on role seniority
    """
    postings = get_recent_postings(company_id, days=30)
    
    has_director = any(p['seniority_level'] in ['director', 'c-level'] for p in postings)
    has_senior = any(p['seniority_level'] == 'senior' for p in postings)
    has_multiple_levels = len(set(p['seniority_level'] for p in postings)) >= 2
    
    score = 0
    
    if has_director:
        score += 15  # Hiring leadership = strategic investment
    if has_senior:
        score += 5
    if has_multiple_levels:
        score += 5  # Expanding entire team, not just backfill
    
    return min(score, 20)
6.4 ICP Fit Scoring
pythondef calculate_icp_score(company_id):
    """
    Score based on Jagoda's ICP criteria
    """
    company = get_company(company_id)
    score = 0
    
    # Headcount in range (200-5,000)
    if 200 <= company['headcount_poland'] <= 5000:
        score += 15
    elif 5000 < company['headcount_poland'] <= 10000:
        score += 10  # Still acceptable for global contracts
    
    # Job titles match target list
    postings = get_recent_postings(company_id, days=30)
    target_titles = [
        'HR Director', 'People & Culture', 'Wellbeing', 'Employee Experience',
        'CHRO', 'CPO', 'HR Business Partner', 'Culture and Engagement',
    ]
    
    matching_titles = sum(
        any(target in p['job_title'] for target in target_titles)
        for p in postings
    )
    
    if matching_titles >= 2:
        score += 5
    
    return min(score, 20)
6.5 Content Signals Scoring
pythondef calculate_content_score(company_id):
    """
    Score based on job description keywords
    """
    postings = get_recent_postings(company_id, days=30)
    
    # High-value keywords
    wellbeing_keywords = ['wellbeing', 'dobrostan', 'mental health', 'zdrowie psychiczne']
    eap_keywords = ['EAP', 'employee assistance', 'wsparcie pracowników']
    culture_keywords = ['kultura organizacyjna', 'employer branding', 'employee experience']
    
    score = 0
    
    for posting in postings:
        jd = posting.get('job_description', '').lower()
        
        if any(kw in jd for kw in wellbeing_keywords):
            score += 5
        if any(kw in jd for kw in eap_keywords):
            score += 3
        if any(kw in jd for kw in culture_keywords):
            score += 2
    
    return min(score, 10)
6.6 Recency Scoring
pythondef calculate_recency_score(company_id):
    """
    Score decays over time - fresh signals matter most
    """
    most_recent_posting = get_most_recent_posting(company_id)
    days_ago = (datetime.date.today() - most_recent_posting['post_date']).days
    
    if days_ago <= 3:
        return 10  # Posted this week
    elif days_ago <= 7:
        return 8
    elif days_ago <= 14:
        return 5
    elif days_ago <= 30:
        return 3
    else:
        return 0   # Stale signal
6.7 Final Composite Score
pythondef calculate_final_score(company_id):
    """
    Combine all signals into final score
    """
    velocity = calculate_velocity_score(company_id)
    seniority = calculate_seniority_score(company_id)
    icp = calculate_icp_score(company_id)
    content = calculate_content_score(company_id)
    recency = calculate_recency_score(company_id)
    
    total_score = velocity + seniority + icp + content + recency
    
    # Classify lead temperature
    if total_score >= 75:
        temperature = 'hot'
    elif total_score >= 50:
        temperature = 'warm'
    else:
        temperature = 'cold'
    
    return {
        'final_score': total_score,
        'lead_temperature': temperature,
        'breakdown': {
            'velocity': velocity,
            'seniority': seniority,
            'icp': icp,
            'content': content,
            'recency': recency,
        }
    }
```

### 6.8 Scoring Examples

**Example 1: Samsung Electronics Polska**
```
Postings in last 30 days: 4
  - 1x HR Director
  - 2x HR Managers
  - 1x Wellbeing Coordinator

Velocity Score: 30 (3+ in 30 days)
Seniority Score: 20 (Director + multiple levels)
ICP Score: 15 (450 employees in Poland = perfect fit)
Content Score: 8 ("wellbeing" in JD + "employee experience")
Recency Score: 10 (posted 2 days ago)

TOTAL: 83 → 🔥 HOT
```

**Example 2: Small Startup (50 employees)**
```
Postings in last 30 days: 2
  - 1x HR Generalist
  - 1x HR Coordinator

Velocity Score: 20 (2 in 30 days)
Seniority Score: 0 (no senior roles)
ICP Score: 0 (below 200 employee threshold)
Content Score: 0 (no wellbeing keywords)
Recency Score: 5 (posted 10 days ago)

TOTAL: 25 → ❄️ COLD (excluded from report)
```

---

## 7. Delivery Mechanism

### 7.1 Email Report Format

**Subject Line**:
```
🔥 12 Companies Scaling HR Teams This Week | Polish Job Market Alerter
Email Body (HTML):
html<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; }
        .header { background: #0066cc; color: white; padding: 20px; }
        .signal { border-left: 4px solid #ff6b35; padding: 15px; margin: 20px 0; background: #f9f9f9; }
        .signal.hot { border-color: #ff6b35; }
        .signal.warm { border-color: #ffa500; }
        .stat { display: inline-block; background: #e8f4f8; padding: 8px 12px; margin: 5px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Weekly HR Hiring Report</h1>
        <p>Week of February 10-17, 2026</p>
    </div>
    
    <div style="padding: 20px;">
        <h2>🔥 HOT SIGNALS (3 companies)</h2>
        <p>Companies with 3+ HR hires in 30 days - perfect timing for outreach</p>
        
        <div class="signal hot">
            <h3>Samsung Electronics Polska</h3>
            <div class="stat">Score: 83/100</div>
            <div class="stat">4 postings in 30 days</div>
            <div class="stat">450 employees (Poland)</div>
            
            <p><strong>Recent Hires:</strong></p>
            <ul>
                <li>HR Director - Posted 2 days ago</li>
                <li>Wellbeing Coordinator - Posted 5 days ago ⭐</li>
                <li>HR Manager - Posted 12 days ago</li>
            </ul>
            
            <p><strong>Why Now:</strong> They're building a dedicated wellbeing function. Job description mentions "implementing employee mental health programs."</p>
            
            <p><strong>Contact:</strong><br>
            Jan Kowalski - HR Director<br>
            <a href="https://linkedin.com/in/jankowalski">LinkedIn Profile</a>
            </p>
            
            <p><strong>Action:</strong><br>
            <a href="https://app.hubspot.com/contacts/12345/company/67890">View in HubSpot</a> | 
            <a href="mailto:sales@lyrapolska.pl?subject=Samsung - HR Expansion Opportunity">Email Sales Team</a>
            </p>
        </div>
        
        <div class="signal hot">
            <h3>Allegro</h3>
            <!-- Similar format -->
        </div>
        
        <hr>
        
        <h2>⚡ WARM SIGNALS (9 companies)</h2>
        <p>Companies with 2 HR hires in 30 days - worth monitoring</p>
        
        <div class="signal warm">
            <h3>Company Name</h3>
            <!-- Abbreviated format for warm leads -->
        </div>
        
        <hr>
        
        <h2>📊 This Week's Stats</h2>
        <ul>
            <li>Total HR postings monitored: 287</li>
            <li>New companies hiring: 45</li>
            <li>ICP matches: 23</li>
            <li>Hot signals: 3</li>
            <li>Warm signals: 9</li>
        </ul>
        
        <p><a href="https://dashboard.example.com/reports/2026-02-17">View Full Report</a></p>
    </div>
</body>
</html>
7.2 Email Sending Code
pythonimport smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_weekly_report(recipient_email, html_content):
    """
    Send weekly report via SMTP
    """
    sender_email = os.getenv('SMTP_EMAIL')
    sender_password = os.getenv('SMTP_PASSWORD')
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🔥 Polish HR Hiring Report | Week of {get_week_range()}"
    msg['From'] = sender_email
    msg['To'] = recipient_email
    
    # Attach HTML body
    html_part = MIMEText(html_content, 'html')
    msg.attach(html_part)
    
    # Send via SMTP
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(msg)
    
    print(f"Report sent to {recipient_email}")
Alternative: SendGrid API
pythonimport sendgrid
from sendgrid.helpers.mail import Mail

def send_via_sendgrid(recipient_email, html_content):
    sg = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))
    
    message = Mail(
        from_email='alerts@yourdomain.com',
        to_emails=recipient_email,
        subject='Polish HR Hiring Report',
        html_content=html_content
    )
    
    response = sg.send(message)
    return response.status_code
7.3 HubSpot Integration (Optional - Phase 2)
Create Company Record:
pythonimport requests

def create_hubspot_company(company_data):
    """
    Create company in HubSpot with signal data
    """
    hubspot_api_key = os.getenv('HUBSPOT_API_KEY')
    
    url = 'https://api.hubapi.com/crm/v3/objects/companies'
    headers = {
        'Authorization': f'Bearer {hubspot_api_key}',
        'Content-Type': 'application/json',
    }
    
    properties = {
        'name': company_data['name'],
        'domain': company_data['domain'],
        'linkedin_company_page': company_data['linkedin_url'],
        'numberofemployees': company_data['headcount_poland'],
        
        # Custom properties (need to be created in HubSpot first)
        'hr_hiring_velocity': company_data['velocity_score'],
        'signal_source': 'job_market_alerter',
        'signal_date': company_data['signal_date'],
        'signal_strength': company_data['final_score'],
        'lead_temperature': company_data['lead_temperature'],
    }
    
    payload = {'properties': properties}
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()
Create Contact & Associate with Company:
pythondef create_hubspot_contact(contact_data, company_id):
    """
    Create contact in HubSpot and link to company
    """
    # Create contact
    url = 'https://api.hubapi.com/crm/v3/objects/contacts'
    
    properties = {
        'firstname': contact_data['first_name'],
        'lastname': contact_data['last_name'],
        'jobtitle': contact_data['job_title'],
        'linkedin': contact_data['linkedin_url'],
    }
    
    response = requests.post(url, headers=headers, json={'properties': properties})
    contact_id = response.json()['id']
    
    # Associate contact with company
    association_url = f'https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}/associations/companies/{company_id}/280'
    requests.put(association_url, headers=headers)
    
    return contact_id
Create Task for Sales:
pythondef create_sales_task(company_name, contact_name, hubspot_owner_id):
    """
    Create task in HubSpot for sales rep
    """
    url = 'https://api.hubapi.com/crm/v3/objects/tasks'
    
    properties = {
        'hs_task_subject': f'Outreach: {company_name} - HR Expansion Signal',
        'hs_task_body': f'{company_name} is hiring 3+ HR roles. Contact {contact_name} this week.',
        'hs_task_status': 'NOT_STARTED',
        'hs_task_priority': 'HIGH',
        'hubspot_owner_id': hubspot_owner_id,
        'hs_timestamp': datetime.datetime.now().isoformat(),
    }
    
    response = requests.post(url, headers=headers, json={'properties': properties})
    return response.json()
```

---

## 8. Implementation Timeline

### 8.1 3-Day Build Schedule

#### **Day 1: Scraping Infrastructure** (8 hours)

**Morning (4 hours)**:
- [ ] Set up project structure
```
  /hr-alerter
  ├── /data
  │   └── hr_alerter.db
  ├── /scrapers
  │   ├── pracuj_scraper.py
  │   ├── nofluff_scraper.py
  │   └── utils.py
  ├── /database
  │   ├── schema.sql
  │   └── db_manager.py
  ├── /config
  │   ├── settings.py
  │   └── .env.example
  └── requirements.txt

 Create SQLite database schema (Section 3.2)
 Build Pracuj.pl scraper
 Test on 5 pages, validate data quality

Afternoon (4 hours):

 Build NoFluffJobs scraper
 Implement data normalization (company names, dates)
 Test scraping both sites
 Store 7 days of historical data in DB
 Add logging and error handling

End of Day 1 Checkpoint:
✅ 200+ job postings scraped and stored
✅ Company names normalized
✅ Database populated with test data

Day 2: Enrichment & Analysis (8 hours)
Morning (4 hours):

 Build company matcher

Option: Use Clay API for LinkedIn matching
Fallback: Manual search script


 Test matching on 20 companies
 Validate match accuracy (should be 80%+)
 Build headcount checker

Scrape LinkedIn company pages OR use Clay API
Focus on Poland-specific headcount if possible



Afternoon (4 hours):

 Implement velocity analyzer (Section 6.2)
 Implement scoring algorithm (Section 6)
 Test scoring on sample companies
 Build filter logic (ICP matching, exclusions)

End of Day 2 Checkpoint:
✅ 50+ companies matched to LinkedIn
✅ Headcount data enriched
✅ Scoring system working (hot/warm/cold classification)
✅ 10-15 "hot" leads identified

Day 3: Delivery & Demo Prep (8 hours)
Morning (4 hours):

 Build email template (Section 7.1)
 Implement email sending (SMTP or SendGrid)
 Generate first weekly report with real data
 Test email delivery to your own inbox

Afternoon (4 hours):

 Run full end-to-end pipeline

Scrape → Enrich → Score → Filter → Report


 Validate data quality in report
 Create demo Loom video

Walk through sample report
Explain each section
Show scoring logic
Demonstrate value


 Prepare backup slides (in case Loom fails)
 Write demo script for Thursday meeting

End of Day 3 Checkpoint:
✅ Working end-to-end system
✅ Sample weekly report generated
✅ Demo video ready
✅ Confidence in presentation

8.2 Post-MVP Roadmap (Phase 2+)
Week 2: HubSpot Integration

Build HubSpot API connector
Auto-create company records
Auto-create contact records
Create tasks for sales team
Test integration with Jagoda's account

Week 3: Slack Alerts

Build instant alert system for ultra-hot signals
Webhook integration
Alert formatting
Test with Jagoda's Slack

Week 4: Dashboard

Build simple web dashboard
Show historical trends
Company detail pages
Export to CSV

Month 2: Expand Data Sources

Add LinkedIn Jobs scraping (if valuable)
Add company career pages scraping
Add Rocket Jobs, Just Join IT
Increase coverage from 200 → 500 postings/week

Month 3: Advanced Features

Competitive intelligence (who else is hiring HR?)
Predictive scoring (ML model)
Custom alert rules per user
Multi-language support (if expanding to other markets)


9. Deployment & Operations
9.1 Hosting Options
Option A: Local Machine (MVP)
Pros:

Zero cost
Full control
Easy debugging

Cons:

Must keep computer running 24/7
No redundancy

Setup:
bash# Set up cron job to run daily at 2am
crontab -e

# Add line:
0 2 * * * cd /path/to/hr-alerter && python main.py scrape
0 6 * * 1 cd /path/to/hr-alerter && python main.py report

Option B: Cloud VPS (Production)
Recommended: DigitalOcean Droplet, Hetzner VPS, or AWS Lightsail
Specs:

1 vCPU, 1GB RAM ($5-6/month)
Ubuntu 22.04 LTS
25GB SSD

Setup:
bash# SSH into server
ssh root@your-server-ip

# Install dependencies
apt update
apt install python3 python3-pip sqlite3 cron

# Clone your repo
git clone https://github.com/yourusername/hr-alerter
cd hr-alerter

# Install Python packages
pip3 install -r requirements.txt

# Set up environment variables
cp .env.example .env
nano .env  # Add API keys

# Set up cron
crontab -e
# Add same cron lines as above

Option C: Serverless (Advanced)
Platform: AWS Lambda + CloudWatch Events OR Railway
Pros:

Auto-scaling
Pay per execution
No server management

Cons:

More complex setup
Cold start delays
Database hosting separate


9.2 Monitoring & Alerts
Daily Health Check:
pythondef health_check():
    """
    Run after each scrape to validate data quality
    """
    checks = {
        'postings_today': count_postings_today(),
        'companies_enriched': count_enriched_companies(),
        'scraper_errors': get_error_count(),
        'last_scrape_time': get_last_scrape_timestamp(),
    }
    
    # Alert if something is wrong
    if checks['postings_today'] < 50:
        send_alert("⚠️ Low scraping volume today")
    
    if checks['scraper_errors'] > 10:
        send_alert("🚨 High error rate in scrapers")
    
    return checks
Error Notification:
pythondef send_alert(message):
    """
    Send alert to your email/Slack if system fails
    """
    # Email yourself
    send_email(
        to='richard.angapin@outlook.com',
        subject='HR Alerter System Alert',
        body=message
    )
    
    # Or Slack
    requests.post(
        'https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
        json={'text': message}
    )
Logging:
pythonimport logging

logging.basicConfig(
    filename='/var/log/hr-alerter.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Usage
logging.info("Scraping started")
logging.error(f"Failed to scrape {url}: {error}")

9.3 Backup Strategy
Daily Database Backup:
bash#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d)
DB_PATH="/home/hr-alerter/data/hr_alerter.db"
BACKUP_DIR="/home/hr-alerter/backups"

# Create backup
sqlite3 $DB_PATH ".backup $BACKUP_DIR/hr_alerter_$DATE.db"

# Keep only last 30 days
find $BACKUP_DIR -name "hr_alerter_*.db" -mtime +30 -delete

echo "Backup created: hr_alerter_$DATE.db"
Cron Job:
bash0 3 * * * /home/hr-alerter/backup.sh

9.4 Security Considerations
Environment Variables (.env file):
bash# Never commit this file to Git
CLAY_API_KEY=sk_live_xxx
SENDGRID_API_KEY=SG.xxx
HUBSPOT_API_KEY=pat-na1-xxx
SMTP_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-app-password
Database Security:
bash# Restrict file permissions
chmod 600 /home/hr-alerter/data/hr_alerter.db
chmod 600 /home/hr-alerter/.env
API Rate Limiting:
pythonimport time
from functools import wraps

def rate_limit(calls_per_minute):
    """
    Decorator to limit API calls
    """
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        
        return wrapper
    return decorator

# Usage
@rate_limit(calls_per_minute=30)
def scrape_page(url):
    # This will never exceed 30 calls/minute
    pass

10. Testing & Validation
10.1 Unit Tests
Test Scraping Logic:
pythonimport unittest

class TestScrapers(unittest.TestCase):
    def test_pracuj_scraper(self):
        """Test Pracuj.pl scraper returns valid data"""
        jobs = scrape_pracuj('HR', max_pages=1)
        
        self.assertGreater(len(jobs), 0)
        self.assertIn('job_title', jobs[0])
        self.assertIn('company_name_raw', jobs[0])
        self.assertIsNotNone(jobs[0]['job_url'])
    
    def test_company_name_normalization(self):
        """Test company name cleaning"""
        raw = "Samsung Electronics Polska Sp. z o.o."
        normalized = normalize_company_name(raw)
        
        self.assertEqual(normalized, "Samsung Electronics Polska")
    
    def test_date_parsing(self):
        """Test Polish date parsing"""
        self.assertEqual(parse_date('dzisiaj'), datetime.date.today())
        self.assertEqual(parse_date('wczoraj'), datetime.date.today() - datetime.timedelta(days=1))
Test Scoring Algorithm:
pythonclass TestScoring(unittest.TestCase):
    def test_velocity_scoring(self):
        """Test hiring velocity calculation"""
        # Create test company with 3 postings in 7 days
        company_id = create_test_company()
        add_test_postings(company_id, count=3, days_ago=3)
        
        score = calculate_velocity_score(company_id)
        self.assertEqual(score, 40)  # Should be ultra hot
    
    def test_icp_filtering(self):
        """Test ICP match logic"""
        company = {
            'headcount_poland': 500,
            'job_titles': ['HR Director', 'Wellbeing Manager']
        }
        
        icp_score = calculate_icp_score(company)
        self.assertGreater(icp_score, 15)  # Should match ICP

10.2 Data Quality Checks
Validation Script:
pythondef validate_data_quality():
    """
    Check data quality after scraping
    """
    issues = []
    
    # Check for missing company names
    missing_names = db.execute(
        "SELECT COUNT(*) FROM job_postings WHERE company_name_raw IS NULL"
    ).fetchone()[0]
    
    if missing_names > 0:
        issues.append(f"{missing_names} postings missing company names")
    
    # Check for unmatched companies
    unmatched = db.execute(
        "SELECT COUNT(*) FROM companies WHERE linkedin_url IS NULL"
    ).fetchone()[0]
    
    if unmatched > 20:
        issues.append(f"{unmatched} companies not matched to LinkedIn")
    
    # Check for stale data
    last_scrape = db.execute(
        "SELECT MAX(scraped_at) FROM job_postings"
    ).fetchone()[0]
    
    hours_since_scrape = (datetime.datetime.now() - last_scrape).total_seconds() / 3600
    
    if hours_since_scrape > 30:
        issues.append(f"No scraping in {hours_since_scrape:.1f} hours")
    
    # Report issues
    if issues:
        send_alert("⚠️ Data Quality Issues:\n" + "\n".join(issues))
    
    return len(issues) == 0

10.3 A/B Testing Report Formats
Test with Jagoda:

Week 1: Send detailed report (full format from Section 7.1)
Week 2: Send condensed report (just company names + scores)
Week 3: Ask which format she prefers

Measure Success:

Does she forward leads to sales?
Does she click through to LinkedIn profiles?
Does she respond with feedback?


10.4 Success Metrics
After 4 weeks, evaluate:
MetricTargetActualHot leads per week3-5?Lead → Outreach conversion70%+?False positive rate<20%?Jagoda engagement (opens email)90%+?Sales team follow-up rate50%+?
If metrics are good → Discuss pricing
If metrics are meh → Iterate on scoring algorithm or data sources

11. Appendix
11.1 Tech Stack Summary
ComponentTechnologyWhyLanguagePython 3.10+Fast development, great librariesWeb ScrapingBeautifulSoup + Requests (Pracuj.pl)Playwright (NoFluffJobs)Simple + robustDatabaseSQLiteZero setup, portableEnrichmentClay API (optional)LinkedIn matching, headcountEmailSMTP or SendGridReliable deliverySchedulingCronBuilt-in, reliableHostingDigitalOcean / HetznerCheap, stableMonitoringPython logging + email alertsSimple, effective
11.2 Dependencies (requirements.txt)
txt# Web scraping
requests==2.31.0
beautifulsoup4==4.12.2
playwright==1.40.0

# Data processing
pandas==2.1.4

# Database
sqlite3  # Built into Python

# Email
sendgrid==6.11.0
python-dotenv==1.0.0

# Utilities
python-dateutil==2.8.2
11.3 Estimated Costs
MVP (Month 1):

Hosting: $0 (local machine)
Clay API: $0 (free trial credits from bootcamp)
Email: $0 (Gmail SMTP or SendGrid free tier)
Total: $0

Production (Month 2+):

VPS Hosting: $6/month (Hetzner)
Clay API: $149/month (if you exceed free tier)
SendGrid: $0 (free tier = 100 emails/day)
Total: ~$155/month

Revenue Potential:

Charge Jagoda: €300/month
Gross margin: €300 - $155 = ~€145/month (~48% margin)

If you sell to 5 clients: €1,500/month revenue, €725 profit

11.4 Questions & Answers
Q: What if job boards change their HTML structure?
A: Scrapers will break. Set up monitoring alerts to detect this quickly. Budget 2-4 hours/month for scraper maintenance.
Q: What if LinkedIn bans my account for scraping?
A: Use Clay API instead of direct scraping. Clay handles the scraping legally via their infrastructure.
Q: How do I handle companies with multiple job postings across different boards?
A: Deduplicate by (company_name, job_title, location). If the same role appears on Pracuj.pl and NoFluffJobs, only count it once.
Q: What if Jagoda's existing customer list changes?
A: Store it in the excluded_customers table. She can send updates via email, and you manually add them. Later, build a simple web form for her to manage it herself.
Q: Can I sell this to other companies?
A: Yes, but you'll need:

Multi-tenant database (separate data per customer)
Payment system (Stripe)
Customer onboarding flow
Support system

For now, focus on making it work for Jagoda. Productize later if successful.

END OF DOCUMENTATION
Next Steps:

Review this document
Ask any clarifying questions
Set up development environment
Start Day 1 build

Good luck! 🚀