"""Seniority-mix scoring dimension for the hr-alerter project.

Scores companies based on the seniority levels of their recent HR
job postings.  Maximum score: 20 points.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def calculate_seniority_score(conn: sqlite3.Connection, company_id: int) -> int:
    """Calculate seniority score based on role levels in recent postings.

    Points awarded (additive, capped at 20):
        - has_director (director or c-level)  -> +15
        - has_senior                          -> +5
        - multiple_levels (2+ distinct)       -> +5

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` to score.

    Returns:
        An integer score between 0 and 20.
    """
    sql = """
        SELECT seniority_level
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', '-30 days')
          AND is_relevant = 1
          AND seniority_level IS NOT NULL
    """
    rows = conn.execute(sql, {"company_id": company_id}).fetchall()

    if not rows:
        return 0

    levels = {row["seniority_level"] for row in rows}

    has_director = bool(levels & {"director", "c-level"})
    has_senior = "senior" in levels
    multiple_levels = len(levels) >= 2

    score = 0
    if has_director:
        score += 15
    if has_senior:
        score += 5
    if multiple_levels:
        score += 5

    score = min(score, 20)

    logger.debug(
        "Seniority score for company_id=%d: %d (levels=%s)",
        company_id, score, levels,
    )
    return score
