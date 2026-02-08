"""Database manager for the hr-alerter project.

Provides connection management, schema initialization, and query helpers
for the SQLite database. All functions take a connection object as their
first parameter and do not manage global state.
"""

import datetime
import logging
import pathlib
import sqlite3

logger = logging.getLogger(__name__)


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with Row factory enabled.

    Args:
        db_path: Filesystem path to the SQLite database file, or ":memory:"
                 for an in-memory database.

    Returns:
        A ``sqlite3.Connection`` configured with ``sqlite3.Row`` as
        ``row_factory`` and foreign-key enforcement turned on.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes by executing ``schema.sql``.

    The SQL file is located relative to this module using ``__file__``
    so it works regardless of the current working directory.

    Args:
        conn: An open SQLite connection.
    """
    schema_path = pathlib.Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    logger.info("Database schema initialized from %s", schema_path)


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> int:
    """Insert job posting dicts into the ``job_postings`` table.

    Duplicates (identified by ``job_url``) are silently ignored via
    ``INSERT OR IGNORE``.

    Each dict is expected to follow the ``job_posting_dict`` contract
    defined in ``team-config.json``.

    Args:
        conn: An open SQLite connection.
        jobs: A list of dicts, each containing at minimum the keys
              ``source``, ``job_url``, ``job_title``, ``company_name_raw``.

    Returns:
        The number of rows actually inserted (excluding ignored duplicates).
    """
    if not jobs:
        return 0

    sql = """
        INSERT OR IGNORE INTO job_postings
            (source, job_url, job_title, company_name_raw, location,
             post_date, job_description, seniority_level, employment_type)
        VALUES
            (:source, :job_url, :job_title, :company_name_raw, :location,
             :post_date, :job_description, :seniority_level, :employment_type)
    """

    count_before = _row_count(conn, "job_postings")

    for job in jobs:
        params = {
            "source": job.get("source"),
            "job_url": job.get("job_url"),
            "job_title": job.get("job_title"),
            "company_name_raw": job.get("company_name_raw"),
            "location": job.get("location"),
            "post_date": job.get("post_date") or datetime.date.today().isoformat(),
            "job_description": job.get("job_description"),
            "seniority_level": job.get("seniority_level"),
            "employment_type": job.get("employment_type"),
        }
        conn.execute(sql, params)

    conn.commit()

    count_after = _row_count(conn, "job_postings")
    inserted = count_after - count_before
    logger.info("Inserted %d new job postings (%d duplicates skipped)",
                inserted, len(jobs) - inserted)
    return inserted


def insert_or_update_company(
    conn: sqlite3.Connection,
    name_normalized: str,
    **fields,
) -> int:
    """Insert a new company or update an existing one (matched by name).

    Args:
        conn: An open SQLite connection.
        name_normalized: The normalized company name (unique key).
        **fields: Optional keyword arguments that map to columns in the
                  ``companies`` table, e.g. ``linkedin_url``,
                  ``headcount_poland``, ``industry``, ``is_icp_match``.

    Returns:
        The ``id`` of the inserted or updated company row.
    """
    existing = conn.execute(
        "SELECT id FROM companies WHERE name_normalized = ?",
        (name_normalized,),
    ).fetchone()

    if existing is not None:
        if fields:
            set_clause = ", ".join(f"{k} = :{k}" for k in fields)
            sql = f"UPDATE companies SET {set_clause} WHERE name_normalized = :name_normalized"
            params = {**fields, "name_normalized": name_normalized}
            conn.execute(sql, params)
            conn.commit()
        return existing["id"]

    columns = ["name_normalized"] + list(fields.keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    col_names = ", ".join(columns)
    sql = f"INSERT INTO companies ({col_names}) VALUES ({placeholders})"
    params = {"name_normalized": name_normalized, **fields}
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.lastrowid


def get_companies_with_postings(
    conn: sqlite3.Connection,
    min_postings: int = 2,
    days: int = 30,
) -> list:
    """Return companies that have at least *min_postings* in the last *days*.

    Groups ``job_postings`` by ``company_name_raw`` and counts rows whose
    ``post_date`` falls within the window.

    Args:
        conn: An open SQLite connection.
        min_postings: Minimum number of postings to include a company.
        days: Look-back window in days.

    Returns:
        A list of ``sqlite3.Row`` objects with columns
        ``company_name_raw`` and ``posting_count``.
    """
    sql = """
        SELECT company_name_raw, COUNT(*) AS posting_count
        FROM job_postings
        WHERE post_date >= date('now', :days_offset)
          AND is_relevant = 1
        GROUP BY company_name_raw
        HAVING COUNT(*) >= :min_postings
        ORDER BY posting_count DESC
    """
    params = {
        "days_offset": f"-{days} days",
        "min_postings": min_postings,
    }
    return conn.execute(sql, params).fetchall()


def get_postings_for_company(
    conn: sqlite3.Connection,
    company_id: int,
    days: int = 30,
) -> list:
    """Return recent job postings for a given company.

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` foreign-key value.
        days: Look-back window in days.

    Returns:
        A list of ``sqlite3.Row`` objects representing matching
        ``job_postings`` rows.
    """
    sql = """
        SELECT *
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', :days_offset)
          AND is_relevant = 1
        ORDER BY post_date DESC
    """
    params = {
        "company_id": company_id,
        "days_offset": f"-{days} days",
    }
    return conn.execute(sql, params).fetchall()


def get_hot_companies(
    conn: sqlite3.Connection,
    min_score: int = 50,
) -> list:
    """Return companies whose latest signal meets or exceeds *min_score*.

    Joins ``signals`` with ``companies`` and excludes existing customers.

    Args:
        conn: An open SQLite connection.
        min_score: Minimum ``final_score`` to include.

    Returns:
        A list of ``sqlite3.Row`` objects with signal and company data.
    """
    sql = """
        SELECT
            c.id AS company_id,
            c.name_normalized,
            c.linkedin_url,
            c.headcount_poland,
            s.posting_count_7d,
            s.posting_count_30d,
            s.final_score,
            s.lead_temperature,
            s.has_director_role,
            s.has_wellbeing_keywords,
            s.multi_city_expansion,
            s.signal_date
        FROM signals s
        JOIN companies c ON s.company_id = c.id
        WHERE s.final_score >= :min_score
          AND c.is_existing_customer = 0
          AND s.signal_date >= date('now', '-7 days')
        ORDER BY s.final_score DESC
    """
    return conn.execute(sql, {"min_score": min_score}).fetchall()


def save_signal(conn: sqlite3.Connection, signal_dict: dict) -> int:
    """Persist a scoring signal to the ``signals`` table.

    Args:
        conn: An open SQLite connection.
        signal_dict: A dict whose keys map to ``signals`` table columns.
                     Required keys: ``company_id``, ``signal_date``,
                     ``signal_type``.

    Returns:
        The ``id`` of the newly inserted signal row.
    """
    sql = """
        INSERT INTO signals
            (company_id, signal_date, signal_type, signal_strength,
             velocity_score, posting_count_7d, posting_count_30d,
             posting_count_90d, has_director_role, has_wellbeing_keywords,
             multi_city_expansion, final_score, lead_temperature)
        VALUES
            (:company_id, :signal_date, :signal_type, :signal_strength,
             :velocity_score, :posting_count_7d, :posting_count_30d,
             :posting_count_90d, :has_director_role, :has_wellbeing_keywords,
             :multi_city_expansion, :final_score, :lead_temperature)
    """
    params = {
        "company_id": signal_dict.get("company_id"),
        "signal_date": signal_dict.get("signal_date",
                                       datetime.date.today().isoformat()),
        "signal_type": signal_dict.get("signal_type", "hiring_velocity"),
        "signal_strength": signal_dict.get("signal_strength"),
        "velocity_score": signal_dict.get("velocity_score"),
        "posting_count_7d": signal_dict.get("posting_count_7d"),
        "posting_count_30d": signal_dict.get("posting_count_30d"),
        "posting_count_90d": signal_dict.get("posting_count_90d"),
        "has_director_role": signal_dict.get("has_director_role"),
        "has_wellbeing_keywords": signal_dict.get("has_wellbeing_keywords"),
        "multi_city_expansion": signal_dict.get("multi_city_expansion"),
        "final_score": signal_dict.get("final_score"),
        "lead_temperature": signal_dict.get("lead_temperature"),
    }
    cursor = conn.execute(sql, params)
    conn.commit()
    logger.info("Saved signal for company_id=%s (score=%s, temp=%s)",
                params["company_id"], params["final_score"],
                params["lead_temperature"])
    return cursor.lastrowid


def save_report(conn: sqlite3.Connection, report_dict: dict) -> int:
    """Persist a report record to the ``reports`` table.

    Args:
        conn: An open SQLite connection.
        report_dict: A dict whose keys map to ``reports`` table columns.
                     Required keys: ``report_date``, ``report_type``,
                     ``recipient_email``.

    Returns:
        The ``id`` of the newly inserted report row.
    """
    sql = """
        INSERT INTO reports
            (report_date, report_type, recipient_email, hot_count,
             warm_count, sent_at, email_subject, email_body)
        VALUES
            (:report_date, :report_type, :recipient_email, :hot_count,
             :warm_count, :sent_at, :email_subject, :email_body)
    """
    params = {
        "report_date": report_dict.get("report_date",
                                       datetime.date.today().isoformat()),
        "report_type": report_dict.get("report_type", "weekly_digest"),
        "recipient_email": report_dict.get("recipient_email"),
        "hot_count": report_dict.get("hot_count"),
        "warm_count": report_dict.get("warm_count"),
        "sent_at": report_dict.get("sent_at"),
        "email_subject": report_dict.get("email_subject"),
        "email_body": report_dict.get("email_body"),
    }
    cursor = conn.execute(sql, params)
    conn.commit()
    logger.info("Saved report id=%d (type=%s, date=%s)",
                cursor.lastrowid, params["report_type"],
                params["report_date"])
    return cursor.lastrowid


def get_job_count(conn: sqlite3.Connection) -> int:
    """Return the total number of rows in the ``job_postings`` table.

    Args:
        conn: An open SQLite connection.

    Returns:
        An integer count of all job postings.
    """
    row = conn.execute("SELECT COUNT(*) AS cnt FROM job_postings").fetchone()
    return row["cnt"]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _row_count(conn: sqlite3.Connection, table: str) -> int:
    """Return the row count of *table* (internal helper)."""
    row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
    return row["cnt"]
