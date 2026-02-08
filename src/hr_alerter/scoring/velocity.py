"""Velocity scoring dimension for the hr-alerter project.

Scores companies based on their HR hiring frequency across three
time windows (7-day, 30-day, 90-day).  Maximum score: 40 points.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def calculate_velocity_score(conn: sqlite3.Connection, company_id: int) -> int:
    """Calculate velocity score based on hiring frequency.

    Thresholds (evaluated top-down, first match wins):
        - 7-day count >= 3  -> 40 (ultra hot -- hiring NOW)
        - 30-day count >= 5 -> 35 (very hot)
        - 30-day count >= 3 -> 30 (hot)
        - 30-day count >= 2 -> 20 (warm)
        - 90-day count >= 2 -> 10 (lukewarm)
        - else              ->  0 (cold)

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` to score.

    Returns:
        An integer score between 0 and 40.
    """
    sql = """
        SELECT
            COUNT(CASE WHEN post_date >= date('now', '-7 days') THEN 1 END)
                AS count_7d,
            COUNT(CASE WHEN post_date >= date('now', '-30 days') THEN 1 END)
                AS count_30d,
            COUNT(CASE WHEN post_date >= date('now', '-90 days') THEN 1 END)
                AS count_90d
        FROM job_postings
        WHERE company_id = :company_id
          AND is_relevant = 1
    """
    row = conn.execute(sql, {"company_id": company_id}).fetchone()

    if row is None:
        return 0

    count_7d = row["count_7d"]
    count_30d = row["count_30d"]
    count_90d = row["count_90d"]

    if count_7d >= 3:
        score = 40
    elif count_30d >= 5:
        score = 35
    elif count_30d >= 3:
        score = 30
    elif count_30d >= 2:
        score = 20
    elif count_90d >= 2:
        score = 10
    else:
        score = 0

    logger.debug(
        "Velocity score for company_id=%d: %d (7d=%d, 30d=%d, 90d=%d)",
        company_id, score, count_7d, count_30d, count_90d,
    )
    return score
