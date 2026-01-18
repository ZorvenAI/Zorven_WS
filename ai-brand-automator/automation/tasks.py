"""
Celery tasks for the automation app.
"""
import logging
from celery import shared_task
from django.utils import timezone

from .publish_helpers import publish_content, update_content_status

logger = logging.getLogger(__name__)


@shared_task(name="automation.publish_scheduled_posts")
def publish_scheduled_posts():
    """
    Celery task to automatically publish scheduled posts that are due.
    This task should be run periodically (e.g., every minute) via Celery Beat.
    """
    from automation.models import ContentCalendar

    now = timezone.now()

    # Get all scheduled posts that are due (scheduled_date <= now)
    due_posts = ContentCalendar.objects.filter(
        status="scheduled", scheduled_date__lte=now
    )

    published_count = 0
    failed_count = 0

    for content in due_posts:
        logger.info(f"Auto-publishing scheduled post: {content.title}")

        results, errors = publish_content(content, log_prefix="Auto-")
        status = update_content_status(content, results, errors)

        if status == "failed":
            failed_count += 1
        else:
            published_count += 1

    logger.info(
        f"Auto-publish completed: {published_count} published, {failed_count} failed"
    )
    return {
        "published": published_count,
        "failed": failed_count,
        "timestamp": now.isoformat(),
    }


@shared_task(name="automation.publish_single_post")
def publish_single_post(content_id):
    """
    Celery task to publish a single scheduled post.
    This can be called when a post is scheduled to run at a specific time.
    """
    from automation.models import ContentCalendar

    try:
        content = ContentCalendar.objects.get(id=content_id)
    except ContentCalendar.DoesNotExist:
        logger.error(f"Content with id {content_id} not found")
        return {"error": "Content not found"}

    if content.status != "scheduled":
        logger.warning(
            f"Content {content_id} is not in scheduled status: {content.status}"
        )
        return {"error": f"Content is {content.status}, not scheduled"}

    logger.info(f"Publishing scheduled post: {content.title}")

    results, errors = publish_content(content, log_prefix="")
    update_content_status(content, results, errors)

    return {
        "content_id": content_id,
        "status": content.status,
        "results": results,
        "errors": errors,
    }
