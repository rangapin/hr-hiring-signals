"""Recency scoring dimension for the hr-alerter project.

Scores companies based on how recently they posted an HR role.
Fresher signals receive higher scores.  Maximum score: 10 points.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def calculate_recency_score(conn: sqlite3.Connection, company_id: int) -> int:
    """Calculate recency score from the most recent posting date.

    Thresholds (first match wins):
        - <= 3 days  -> 10
        - <= 7 days  ->  8
        - <= 14 days ->  5
        - <= 30 days ->  3
        - else       ->  0

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` to score.

    Returns:
        An integer score between 0 and 10.
    """
    row = conn.execute(
        """
        SELECT MAX(post_date) AS latest_post_date
        FROM job_postings
        WHERE company_id = :company_id
          AND is_relevant = 1
        """,
        {"company_id": company_id},
    ).fetchone()

    if row is None or row["latest_post_date"] is None:
        return 0

    # Use SQLite to compute the number of days between now and the latest post.
    days_row = conn.execute(
        """
        SELECT CAST(julianday('now') - julianday(:latest) AS INTEGER) AS days_ago
        """,
        {"latest": row["latest_post_date"]},
    ).fetchone()

    days_ago = days_row["days_ago"] if days_row else 999

    if days_ago <= 3:
        score = 10
    elif days_ago <= 7:
        score = 8
    elif days_ago <= 14:
        score = 5
    elif days_ago <= 30:
        score = 3
    else:
        score = 0

    logger.debug(
        "Recency score for company_id=%d: %d (days_ago=%d)",
        company_id, score, days_ago,
    )
    return score
