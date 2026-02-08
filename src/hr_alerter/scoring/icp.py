"""ICP (Ideal Customer Profile) fit scoring dimension for the hr-alerter project.

Scores companies based on headcount in Poland and whether their job
titles match Lyra Polska's target persona list.  Maximum score: 20 points.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Job titles that indicate strong ICP alignment with Lyra Polska.
TARGET_TITLES: list[str] = [
    "HR Director",
    "People & Culture",
    "Wellbeing",
    "Employee Experience",
    "CHRO",
    "CPO",
    "HR Business Partner",
    "Culture and Engagement",
]


def calculate_icp_score(conn: sqlite3.Connection, company_id: int) -> int:
    """Calculate ICP fit score for a company.

    Points awarded (additive, capped at 20):
        - headcount_poland 200-5000   -> +15 (perfect fit)
        - headcount_poland 5001-10000 -> +10 (acceptable for global contracts)
        - 2+ postings with target title matches -> +5

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` to score.

    Returns:
        An integer score between 0 and 20.
    """
    # --- Headcount component ---
    company_row = conn.execute(
        "SELECT headcount_poland FROM companies WHERE id = :company_id",
        {"company_id": company_id},
    ).fetchone()

    score = 0

    if company_row and company_row["headcount_poland"] is not None:
        headcount = company_row["headcount_poland"]
        if 200 <= headcount <= 5000:
            score += 15
        elif 5001 <= headcount <= 10000:
            score += 10

    # --- Title-match component ---
    postings = conn.execute(
        """
        SELECT job_title
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', '-30 days')
          AND is_relevant = 1
        """,
        {"company_id": company_id},
    ).fetchall()

    matching_count = 0
    for posting in postings:
        title = posting["job_title"] or ""
        title_lower = title.lower()
        if any(target.lower() in title_lower for target in TARGET_TITLES):
            matching_count += 1

    if matching_count >= 2:
        score += 5

    score = min(score, 20)

    logger.debug(
        "ICP score for company_id=%d: %d (matching_titles=%d)",
        company_id, score, matching_count,
    )
    return score
