"""Send brand equity PDF report via Mailgun HTTP API (async)."""

import logging
from enum import Enum

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MAILGUN_API_URL = "https://api.mailgun.net/v3/{domain}/messages"


class EmailResult(Enum):
    """Outcome of an email send attempt."""

    SUCCESS = "success"
    NOT_CONFIGURED = "not_configured"
    SEND_FAILED = "send_failed"


async def send_report_email(
    to_email: str,
    company_name: str,
    overall_score: int,
    pdf_bytes: bytes,
) -> EmailResult:
    """Send the brand equity PDF report via Mailgun.

    Returns an EmailResult enum so callers can differentiate between
    misconfiguration and transient send failures.
    """
    if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN:
        logger.warning(
            "Mailgun not configured — cannot send email to %s", to_email
        )
        return EmailResult.NOT_CONFIGURED

    url = MAILGUN_API_URL.format(domain=settings.MAILGUN_DOMAIN)
    filename = f"brand-equity-{company_name.lower().replace(' ', '-')}.pdf"

    body_text = (
        f"Hi,\n\n"
        f"Attached is your Brand Equity Report for {company_name}.\n\n"
        f"Overall Brand Equity Score: {overall_score}/100\n"
        f"Methodology: ISO 20671:2019\n\n"
        f"This report includes:\n"
        f"  - 5-dimension brand equity analysis\n"
        f"  - Competitor benchmarking\n"
        f"  - Formula explanation and derivation\n"
        f"  - Limitations and actionable recommendations\n\n"
        f"Want help implementing these recommendations?\n"
        f"Sign up for AI Brand Automator: https://aibrandautomator.com\n\n"
        f"Best regards,\n"
        f"AI Brand Automator Team"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                auth=("api", settings.MAILGUN_API_KEY),
                data={
                    "from": settings.MAILGUN_FROM_EMAIL,
                    "to": [to_email],
                    "subject": (
                        f"Brand Equity Report: {company_name} "
                        f"(Score: {overall_score}/100)"
                    ),
                    "text": body_text,
                },
                files={"attachment": (filename, pdf_bytes, "application/pdf")},
            )

        if response.status_code == 200:
            logger.info("Report emailed to %s for %s via Mailgun", to_email, company_name)
            return EmailResult.SUCCESS

        logger.error(
            "Mailgun API error %d for %s: %s",
            response.status_code,
            to_email,
            response.text[:300],
        )
        return EmailResult.SEND_FAILED

    except Exception as exc:
        logger.error(
            "Failed to send email to %s via Mailgun: %s",
            to_email,
            exc,
            exc_info=True,
        )
        return EmailResult.SEND_FAILED
