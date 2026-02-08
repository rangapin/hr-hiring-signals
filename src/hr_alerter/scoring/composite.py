"""Composite scorer for the hr-alerter project.

Combines all five scoring dimensions into a single final score and
classifies the lead temperature as hot, warm, or cold.
"""

import datetime
import logging
import sqlite3

from hr_alerter.scoring.velocity import calculate_velocity_score
from hr_alerter.scoring.seniority import calculate_seniority_score
from hr_alerter.scoring.icp import calculate_icp_score
from hr_alerter.scoring.content import calculate_content_score
from hr_alerter.scoring.recency import calculate_recency_score

logger = logging.getLogger(__name__)


def calculate_final_score(conn: sqlite3.Connection, company_id: int) -> dict:
    """Compute the composite score for a company across all 5 dimensions.

    Dimensions:
        - Velocity  (max 40)
        - Seniority (max 20)
        - ICP Fit   (max 20)
        - Content   (max 10)
        - Recency   (max 10)

    Temperature classification:
        - >= 75 -> hot
        - >= 50 -> warm
        - <  50 -> cold

    Args:
        conn: An open SQLite connection.
        company_id: The ``companies.id`` to score.

    Returns:
        A dict matching the ``score_result_dict`` contract from
        ``team-config.json``.
    """
    velocity = calculate_velocity_score(conn, company_id)
    seniority = calculate_seniority_score(conn, company_id)
    icp = calculate_icp_score(conn, company_id)
    content = calculate_content_score(conn, company_id)
    recency = calculate_recency_score(conn, company_id)

    final_score = velocity + seniority + icp + content + recency

    if final_score >= 75:
        lead_temperature = "hot"
    elif final_score >= 50:
        lead_temperature = "warm"
    else:
        lead_temperature = "cold"

    # ---- Supplementary metadata ----
    posting_count_7d = _count_postings(conn, company_id, 7)
    posting_count_30d = _count_postings(conn, company_id, 30)
    has_director_role = _has_director_role(conn, company_id)
    has_wellbeing_keywords = _has_wellbeing_keywords(conn, company_id)
    multi_city_expansion = _multi_city_expansion(conn, company_id)

    result: dict = {
        "company_id": company_id,
        "final_score": final_score,
        "lead_temperature": lead_temperature,
        "velocity": velocity,
        "seniority": seniority,
        "icp": icp,
        "content": content,
        "recency": recency,
        "posting_count_7d": posting_count_7d,
        "posting_count_30d": posting_count_30d,
        "has_director_role": has_director_role,
        "has_wellbeing_keywords": has_wellbeing_keywords,
        "multi_city_expansion": multi_city_expansion,
    }

    logger.info(
        "Scored company_id=%d: total=%d (%s) "
        "[vel=%d, sen=%d, icp=%d, con=%d, rec=%d]",
        company_id, final_score, lead_temperature,
        velocity, seniority, icp, content, recency,
    )
    return result


# ---------------------------------------------------------------------------
# Private helpers for metadata fields
# ---------------------------------------------------------------------------

def _count_postings(
    conn: sqlite3.Connection, company_id: int, days: int
) -> int:
    """Count relevant postings within the given window."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', :offset)
          AND is_relevant = 1
        """,
        {"company_id": company_id, "offset": f"-{days} days"},
    ).fetchone()
    return row["cnt"] if row else 0


def _has_director_role(conn: sqlite3.Connection, company_id: int) -> bool:
    """Check whether the company has any director/c-level postings in 30d."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', '-30 days')
          AND seniority_level IN ('director', 'c-level')
          AND is_relevant = 1
        """,
        {"company_id": company_id},
    ).fetchone()
    return (row["cnt"] if row else 0) > 0


def _has_wellbeing_keywords(conn: sqlite3.Connection, company_id: int) -> bool:
    """Check whether any recent JD text contains wellbeing-related keywords."""
    postings = conn.execute(
        """
        SELECT job_description
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', '-30 days')
          AND is_relevant = 1
          AND job_description IS NOT NULL
        """,
        {"company_id": company_id},
    ).fetchall()

    keywords = ["wellbeing", "dobrostan", "mental health", "zdrowie psychiczne"]

    for posting in postings:
        jd = (posting["job_description"] or "").lower()
        if any(kw in jd for kw in keywords):
            return True
    return False


def _multi_city_expansion(conn: sqlite3.Connection, company_id: int) -> bool:
    """Check whether the company is hiring in 2+ distinct cities (30d)."""
    rows = conn.execute(
        """
        SELECT DISTINCT location
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', '-30 days')
          AND is_relevant = 1
          AND location IS NOT NULL
          AND location != ''
        """,
        {"company_id": company_id},
    ).fetchall()

    return len(rows) >= 2
