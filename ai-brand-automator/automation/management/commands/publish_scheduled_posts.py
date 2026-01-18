"""
Management command to automatically publish scheduled posts that are due.
Run this via cron: */5 * * * * python manage.py publish_scheduled_posts
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from automation.models import ContentCalendar
from automation.services import linkedin_service
from automation.constants import TEST_ACCESS_TOKEN

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Publish scheduled posts that are due"

    def handle(self, *args, **options):
        now = timezone.now()

        # Get all scheduled posts that are due (scheduled_date <= now)
        due_posts = ContentCalendar.objects.filter(
            status="scheduled", scheduled_date__lte=now
        )

        published_count = 0
        failed_count = 0

        for content in due_posts:
            self.stdout.write(f"Processing: {content.title}")

            results = {}
            errors = []

            # Publish to each connected platform
            for profile in content.social_profiles.all():
                if profile.platform == "linkedin" and profile.status == "connected":
                    try:
                        # Check if test mode
                        if profile.access_token == TEST_ACCESS_TOKEN:
                            results["linkedin"] = {
                                "test_mode": True,
                                "message": "Post simulated in test mode",
                            }
                            logger.info(
                                f"Test auto-publish to LinkedIn: {content.title}"
                            )
                        else:
                            access_token = profile.get_valid_access_token()
                            result = linkedin_service.create_share(
                                access_token=access_token,
                                user_urn=profile.profile_id,
                                text=content.content,
                            )
                            results["linkedin"] = result
                    except Exception as e:
                        errors.append(f"LinkedIn: {str(e)}")
                        logger.error(f"Failed to auto-publish to LinkedIn: {e}")

            # Update content status
            if errors and not results:
                content.status = "failed"
                content.post_results = {"errors": errors}
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  Failed: {errors}"))
            else:
                content.status = "published"
                content.published_at = timezone.now()
                content.post_results = results
                published_count += 1
                self.stdout.write(self.style.SUCCESS("  Published successfully"))

            content.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted: {published_count} published, {failed_count} failed"
            )
        )
