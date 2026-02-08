"""pypyr step: send the weekly report email.

Reads the composed report from ``context['report']`` and the recipient
address from context or the ``RECIPIENT_EMAIL`` environment variable,
then dispatches the HTML email via SMTP.  On success the step updates
the corresponding ``reports`` row with ``sent_at``.

Usage in a pipeline YAML::

    steps:
      - name: hr_alerter.steps.send_email

Context keys consumed:
    report (dict): The composed report (must contain ``subject`` and
        ``html_body``).
    conn (sqlite3.Connection): An initialised database connection.
    recipient_email (str, optional): Override recipient email.  Falls
        back to the ``RECIPIENT_EMAIL`` env var.

Context keys produced:
    email_sent (bool): Whether the email was dispatched successfully.
"""

import datetime
import logging
import os

from hr_alerter.reporting.sender import send_email

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """pypyr entry-point: send the weekly report email.

    Args:
        context: The mutable pypyr context dictionary.
    """
    report = context.get("report")
    if not report:
        logger.warning("No report found in context; skipping email send.")
        context["email_sent"] = False
        return

    recipient = context.get(
        "recipient_email",
        os.environ.get("RECIPIENT_EMAIL", ""),
    )
    if not recipient:
        logger.warning(
            "No recipient email configured. Set recipient_email in "
            "context or RECIPIENT_EMAIL environment variable."
        )
        context["email_sent"] = False
        return

    subject = report["subject"]
    html_body = report["html_body"]

    success = send_email(recipient, subject, html_body)
    context["email_sent"] = success

    if success:
        logger.info("Email sent to %s", recipient)
        # Update reports.sent_at for the most recent unsent report.
        conn = context.get("conn")
        if conn:
            try:
                conn.execute(
                    "UPDATE reports SET sent_at = :sent_at "
                    "WHERE id = (SELECT id FROM reports WHERE sent_at IS NULL ORDER BY id DESC LIMIT 1)",
                    {"sent_at": datetime.datetime.now().isoformat()},
                )
                conn.commit()
                logger.info("Updated reports.sent_at in database.")
            except Exception as exc:
                logger.error("Failed to update reports.sent_at: %s", exc)
    else:
        logger.warning("Email delivery failed for %s", recipient)
