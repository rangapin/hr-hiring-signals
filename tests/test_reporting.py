"""Tests for the reporting sub-package (composer + sender).

All database tests use an in-memory SQLite database seeded with
realistic signal and company data.  No network calls are made.
"""

import datetime
import logging
import os
import sqlite3
import pathlib

import pytest

from hr_alerter.db.manager import get_connection, init_db, save_signal
from hr_alerter.reporting.composer import compose_weekly_report
from hr_alerter.reporting.sender import send_email


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_conn():
    """In-memory SQLite database with schema applied."""
    conn = get_connection(":memory:")
    init_db(conn)
    yield conn
    conn.close()


def _seed_company(conn, name, headcount_poland=None, is_icp_match=False):
    """Insert a company row and return its id."""
    cursor = conn.execute(
        "INSERT INTO companies (name_normalized, headcount_poland, is_icp_match) "
        "VALUES (?, ?, ?)",
        (name, headcount_poland, int(is_icp_match)),
    )
    conn.commit()
    return cursor.lastrowid


def _seed_posting(conn, company_id, title, days_ago=1, description=None):
    """Insert a job posting for the given company."""
    post_date = (
        datetime.date.today() - datetime.timedelta(days=days_ago)
    ).isoformat()
    job_url = f"https://example.com/jobs/{company_id}/{title.replace(' ', '-')}-{days_ago}"
    conn.execute(
        "INSERT INTO job_postings "
        "(source, job_url, job_title, company_name_raw, company_id, "
        " post_date, job_description, seniority_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "pracuj.pl",
            job_url,
            title,
            f"Company {company_id} Raw",
            company_id,
            post_date,
            description,
            None,
        ),
    )
    conn.commit()


def _seed_signal(conn, company_id, temperature, score, posting_count_30d=3,
                 has_director=False, has_wellbeing=False, multi_city=False):
    """Insert a signal for the given company."""
    save_signal(conn, {
        "company_id": company_id,
        "signal_date": datetime.date.today().isoformat(),
        "signal_type": "hiring_velocity",
        "signal_strength": score,
        "velocity_score": 30,
        "posting_count_7d": 2,
        "posting_count_30d": posting_count_30d,
        "posting_count_90d": posting_count_30d + 1,
        "has_director_role": has_director,
        "has_wellbeing_keywords": has_wellbeing,
        "multi_city_expansion": multi_city,
        "final_score": score,
        "lead_temperature": temperature,
    })


# ---------------------------------------------------------------------------
# test_compose_weekly_report
# ---------------------------------------------------------------------------

class TestComposeWeeklyReport:
    """Tests for compose_weekly_report()."""

    def test_empty_database(self, db_conn):
        """Report on an empty database should produce valid output."""
        report = compose_weekly_report(db_conn)

        assert isinstance(report["subject"], str)
        assert isinstance(report["html_body"], str)
        assert report["hot_count"] == 0
        assert report["warm_count"] == 0

    def test_hot_and_warm_signals(self, db_conn):
        """Seed hot and warm signals and verify they appear in the report."""
        # Create two companies
        hot_id = _seed_company(db_conn, "Samsung Electronics Polska", 450, True)
        warm_id = _seed_company(db_conn, "Allegro", 1200, True)

        # Seed postings for the hot company
        _seed_posting(db_conn, hot_id, "HR Director", days_ago=2)
        _seed_posting(db_conn, hot_id, "Wellbeing Coordinator", days_ago=5)
        _seed_posting(db_conn, hot_id, "HR Manager", days_ago=12)

        # Seed postings for the warm company
        _seed_posting(db_conn, warm_id, "HR Business Partner", days_ago=3)
        _seed_posting(db_conn, warm_id, "People & Culture Lead", days_ago=10)

        # Seed signals
        _seed_signal(db_conn, hot_id, "hot", 83, posting_count_30d=3,
                     has_director=True, has_wellbeing=True)
        _seed_signal(db_conn, warm_id, "warm", 60, posting_count_30d=2)

        report = compose_weekly_report(db_conn)

        assert report["hot_count"] == 1
        assert report["warm_count"] == 1
        assert "Samsung Electronics Polska" in report["html_body"]
        assert "Allegro" in report["html_body"]

    def test_company_names_in_html(self, db_conn):
        """Company names must appear in the rendered HTML body."""
        cid = _seed_company(db_conn, "TestCorp International")
        _seed_posting(db_conn, cid, "HR Manager", days_ago=1)
        _seed_signal(db_conn, cid, "hot", 80, posting_count_30d=4)

        report = compose_weekly_report(db_conn)
        assert "TestCorp International" in report["html_body"]

    def test_existing_customer_excluded(self, db_conn):
        """Existing customers should not appear in the report."""
        cid = _seed_company(db_conn, "ExistingClient")
        db_conn.execute(
            "UPDATE companies SET is_existing_customer = 1 WHERE id = ?",
            (cid,),
        )
        db_conn.commit()
        _seed_signal(db_conn, cid, "hot", 90)

        report = compose_weekly_report(db_conn)
        assert report["hot_count"] == 0
        assert "ExistingClient" not in report["html_body"]


# ---------------------------------------------------------------------------
# test_subject_format
# ---------------------------------------------------------------------------

class TestSubjectFormat:
    """Tests for the email subject line format."""

    def test_subject_pattern(self, db_conn):
        """Subject must match 'X Companies ... | Polish Job Market Alerter'."""
        cid = _seed_company(db_conn, "Acme Corp")
        _seed_signal(db_conn, cid, "hot", 85)

        report = compose_weekly_report(db_conn)
        subject = report["subject"]

        assert "Companies Scaling HR Teams This Week" in subject
        assert "Polish Job Market Alerter" in subject
        assert subject.startswith("1 ")  # one company

    def test_subject_count_matches(self, db_conn):
        """Subject count should equal hot + warm."""
        c1 = _seed_company(db_conn, "CompanyA")
        c2 = _seed_company(db_conn, "CompanyB")
        c3 = _seed_company(db_conn, "CompanyC")
        _seed_signal(db_conn, c1, "hot", 85)
        _seed_signal(db_conn, c2, "hot", 80)
        _seed_signal(db_conn, c3, "warm", 55)

        report = compose_weekly_report(db_conn)
        assert report["subject"].startswith("3 ")

    def test_zero_companies_subject(self, db_conn):
        """Subject should show 0 when no signals exist."""
        report = compose_weekly_report(db_conn)
        assert report["subject"].startswith("0 ")


# ---------------------------------------------------------------------------
# test_send_email_missing_creds
# ---------------------------------------------------------------------------

class TestSendEmailMissingCreds:
    """Tests for send_email() when SMTP credentials are not set."""

    def test_returns_false_no_creds(self, monkeypatch):
        """send_email should return False when SMTP vars are unset."""
        monkeypatch.delenv("SMTP_EMAIL", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        result = send_email("test@example.com", "Subject", "<p>Body</p>")
        assert result is False

    def test_logs_warning_no_creds(self, monkeypatch, caplog):
        """send_email should log a warning when SMTP vars are unset."""
        monkeypatch.delenv("SMTP_EMAIL", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        with caplog.at_level(logging.WARNING):
            send_email("test@example.com", "Subject", "<p>Body</p>")

        assert any("SMTP" in msg for msg in caplog.messages)

    def test_returns_false_empty_recipient(self, monkeypatch):
        """send_email should return False for an empty recipient."""
        monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "password123")

        result = send_email("", "Subject", "<p>Body</p>")
        assert result is False

    def test_returns_false_partial_creds(self, monkeypatch):
        """send_email should return False if only SMTP_EMAIL is set."""
        monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        result = send_email("test@example.com", "Subject", "<p>Body</p>")
        assert result is False


# ---------------------------------------------------------------------------
# test_template_renders
# ---------------------------------------------------------------------------

class TestTemplateRenders:
    """Tests that the HTML template renders expected sections."""

    def test_template_file_exists(self):
        """The weekly_report.html template file must exist."""
        template_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "hr_alerter" / "reporting" / "templates"
            / "weekly_report.html"
        )
        assert template_path.exists(), f"Template not found at {template_path}"

    def test_hot_signals_section(self, db_conn):
        """Rendered HTML should contain the HOT SIGNALS heading."""
        report = compose_weekly_report(db_conn)
        assert "HOT SIGNALS" in report["html_body"]

    def test_warm_signals_section(self, db_conn):
        """Rendered HTML should contain the WARM SIGNALS heading."""
        report = compose_weekly_report(db_conn)
        assert "WARM SIGNALS" in report["html_body"]

    def test_stats_section(self, db_conn):
        """Rendered HTML should contain the stats section."""
        report = compose_weekly_report(db_conn)
        html = report["html_body"]
        assert "This Week" in html
        assert "Total HR postings monitored" in html
        assert "Hot signals" in html
        assert "Warm signals" in html

    def test_header_present(self, db_conn):
        """Rendered HTML should contain the report header."""
        report = compose_weekly_report(db_conn)
        assert "Weekly HR Hiring Report" in report["html_body"]

    def test_score_displayed(self, db_conn):
        """Score should appear as 'X/100' in the report."""
        cid = _seed_company(db_conn, "ScoreTestCorp")
        _seed_signal(db_conn, cid, "hot", 92)

        report = compose_weekly_report(db_conn)
        assert "92/100" in report["html_body"]

    def test_why_now_for_hot(self, db_conn):
        """Hot signals should include a 'Why Now' blurb."""
        cid = _seed_company(db_conn, "WhyNowCorp")
        _seed_signal(db_conn, cid, "hot", 78, has_director=True)

        report = compose_weekly_report(db_conn)
        assert "Why Now" in report["html_body"]

    def test_posting_count_in_stats(self, db_conn):
        """Seeded postings should show up in total postings stat."""
        cid = _seed_company(db_conn, "StatsCorp")
        _seed_posting(db_conn, cid, "HR Lead", days_ago=1)
        _seed_posting(db_conn, cid, "HR Specialist", days_ago=2)
        _seed_signal(db_conn, cid, "warm", 55)

        report = compose_weekly_report(db_conn)
        # The stats section should reflect the 2 postings
        assert "Total HR postings monitored" in report["html_body"]
