"""Tests for the hr_alerter.db package.

All tests use an in-memory SQLite database (`:memory:`) so they run
quickly, require no filesystem access, and leave no artefacts behind.
"""

import datetime
import sqlite3

import pytest

from hr_alerter.db.manager import (
    get_connection,
    get_companies_with_postings,
    get_job_count,
    init_db,
    insert_jobs,
    insert_or_update_company,
    save_signal,
    save_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    """Yield an initialised in-memory database connection."""
    connection = get_connection(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _make_job(
    job_url: str,
    company: str = "Acme Sp. z o.o.",
    title: str = "HR Manager",
    source: str = "pracuj.pl",
    post_date: str | None = None,
    **overrides,
) -> dict:
    """Helper to create a job_posting_dict with sensible defaults."""
    return {
        "source": source,
        "job_url": job_url,
        "job_title": title,
        "company_name_raw": company,
        "location": "Warszawa",
        "post_date": post_date or datetime.date.today().isoformat(),
        "job_description": overrides.get("job_description"),
        "seniority_level": overrides.get("seniority_level"),
        "employment_type": overrides.get("employment_type", "full-time"),
    }


# ---------------------------------------------------------------------------
# Schema creation tests
# ---------------------------------------------------------------------------

class TestSchemaCreation:
    """Verify that init_db creates all expected tables and indexes."""

    EXPECTED_TABLES = [
        "job_postings",
        "companies",
        "contacts",
        "signals",
        "reports",
        "excluded_customers",
    ]

    def test_all_tables_exist(self, conn: sqlite3.Connection):
        """All 6 tables from the schema must be present."""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = sorted(row["name"] for row in rows)

        for expected in self.EXPECTED_TABLES:
            assert expected in table_names, f"Table '{expected}' not found"

    def test_indexes_exist(self, conn: sqlite3.Connection):
        """Key indexes from the schema must be present."""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {row["name"] for row in rows}

        expected_indexes = [
            "idx_company_name",
            "idx_post_date",
            "idx_company_id",
            "idx_name",
            "idx_icp",
            "idx_signal_date",
            "idx_lead_temperature",
            "idx_final_score",
            "idx_report_date",
        ]
        for expected in expected_indexes:
            assert expected in index_names, f"Index '{expected}' not found"

    def test_idempotent_init(self, conn: sqlite3.Connection):
        """Calling init_db twice must not raise."""
        init_db(conn)  # second call
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [row["name"] for row in rows]
        for expected in self.EXPECTED_TABLES:
            assert expected in table_names


# ---------------------------------------------------------------------------
# insert_jobs tests
# ---------------------------------------------------------------------------

class TestInsertJobs:
    """Verify insert_jobs behaviour including deduplication."""

    def test_insert_single_job(self, conn: sqlite3.Connection):
        jobs = [_make_job("https://example.com/job/1")]
        count = insert_jobs(conn, jobs)
        assert count == 1
        assert get_job_count(conn) == 1

    def test_insert_multiple_jobs(self, conn: sqlite3.Connection):
        jobs = [
            _make_job("https://example.com/job/1"),
            _make_job("https://example.com/job/2", company="Beta Corp"),
            _make_job("https://example.com/job/3", company="Gamma S.A."),
        ]
        count = insert_jobs(conn, jobs)
        assert count == 3
        assert get_job_count(conn) == 3

    def test_dedup_by_job_url(self, conn: sqlite3.Connection):
        """Duplicate job_url values must be ignored (INSERT OR IGNORE)."""
        jobs_batch_1 = [
            _make_job("https://example.com/job/1"),
            _make_job("https://example.com/job/2"),
        ]
        count_1 = insert_jobs(conn, jobs_batch_1)
        assert count_1 == 2

        # Second batch overlaps on job/1 and job/2, adds job/3
        jobs_batch_2 = [
            _make_job("https://example.com/job/1"),  # duplicate
            _make_job("https://example.com/job/2"),  # duplicate
            _make_job("https://example.com/job/3"),  # new
        ]
        count_2 = insert_jobs(conn, jobs_batch_2)
        assert count_2 == 1
        assert get_job_count(conn) == 3

    def test_insert_empty_list(self, conn: sqlite3.Connection):
        count = insert_jobs(conn, [])
        assert count == 0
        assert get_job_count(conn) == 0

    def test_default_post_date(self, conn: sqlite3.Connection):
        """If post_date is None, today's date should be used."""
        jobs = [_make_job("https://example.com/job/nodate", post_date=None)]
        insert_jobs(conn, jobs)
        row = conn.execute(
            "SELECT post_date FROM job_postings WHERE job_url = ?",
            ("https://example.com/job/nodate",),
        ).fetchone()
        assert row["post_date"] == datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# get_companies_with_postings tests
# ---------------------------------------------------------------------------

class TestGetCompaniesWithPostings:
    """Verify grouping and filtering of companies by posting count."""

    def test_returns_companies_above_threshold(self, conn: sqlite3.Connection):
        """Companies with >= min_postings in the window appear."""
        today = datetime.date.today().isoformat()
        jobs = [
            _make_job("https://example.com/a1", company="Alpha", post_date=today),
            _make_job("https://example.com/a2", company="Alpha", post_date=today),
            _make_job("https://example.com/a3", company="Alpha", post_date=today),
            _make_job("https://example.com/b1", company="Beta", post_date=today),
        ]
        insert_jobs(conn, jobs)

        results = get_companies_with_postings(conn, min_postings=2, days=30)
        names = [r["company_name_raw"] for r in results]

        assert "Alpha" in names
        assert "Beta" not in names

    def test_excludes_old_postings(self, conn: sqlite3.Connection):
        """Postings older than the window must not be counted."""
        today = datetime.date.today()
        old_date = (today - datetime.timedelta(days=60)).isoformat()
        recent_date = today.isoformat()

        jobs = [
            _make_job("https://example.com/old1", company="OldCo",
                       post_date=old_date),
            _make_job("https://example.com/old2", company="OldCo",
                       post_date=old_date),
            _make_job("https://example.com/new1", company="NewCo",
                       post_date=recent_date),
            _make_job("https://example.com/new2", company="NewCo",
                       post_date=recent_date),
        ]
        insert_jobs(conn, jobs)

        results = get_companies_with_postings(conn, min_postings=2, days=30)
        names = [r["company_name_raw"] for r in results]

        assert "NewCo" in names
        assert "OldCo" not in names

    def test_posting_count_value(self, conn: sqlite3.Connection):
        """The returned posting_count must equal the actual count."""
        today = datetime.date.today().isoformat()
        jobs = [
            _make_job(f"https://example.com/j{i}", company="CountCo",
                       post_date=today)
            for i in range(5)
        ]
        insert_jobs(conn, jobs)

        results = get_companies_with_postings(conn, min_postings=1, days=30)
        row = [r for r in results if r["company_name_raw"] == "CountCo"][0]
        assert row["posting_count"] == 5

    def test_empty_database(self, conn: sqlite3.Connection):
        """An empty database returns an empty list."""
        results = get_companies_with_postings(conn, min_postings=1, days=30)
        assert results == []


# ---------------------------------------------------------------------------
# insert_or_update_company tests
# ---------------------------------------------------------------------------

class TestInsertOrUpdateCompany:

    def test_insert_new_company(self, conn: sqlite3.Connection):
        cid = insert_or_update_company(conn, "Samsung Electronics Polska",
                                       industry="Technology")
        assert cid is not None
        row = conn.execute("SELECT * FROM companies WHERE id = ?",
                           (cid,)).fetchone()
        assert row["name_normalized"] == "Samsung Electronics Polska"
        assert row["industry"] == "Technology"

    def test_update_existing_company(self, conn: sqlite3.Connection):
        cid1 = insert_or_update_company(conn, "Samsung Electronics Polska",
                                        industry="Technology")
        cid2 = insert_or_update_company(conn, "Samsung Electronics Polska",
                                        headcount_poland=450)
        assert cid1 == cid2
        row = conn.execute("SELECT * FROM companies WHERE id = ?",
                           (cid1,)).fetchone()
        assert row["headcount_poland"] == 450
        # Original field should still be there
        assert row["industry"] == "Technology"


# ---------------------------------------------------------------------------
# save_signal / save_report tests
# ---------------------------------------------------------------------------

class TestSaveSignal:

    def test_save_and_retrieve(self, conn: sqlite3.Connection):
        cid = insert_or_update_company(conn, "TestCo")
        signal_id = save_signal(conn, {
            "company_id": cid,
            "signal_date": "2026-02-08",
            "signal_type": "hiring_velocity",
            "final_score": 83,
            "lead_temperature": "hot",
            "posting_count_7d": 3,
            "posting_count_30d": 4,
        })
        assert signal_id is not None
        row = conn.execute("SELECT * FROM signals WHERE id = ?",
                           (signal_id,)).fetchone()
        assert row["final_score"] == 83
        assert row["lead_temperature"] == "hot"


class TestSaveReport:

    def test_save_and_retrieve(self, conn: sqlite3.Connection):
        report_id = save_report(conn, {
            "report_date": "2026-02-08",
            "report_type": "weekly_digest",
            "recipient_email": "test@example.com",
            "hot_count": 3,
            "warm_count": 9,
            "email_subject": "Test Report",
        })
        assert report_id is not None
        row = conn.execute("SELECT * FROM reports WHERE id = ?",
                           (report_id,)).fetchone()
        assert row["recipient_email"] == "test@example.com"
        assert row["hot_count"] == 3


# ---------------------------------------------------------------------------
# get_job_count tests
# ---------------------------------------------------------------------------

class TestGetJobCount:

    def test_zero_on_empty(self, conn: sqlite3.Connection):
        assert get_job_count(conn) == 0

    def test_correct_after_inserts(self, conn: sqlite3.Connection):
        jobs = [_make_job(f"https://example.com/{i}") for i in range(7)]
        insert_jobs(conn, jobs)
        assert get_job_count(conn) == 7
