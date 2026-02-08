"""Content-signals scoring dimension for the hr-alerter project.

Scans job description text for wellbeing, EAP, and culture keywords
(in both Polish and English).  Maximum score: 10 points.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Keyword groups with their point values.
WELLBEING_KEYWORDS: list[str] = [
    "wellbeing",
    "dobrostan",
    "mental health",
    "zdrowie psychiczne",
]

EAP_KEYWORDS: list[str] = [
    "eap",
    "employee assistance",
    "wsparcie pracownik\u00f3w",  # wsparcie pracownikow
]

CULTURE_KEYWORDS: list[str] = [
    "kultura organizacyjna",
    "employer branding",
    "employee experience",
]


def calculate_content_score(conn: sqlite3.Connection, company_id: int) -> int:
    """Calculate content score by scanning job descriptions for keywords.

    Points per posting (additive across all postings, capped at 10):
        - Wellbeing keyword found -> +5
        - EAP keyword found      -> +3
        - Culture keyword found   -> +2

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` to score.

    Returns:
        An integer score between 0 and 10.
    """
    postings = conn.execute(
        """
        SELECT job_description
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', '-30 days')
          AND is_relevant = 1
        """,
        {"company_id": company_id},
    ).fetchall()

    score = 0

    for posting in postings:
        jd = (posting["job_description"] or "").lower()
        if not jd:
            continue

        if any(kw.lower() in jd for kw in WELLBEING_KEYWORDS):
            score += 5
        if any(kw.lower() in jd for kw in EAP_KEYWORDS):
            score += 3
        if any(kw.lower() in jd for kw in CULTURE_KEYWORDS):
            score += 2

    score = min(score, 10)

    logger.debug("Content score for company_id=%d: %d", company_id, score)
    return score
