"""Celery tasks for ai_services."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def auto_title_session(self, session_id):
    """Generate a concise title from the first user message using Gemini."""
    from .models import ChatSession, ChatMessage
    from .services import ai_service

    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        logger.warning("auto_title_session: session %s not found", session_id)
        return

    # Skip if already titled (not a default timestamp title)
    if session.title and not session.title.startswith("Chat "):
        return

    first_msg = (
        ChatMessage.objects.filter(session=session, role="user")
        .order_by("created_at")
        .first()
    )
    if not first_msg:
        return

    try:
        title = ai_service.generate_title(first_msg.content)
    except Exception as exc:
        # Retry on rate-limit (429) errors with exponential backoff
        logger.warning(
            "Title generation failed for session %s (attempt %d): %s",
            session.session_id,
            self.request.retries + 1,
            exc,
        )
        raise self.retry(exc=exc, countdown=15 * (self.request.retries + 1))

    session.title = title[:255]
    session.save(update_fields=["title"])
    logger.info("Auto-titled session %s: '%s'", session.session_id, session.title)

    # Invalidate cached session list so sidebar shows new title
    if session.tenant_id:
        from django.core.cache import cache

        try:
            cache.delete(
                f"chat:sessions:{session.tenant_id}:" f"page=:page_size=:ordering="
            )
        except Exception:
            pass
