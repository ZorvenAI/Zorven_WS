"""
Shared helper functions for publishing content to social platforms.
This module consolidates duplicate publish logic from tasks.py and views.py.
"""
import logging
from typing import Optional

from django.utils import timezone

from .constants import (
    TEST_ACCESS_TOKEN,
    TWITTER_TEST_ACCESS_TOKEN,
    FACEBOOK_TEST_ACCESS_TOKEN,
    FACEBOOK_TEST_PAGE_TOKEN,
    INSTAGRAM_TEST_USER_TOKEN,
)

logger = logging.getLogger(__name__)


def publish_to_platform(
    profile,
    content_text: str,
    content_title: str,
    media_urls: Optional[list] = None,
    log_prefix: str = "",
) -> tuple[Optional[dict], Optional[str]]:
    """
    Publish content to a single social platform.

    Args:
        profile: SocialProfile instance
        content_text: The text content to publish
        content_title: Title for logging purposes
        media_urls: Optional list of media URLs/IDs
        log_prefix: Prefix for log messages (e.g., "Auto-", "Test ")

    Returns:
        Tuple of (result_dict, error_string) - one will be None
    """
    from .services import linkedin_service, twitter_service, facebook_service

    media_urls = media_urls or []

    if profile.platform == "linkedin" and profile.status == "connected":
        try:
            if profile.access_token == TEST_ACCESS_TOKEN:
                result = {
                    "test_mode": True,
                    "message": "Post simulated in test mode",
                    "has_media": len(media_urls) > 0,
                }
                logger.info(f"{log_prefix}Test publish to LinkedIn: {content_title}")
                return result, None
            else:
                access_token = profile.get_valid_access_token()
                result = linkedin_service.create_share(
                    access_token=access_token,
                    user_urn=profile.profile_id,
                    text=content_text,
                    image_urns=media_urls if media_urls else None,
                )
                logger.info(
                    f"{log_prefix}Successfully published to LinkedIn: {content_title}"
                )
                return result, None
        except Exception as e:
            error = f"LinkedIn: {str(e)}"
            logger.error(f"{log_prefix}Failed to publish to LinkedIn: {e}")
            return None, error

    elif profile.platform == "twitter" and profile.status == "connected":
        try:
            if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
                result = {
                    "test_mode": True,
                    "message": "Tweet simulated in test mode",
                    "has_media": len(media_urls) > 0,
                }
                logger.info(f"{log_prefix}Test publish to Twitter: {content_title}")
                return result, None
            else:
                access_token = profile.get_valid_access_token()
                result = twitter_service.create_tweet(
                    access_token=access_token,
                    text=content_text,
                    media_ids=media_urls if media_urls else None,
                )
                logger.info(
                    f"{log_prefix}Successfully published to Twitter: {content_title}"
                )
                return result, None
        except Exception as e:
            error = f"Twitter: {str(e)}"
            logger.error(f"{log_prefix}Failed to publish to Twitter: {e}")
            return None, error

    elif profile.platform == "facebook" and profile.status == "connected":
        try:
            if (
                profile.access_token == FACEBOOK_TEST_ACCESS_TOKEN
                or profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN
            ):
                import uuid

                test_post_id = f"test_post_{uuid.uuid4().hex[:8]}"
                result = {
                    "test_mode": True,
                    "id": test_post_id,
                    "message": "Facebook post simulated in test mode",
                    "has_media": len(media_urls) > 0,
                }
                logger.info(f"{log_prefix}Test publish to Facebook: {content_title}")
                return result, None
            else:
                if not profile.page_access_token or not profile.page_id:
                    return None, "Facebook: No page access token or page ID"

                # For Facebook, media_urls are photo URLs
                if media_urls and len(media_urls) > 0:
                    # Post with first photo
                    result = facebook_service.create_page_photo_post(
                        page_id=profile.page_id,
                        page_access_token=profile.page_access_token,
                        photo_url=media_urls[0],
                        message=content_text,
                    )
                else:
                    result = facebook_service.create_page_post(
                        page_id=profile.page_id,
                        page_access_token=profile.page_access_token,
                        message=content_text,
                    )
                logger.info(
                    f"{log_prefix}Successfully published to Facebook: {content_title}"
                )
                return result, None
        except Exception as e:
            error = f"Facebook: {str(e)}"
            logger.error(f"{log_prefix}Failed to publish to Facebook: {e}")
            return None, error

    elif profile.platform == "instagram" and profile.status == "connected":
        from .services import instagram_service

        try:
            access_token = profile.instagram_access_token or profile.page_access_token
            if access_token == INSTAGRAM_TEST_USER_TOKEN:
                import uuid

                test_post_id = f"test_ig_post_{uuid.uuid4().hex[:8]}"
                result = {
                    "test_mode": True,
                    "id": test_post_id,
                    "message": "Instagram post simulated in test mode",
                    "has_media": len(media_urls) > 0,
                }
                logger.info(f"{log_prefix}Test publish to Instagram: {content_title}")
                return result, None
            else:
                if not profile.instagram_user_id:
                    return None, "Instagram: No Instagram Business Account connected"

                # Instagram requires media
                if not media_urls or len(media_urls) == 0:
                    return None, "Instagram: Media is required for Instagram posts"

                # For Instagram, media_urls should be image URLs
                # Create media container and publish
                container = instagram_service.create_media_container(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    image_url=media_urls[0],  # Use first image
                    caption=content_text,
                    media_type="IMAGE",
                )

                container_id = container.get("id")
                result = instagram_service.publish_media(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    container_id=container_id,
                )
                logger.info(
                    f"{log_prefix}Successfully published to Instagram: {content_title}"
                )
                return result, None
        except Exception as e:
            error = f"Instagram: {str(e)}"
            logger.error(f"{log_prefix}Failed to publish to Instagram: {e}")
            return None, error

    return None, None


def publish_content(content, log_prefix: str = "") -> tuple[dict, list]:
    """
    Publish content to all connected social platforms.

    Args:
        content: ContentCalendar instance
        log_prefix: Prefix for log messages

    Returns:
        Tuple of (results_dict, errors_list)
    """
    results = {}
    errors = []

    media_urls = content.media_urls if content.media_urls else []

    for profile in content.social_profiles.all():
        result, error = publish_to_platform(
            profile=profile,
            content_text=content.content,
            content_title=content.title,
            media_urls=media_urls,
            log_prefix=log_prefix,
        )

        if result:
            results[profile.platform] = result
        if error:
            errors.append(error)

    return results, errors


def update_content_status(content, results: dict, errors: list) -> str:
    """
    Update content status based on publish results.

    Args:
        content: ContentCalendar instance
        results: Dict of platform results
        errors: List of error strings

    Returns:
        The new status string
    """
    if errors and not results:
        content.status = "failed"
        content.post_results = {"errors": errors}
    else:
        content.status = "published"
        content.published_at = timezone.now()
        content.post_results = results

    content.save()
    return content.status
