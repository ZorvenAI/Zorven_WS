"""
Custom email backend for Mailgun HTTP API.

Uses requests to send email via Mailgun's REST API instead of SMTP.
This avoids SMTP auth issues with sandbox domains and is more reliable
from containerized environments.

Usage in settings.py:
    EMAIL_BACKEND = "brand_automator.email_backends.MailgunAPIBackend"

Required env vars:
    MAILGUN_API_KEY   — Your Mailgun API key
    MAILGUN_DOMAIN    — Your Mailgun domain (e.g. sandbox...mailgun.org)
"""

import logging

import requests
from decouple import config
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class MailgunAPIBackend(BaseEmailBackend):
    """Send email via Mailgun HTTP API."""

    API_URL = "https://api.mailgun.net/v3/{domain}/messages"

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = config("MAILGUN_API_KEY", default="")
        self.domain = config("MAILGUN_DOMAIN", default="")

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        if not self.api_key or not self.domain:
            logger.error(
                "Mailgun not configured: MAILGUN_API_KEY and "
                "MAILGUN_DOMAIN are required"
            )
            if not self.fail_silently:
                raise ValueError("MAILGUN_API_KEY and MAILGUN_DOMAIN must be set")
            return 0

        num_sent = 0
        url = self.API_URL.format(domain=self.domain)

        for message in email_messages:
            try:
                data = {
                    "from": message.from_email,
                    "to": message.to,
                    "subject": message.subject,
                    "text": message.body,
                }

                # Add CC and BCC if present
                if message.cc:
                    data["cc"] = message.cc
                if message.bcc:
                    data["bcc"] = message.bcc

                # Add HTML body if present
                if hasattr(message, "alternatives"):
                    for content, mimetype in message.alternatives:
                        if mimetype == "text/html":
                            data["html"] = content

                response = requests.post(
                    url,
                    auth=("api", self.api_key),
                    data=data,
                    timeout=10,
                )

                if response.status_code == 200:
                    logger.info(
                        "Email sent via Mailgun to %s: %s",
                        message.to,
                        response.json().get("id", ""),
                    )
                    num_sent += 1
                else:
                    logger.error(
                        "Mailgun API error %d for %s: %s",
                        response.status_code,
                        message.to,
                        response.text,
                    )
                    if not self.fail_silently:
                        response.raise_for_status()

            except Exception as exc:
                logger.error(
                    "Failed to send email via Mailgun to %s: %s",
                    message.to,
                    exc,
                )
                if not self.fail_silently:
                    raise

        return num_sent
