"""Compose the weekly HR hiring report.

Queries the database for hot and warm signals from the last 7 days,
enriches them with recent job postings, and renders an HTML email body
using the Jinja2 template at ``templates/weekly_report.html``.
"""

import datetime
import logging
import pathlib
import sqlite3

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Locate the templates directory relative to this file.
_TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"


def _get_week_range() -> str:
    """Return a human-readable week range string for the current week."""
    today = datetime.date.today()
    # Week runs Monday to Sunday; find the most recent Monday.
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"Week of {monday.strftime('%B %d')} - {sunday.strftime('%B %d, %Y')}"


def _build_why_now(signal: dict) -> str:
    """Generate a short 'Why Now' blurb from signal flags."""
    parts: list[str] = []
    if signal.get("has_director_role"):
        parts.append("Hiring HR leadership roles signals strategic investment in people operations")
    if signal.get("has_wellbeing_keywords"):
        parts.append("Job descriptions mention wellbeing/mental health programs")
    if signal.get("multi_city_expansion"):
        parts.append("Expanding HR presence across multiple cities")
    if not parts:
        posting_count = signal.get("posting_count_30d", 0)
        parts.append(
            f"Active HR hiring with {posting_count} postings in 30 days "
            "indicates team expansion"
        )
    return ". ".join(parts) + "."


def _query_signals(
    conn: sqlite3.Connection,
    temperature: str,
    days: int = 7,
) -> list[dict]:
    """Return signals of the given temperature from the last *days* days.

    Joins ``signals`` with ``companies`` to get the company name and
    headcount.
    """
    sql = """
        SELECT
            s.id            AS signal_id,
            s.company_id,
            c.name_normalized AS company_name,
            c.headcount_poland,
            s.final_score,
            s.posting_count_7d,
            s.posting_count_30d,
            s.has_director_role,
            s.has_wellbeing_keywords,
            s.multi_city_expansion
        FROM signals s
        JOIN companies c ON s.company_id = c.id
        WHERE s.lead_temperature = :temperature
          AND s.signal_date >= date('now', :days_offset)
          AND c.is_existing_customer = 0
        ORDER BY s.final_score DESC
    """
    rows = conn.execute(sql, {
        "temperature": temperature,
        "days_offset": f"-{days} days",
    }).fetchall()

    return [dict(row) for row in rows]


def _query_recent_postings(
    conn: sqlite3.Connection,
    company_id: int,
    days: int = 30,
) -> list[dict]:
    """Return recent job postings for a company, enriched with days_ago."""
    sql = """
        SELECT
            job_title,
            post_date,
            job_description
        FROM job_postings
        WHERE company_id = :company_id
          AND post_date >= date('now', :days_offset)
          AND is_relevant = 1
        ORDER BY post_date DESC
        LIMIT 5
    """
    rows = conn.execute(sql, {
        "company_id": company_id,
        "days_offset": f"-{days} days",
    }).fetchall()

    today = datetime.date.today()
    wellbeing_keywords = [
        "wellbeing", "dobrostan", "mental health", "zdrowie psychiczne",
    ]

    results = []
    for row in rows:
        row_dict = dict(row)
        post_date_str = row_dict.get("post_date", "")
        try:
            post_date = datetime.date.fromisoformat(post_date_str)
            days_ago = (today - post_date).days
        except (ValueError, TypeError):
            days_ago = 0

        jd = (row_dict.get("job_description") or "").lower()
        has_wellbeing_kw = any(kw in jd for kw in wellbeing_keywords)

        results.append({
            "job_title": row_dict["job_title"],
            "days_ago": days_ago,
            "has_wellbeing_kw": has_wellbeing_kw,
        })

    return results


def _query_stats(conn: sqlite3.Connection, days: int = 7) -> dict:
    """Gather aggregate statistics for the stats section."""
    total_postings = conn.execute(
        "SELECT COUNT(*) AS cnt FROM job_postings "
        "WHERE post_date >= date('now', :offset)",
        {"offset": f"-{days} days"},
    ).fetchone()["cnt"]

    new_companies = conn.execute(
        "SELECT COUNT(DISTINCT company_name_raw) AS cnt FROM job_postings "
        "WHERE post_date >= date('now', :offset)",
        {"offset": f"-{days} days"},
    ).fetchone()["cnt"]

    icp_matches = conn.execute(
        "SELECT COUNT(*) AS cnt FROM companies WHERE is_icp_match = 1"
    ).fetchone()["cnt"]

    return {
        "total_postings": total_postings,
        "new_companies": new_companies,
        "icp_matches": icp_matches,
    }


def compose_weekly_report(conn: sqlite3.Connection) -> dict:
    """Build the weekly HR hiring report.

    Queries the database for hot and warm signals from the last 7 days,
    enriches each signal with recent job postings and a "Why Now" blurb,
    then renders the HTML template.

    Args:
        conn: An open SQLite connection (with ``sqlite3.Row`` row factory).

    Returns:
        A dict with keys:
            - ``subject`` (str): The email subject line.
            - ``html_body`` (str): The rendered HTML report.
            - ``hot_count`` (int): Number of hot signals.
            - ``warm_count`` (int): Number of warm signals.
    """
    # --- query signals -----------------------------------------------
    hot_signals = _query_signals(conn, "hot")
    warm_signals = _query_signals(conn, "warm")

    # --- enrich each signal with postings and why_now ----------------
    for signal in hot_signals:
        signal["recent_postings"] = _query_recent_postings(
            conn, signal["company_id"]
        )
        signal["why_now"] = _build_why_now(signal)

    for signal in warm_signals:
        signal["recent_postings"] = _query_recent_postings(
            conn, signal["company_id"]
        )
        signal["why_now"] = _build_why_now(signal)

    # --- stats -------------------------------------------------------
    stats = _query_stats(conn)
    stats["hot_count"] = len(hot_signals)
    stats["warm_count"] = len(warm_signals)

    # --- render template ---------------------------------------------
    week_range = _get_week_range()

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("weekly_report.html")

    html_body = template.render(
        week_range=week_range,
        hot_signals=hot_signals,
        warm_signals=warm_signals,
        stats=stats,
    )

    # --- subject line ------------------------------------------------
    total_companies = len(hot_signals) + len(warm_signals)
    subject = (
        f"{total_companies} Companies Scaling HR Teams This Week "
        "| Polish Job Market Alerter"
    )

    logger.info(
        "Composed weekly report: %d hot, %d warm signals",
        len(hot_signals),
        len(warm_signals),
    )

    return {
        "subject": subject,
        "html_body": html_body,
        "hot_count": len(hot_signals),
        "warm_count": len(warm_signals),
    }
