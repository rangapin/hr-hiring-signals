"""Reporting sub-package for the hr-alerter project.

Exports the two main public functions:

- ``compose_weekly_report`` -- build the HTML report from DB data.
- ``send_email`` -- deliver an HTML email via SMTP.

Usage::

    from hr_alerter.reporting import compose_weekly_report, send_email

    report = compose_weekly_report(conn)
    send_email("recipient@example.com", report["subject"], report["html_body"])
"""

from hr_alerter.reporting.composer import compose_weekly_report
from hr_alerter.reporting.sender import send_email

__all__ = ["compose_weekly_report", "send_email"]
