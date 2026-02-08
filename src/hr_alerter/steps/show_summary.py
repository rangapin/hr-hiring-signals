"""pypyr step: show_summary

Prints a summary of the current database state including total job count,
new jobs from this run, and the top 15 companies by posting count.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """Print a summary of scraping results and close the DB connection.

    Expects the following keys in *context*:
        conn           -- open sqlite3 connection
        inserted_count -- (optional) number of new jobs inserted this run
    """
    conn = context.get("conn")
    if conn is None:
        logger.warning("show_summary: no database connection in context")
        return

    try:
        # Total jobs in DB
        total_jobs = conn.execute(
            "SELECT COUNT(*) FROM job_postings"
        ).fetchone()[0]

        # New jobs this run (set by scrape steps; 0 if missing)
        inserted_count = context.get("inserted_count", 0)

        # Top 15 companies by posting count
        rows = conn.execute(
            """
            SELECT company_name_raw, COUNT(*) AS cnt
            FROM job_postings
            GROUP BY company_name_raw
            ORDER BY cnt DESC
            LIMIT 15
            """
        ).fetchall()

        # Build output
        separator = "-" * 55
        print(separator)
        print(f"  Total jobs in database : {total_jobs}")
        print(f"  New jobs this run      : {inserted_count}")
        print(separator)
        print("  Top 15 companies by posting count:")
        print(f"  {'#':<4} {'Company':<35} {'Posts':>6}")
        print(f"  {'---':<4} {'---':<35} {'---':>6}")
        for idx, row in enumerate(rows, start=1):
            company = row[0] if row[0] else "(unknown)"
            count = row[1]
            # Truncate long names
            if len(company) > 33:
                company = company[:30] + "..."
            print(f"  {idx:<4} {company:<35} {count:>6}")
        print(separator)

    except Exception as exc:
        logger.error("show_summary failed: %s", exc)
    finally:
        conn.close()
        logger.info("Database connection closed by show_summary step.")
