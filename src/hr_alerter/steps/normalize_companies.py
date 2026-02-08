"""pypyr step: normalize raw company names and link to the companies table.

Reads distinct ``company_name_raw`` values from ``job_postings``, applies
``normalize_company_name`` from :mod:`hr_alerter.scrapers.utils`, inserts
normalized names into the ``companies`` table (``INSERT OR IGNORE``), and
back-fills the ``company_id`` foreign key on every ``job_postings`` row.
"""

import logging
import sqlite3

from hr_alerter.scrapers.utils import normalize_company_name

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """pypyr entry-point.

    Expects ``context['conn']`` to be an open :class:`sqlite3.Connection`.
    """
    conn: sqlite3.Connection = context["conn"]

    # 1. Fetch all distinct raw company names from job_postings.
    rows = conn.execute(
        "SELECT DISTINCT company_name_raw FROM job_postings"
    ).fetchall()

    inserted = 0
    for row in rows:
        raw_name = row["company_name_raw"]
        normalized = normalize_company_name(raw_name)
        if not normalized:
            continue

        conn.execute(
            "INSERT OR IGNORE INTO companies (name_normalized) VALUES (?)",
            (normalized,),
        )
        inserted += 1

    conn.commit()
    logger.info(
        "Processed %d raw company names (%d INSERT OR IGNORE operations)",
        len(rows), inserted,
    )

    # 2. Link job_postings rows to their companies via Python-side
    #    normalization (SQLite cannot call Python functions in SQL).
    unlinked = conn.execute(
        "SELECT id, company_name_raw FROM job_postings WHERE company_id IS NULL"
    ).fetchall()

    linked_count = 0
    for posting in unlinked:
        normalized = normalize_company_name(posting["company_name_raw"])
        if not normalized:
            continue

        company_row = conn.execute(
            "SELECT id FROM companies WHERE name_normalized = ?",
            (normalized,),
        ).fetchone()

        if company_row:
            conn.execute(
                "UPDATE job_postings SET company_id = ? WHERE id = ?",
                (company_row["id"], posting["id"]),
            )
            linked_count += 1

    conn.commit()
    logger.info("Linked %d job postings to companies", linked_count)
