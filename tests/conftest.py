"""Shared pytest fixtures for the hr-alerter test suite.

Provides:
    tmp_db      -- in-memory SQLite connection with full schema applied
    sample_jobs -- list of 10 realistic job_posting_dicts
    sample_company -- inserts a company into tmp_db with known data for scoring
"""

import datetime
import pathlib
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# tmp_db fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db():
    """Create an in-memory SQLite connection with the full schema applied.

    Yields the connection and closes it after the test.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    schema_path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "src" / "hr_alerter" / "db" / "schema.sql"
    )
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)

    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# sample_jobs fixture
# ---------------------------------------------------------------------------

def _make_sample_job(
    index: int,
    company: str,
    title: str,
    source: str = "pracuj.pl",
    days_ago: int = 0,
    seniority: str | None = None,
    location: str = "Warszawa",
    description: str | None = None,
) -> dict:
    """Build a single job_posting_dict for fixture use."""
    post_date = (
        datetime.date.today() - datetime.timedelta(days=days_ago)
    ).isoformat()
    return {
        "source": source,
        "job_url": f"https://example.com/jobs/{index}",
        "job_title": title,
        "company_name_raw": company,
        "location": location,
        "post_date": post_date,
        "job_description": description,
        "seniority_level": seniority,
        "employment_type": "full-time",
    }


@pytest.fixture()
def sample_jobs() -> list[dict]:
    """Return a list of 10 realistic job_posting_dicts.

    Mix of companies, titles, dates, and sources.
    """
    return [
        _make_sample_job(
            1, "Samsung Electronics Polska Sp. z o.o.", "HR Director",
            days_ago=2, seniority="director",
            description="Lead wellbeing and EAP programme.",
        ),
        _make_sample_job(
            2, "Samsung Electronics Polska Sp. z o.o.", "HR Manager",
            days_ago=5, seniority="mid", location="Krakow",
        ),
        _make_sample_job(
            3, "Samsung Electronics Polska Sp. z o.o.", "Senior Recruiter",
            days_ago=8, seniority="senior",
        ),
        _make_sample_job(
            4, "Allegro S.A.", "HR Business Partner",
            days_ago=3, seniority="mid",
        ),
        _make_sample_job(
            5, "Allegro S.A.", "People & Culture Lead",
            days_ago=10, seniority="mid",
        ),
        _make_sample_job(
            6, "Maly Startup Sp. z o.o.", "HR Generalist",
            source="nofluffjobs", days_ago=10,
        ),
        _make_sample_job(
            7, "Maly Startup Sp. z o.o.", "HR Coordinator",
            source="nofluffjobs", days_ago=12,
        ),
        _make_sample_job(
            8, "Google Poland", "Talent Acquisition Manager",
            days_ago=1, seniority="mid", location="Wroclaw",
        ),
        _make_sample_job(
            9, "Google Poland", "Senior HR Analyst",
            days_ago=4, seniority="senior",
        ),
        _make_sample_job(
            10, "ING Bank Slaski S.A.", "Junior HR Specialist",
            days_ago=6, seniority="junior", location="Katowice",
        ),
    ]


# ---------------------------------------------------------------------------
# sample_company fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_company(tmp_db):
    """Insert a company into tmp_db with known data for scoring tests.

    Creates a company 'TestCorp International' with headcount_poland=500,
    is_icp_match=True, and 3 linked job postings (1 director, 1 senior,
    1 mid) with varying dates and descriptions.

    Returns a dict with 'company_id' and 'conn' keys.
    """
    conn = tmp_db

    conn.execute(
        "INSERT INTO companies (name_normalized, headcount_poland, is_icp_match) "
        "VALUES ('TestCorp International', 500, 1)"
    )
    company_id = conn.execute(
        "SELECT id FROM companies WHERE name_normalized = 'TestCorp International'"
    ).fetchone()["id"]

    today = datetime.date.today()

    # Posting 1: director, 1 day ago, wellbeing keyword
    conn.execute(
        "INSERT INTO job_postings "
        "(source, job_url, job_title, company_name_raw, company_id, "
        " location, post_date, seniority_level, job_description, is_relevant) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            "pracuj.pl",
            "https://example.com/testcorp/1",
            "HR Director",
            "TestCorp International Sp. z o.o.",
            company_id,
            "Warszawa",
            (today - datetime.timedelta(days=1)).isoformat(),
            "director",
            "Leading wellbeing and employee assistance programme (EAP).",
        ),
    )

    # Posting 2: senior, 4 days ago
    conn.execute(
        "INSERT INTO job_postings "
        "(source, job_url, job_title, company_name_raw, company_id, "
        " location, post_date, seniority_level, job_description, is_relevant) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            "pracuj.pl",
            "https://example.com/testcorp/2",
            "Senior HR Business Partner",
            "TestCorp International Sp. z o.o.",
            company_id,
            "Krakow",
            (today - datetime.timedelta(days=4)).isoformat(),
            "senior",
            "Manage employer branding and kultura organizacyjna.",
        ),
    )

    # Posting 3: mid, 9 days ago
    conn.execute(
        "INSERT INTO job_postings "
        "(source, job_url, job_title, company_name_raw, company_id, "
        " location, post_date, seniority_level, job_description, is_relevant) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            "pracuj.pl",
            "https://example.com/testcorp/3",
            "HR Manager",
            "TestCorp International Sp. z o.o.",
            company_id,
            "Warszawa",
            (today - datetime.timedelta(days=9)).isoformat(),
            "mid",
            "Support HR operations and team management.",
        ),
    )

    conn.commit()

    return {"company_id": company_id, "conn": conn}
