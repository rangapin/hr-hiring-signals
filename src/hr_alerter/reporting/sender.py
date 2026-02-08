"""Send HTML email reports via SMTP.

Uses stdlib ``smtplib`` and ``email.mime`` to send HTML emails.
SMTP credentials are read from environment variables:

- ``SMTP_EMAIL`` -- sender email address (required)
- ``SMTP_PASSWORD`` -- sender password / app password (required)
- ``SMTP_HOST`` -- SMTP server hostname (default: ``smtp.gmail.com``)
- ``SMTP_PORT`` -- SMTP server port (default: ``465``)

If the required credentials are missing the function logs a warning
and returns ``False`` without raising.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(recipient: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP_SSL.

    Args:
        recipient: The destination email address.
        subject: The email subject line.
        html_body: The full HTML content of the email body.

    Returns:
        ``True`` if the email was sent successfully, ``False`` otherwise.
        This function never raises; all errors are logged and swallowed.
    """
    sender_email = os.environ.get("SMTP_EMAIL", "")
    sender_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))

    # --- guard: missing credentials ----------------------------------
    if not sender_email or not sender_password:
        logger.warning(
            "SMTP credentials not configured. "
            "Set SMTP_EMAIL and SMTP_PASSWORD environment variables to "
            "enable email delivery."
        )
        return False

    if not recipient:
        logger.warning("No recipient email address provided; skipping send.")
        return False

    # --- build MIME message ------------------------------------------
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient

    html_part = MIMEText(html_body, "html", "utf-8")
    msg.attach(html_part)

    # --- send via SMTP_SSL -------------------------------------------
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

        logger.info("Email sent successfully to %s", recipient)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed. Check SMTP_EMAIL and "
            "SMTP_PASSWORD environment variables."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending email: %s", exc)
        return False

    except OSError as exc:
        logger.error(
            "Network error while connecting to %s:%d: %s",
            smtp_host, smtp_port, exc,
        )
        return False
