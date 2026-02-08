"""pypyr step: generate the weekly HTML report.

Reads the database connection from the pypyr context, calls
``compose_weekly_report`` to build the HTML email body, stores the
result in ``context['report']``, and persists a record to the
``reports`` table.

Usage in a pipeline YAML::

    steps:
      - name: hr_alerter.steps.generate_report

Context keys consumed:
    conn (sqlite3.Connection): An initialised database connection.
    recipient_email (str, optional): Email address for the report
        recipient.  Falls back to the ``RECIPIENT_EMAIL`` env var.

Context keys produced:
    report (dict): The composed report with keys ``subject``,
        ``html_body``, ``hot_count``, ``warm_count``.
"""

import datetime
import logging
import os

from hr_alerter.reporting.composer import compose_weekly_report
from hr_alerter.db.manager import save_report

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """pypyr entry-point: compose weekly report and persist to DB.

    Args:
        context: The mutable pypyr context dictionary.
    """
    conn = context["conn"]

    report = compose_weekly_report(conn)
    context["report"] = report

    logger.info(
        "Weekly report generated: %d hot, %d warm signals",
        report["hot_count"],
        report["warm_count"],
    )

    # Persist report metadata to the reports table.
    recipient = context.get(
        "recipient_email",
        os.environ.get("RECIPIENT_EMAIL", ""),
    )

    save_report(conn, {
        "report_date": datetime.date.today().isoformat(),
        "report_type": "weekly_digest",
        "recipient_email": recipient,
        "hot_count": report["hot_count"],
        "warm_count": report["warm_count"],
        "email_subject": report["subject"],
        "email_body": report["html_body"],
    })

    logger.info("Report saved to database.")
