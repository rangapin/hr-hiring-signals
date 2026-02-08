"""pypyr step: score all qualifying companies and save signals.

Queries the database for companies with at least 2 job postings in the
last 30 days, runs the composite scorer on each, and persists the
results to the ``signals`` table.
"""

import datetime
import logging
import sqlite3

from hr_alerter.scoring.composite import calculate_final_score
from hr_alerter.db.manager import save_signal

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """pypyr entry-point.

    Expects ``context['conn']`` to be an open :class:`sqlite3.Connection`.

    After execution, ``context['scored_companies']`` will contain a list
    of ``score_result_dict`` objects.
    """
    conn: sqlite3.Connection = context["conn"]

    # Find companies with 2+ postings in the last 30 days.
    rows = conn.execute(
        """
        SELECT company_id, COUNT(*) AS posting_count
        FROM job_postings
        WHERE company_id IS NOT NULL
          AND post_date >= date('now', '-30 days')
          AND is_relevant = 1
        GROUP BY company_id
        HAVING COUNT(*) >= 2
        ORDER BY posting_count DESC
        """
    ).fetchall()

    logger.info("Found %d companies with 2+ postings in 30 days", len(rows))

    scored: list[dict] = []
    today = datetime.date.today().isoformat()

    for row in rows:
        company_id = row["company_id"]

        try:
            result = calculate_final_score(conn, company_id)
        except Exception:
            logger.exception(
                "Error scoring company_id=%d, skipping", company_id
            )
            continue

        # Build signal dict for persistence.
        signal = {
            "company_id": company_id,
            "signal_date": today,
            "signal_type": "hiring_velocity",
            "signal_strength": result["final_score"],
            "velocity_score": result["velocity"],
            "posting_count_7d": result["posting_count_7d"],
            "posting_count_30d": result["posting_count_30d"],
            "posting_count_90d": row["posting_count"],  # approximate
            "has_director_role": result["has_director_role"],
            "has_wellbeing_keywords": result["has_wellbeing_keywords"],
            "multi_city_expansion": result["multi_city_expansion"],
            "final_score": result["final_score"],
            "lead_temperature": result["lead_temperature"],
        }

        save_signal(conn, signal)
        scored.append(result)

    context["scored_companies"] = scored

    hot = sum(1 for s in scored if s["lead_temperature"] == "hot")
    warm = sum(1 for s in scored if s["lead_temperature"] == "warm")
    cold = sum(1 for s in scored if s["lead_temperature"] == "cold")

    logger.info(
        "Scoring complete: %d companies scored (%d hot, %d warm, %d cold)",
        len(scored), hot, warm, cold,
    )
