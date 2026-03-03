"""Send brand equity PDF report via email."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_report_email(
    to_email: str,
    company_name: str,
    overall_score: int,
    pdf_bytes: bytes,
) -> bool:
    """Send the brand equity PDF report to the given email address.

    Returns True on success, False on failure (non-fatal).
    """
    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured — cannot send email to %s", to_email)
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Brand Equity Report: {company_name} (Score: {overall_score}/100)"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    msg.set_content(
        f"Hi,\n\n"
        f"Attached is your Brand Equity Report for {company_name}.\n\n"
        f"Overall Brand Equity Score: {overall_score}/100\n"
        f"Methodology: ISO 20671:2019\n\n"
        f"This report includes:\n"
        f"• 5-dimension brand equity analysis\n"
        f"• Competitor benchmarking\n"
        f"• Formula explanation and derivation\n"
        f"• Limitations and actionable recommendations\n\n"
        f"Want help implementing these recommendations?\n"
        f"Sign up for AI Brand Automator: https://aibrandautomator.com\n\n"
        f"Best regards,\n"
        f"AI Brand Automator Team"
    )

    filename = f"brand-equity-{company_name.lower().replace(' ', '-')}.pdf"
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Report emailed to %s for %s", to_email, company_name)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc, exc_info=True)
        return False
