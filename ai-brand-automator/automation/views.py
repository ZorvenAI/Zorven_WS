"""
Views for the automation app - social media integrations and content scheduling.
"""
import uuid
import logging
from datetime import timedelta
from django.http import HttpResponseRedirect
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import SocialProfile, AutomationTask, ContentCalendar, OAuthState
from .serializers import (
    SocialProfileSerializer,
    AutomationTaskSerializer,
    ContentCalendarSerializer,
)
from .services import (
    linkedin_service,
    twitter_service,
    facebook_service,
    instagram_service,
)
from .constants import (
    TEST_ACCESS_TOKEN,
    TEST_REFRESH_TOKEN,
    LINKEDIN_TITLE_MAX_LENGTH,
    EDITABLE_STATUSES,
    IMAGE_TYPES,
    VIDEO_TYPES,
    DOCUMENT_TYPES,
    MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    MAX_DOCUMENT_SIZE,
    TWITTER_TEST_ACCESS_TOKEN,
    TWITTER_TEST_REFRESH_TOKEN,
    TWITTER_IMAGE_TYPES,
    TWITTER_VIDEO_TYPES,
    TWITTER_MEDIA_MAX_IMAGE_SIZE,
    TWITTER_MEDIA_MAX_VIDEO_SIZE,
    TWITTER_MEDIA_MAX_GIF_SIZE,
    FACEBOOK_TEST_ACCESS_TOKEN,
    FACEBOOK_TEST_PAGE_TOKEN,
    INSTAGRAM_TEST_ACCESS_TOKEN,
    INSTAGRAM_TEST_USER_TOKEN,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class SocialProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing social media profiles.
    """

    serializer_class = SocialProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SocialProfile.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def disconnect(self, request, pk=None):
        """Disconnect a social profile."""
        profile = self.get_object()
        profile.disconnect()
        return Response(
            {"message": f"{profile.get_platform_display()} disconnected successfully"}
        )

    @action(detail=False, methods=["get"])
    def status(self, request):
        """Get connection status for all platforms."""
        profiles = self.get_queryset()

        # Build status for each supported platform
        platforms = ["linkedin", "twitter", "instagram", "facebook"]
        status_dict = {}

        for platform in platforms:
            profile = profiles.filter(platform=platform).first()
            if profile:
                status_dict[platform] = {
                    "connected": profile.status == "connected",
                    "profile_name": profile.profile_name,
                    "profile_url": profile.profile_url,
                    "profile_image_url": profile.profile_image_url,
                    "status": profile.status,
                    "is_token_valid": profile.is_token_valid,
                }
            else:
                status_dict[platform] = {
                    "connected": False,
                    "profile_name": None,
                    "profile_url": None,
                    "profile_image_url": None,
                    "status": "disconnected",
                    "is_token_valid": False,
                }

        return Response(status_dict)


class LinkedInConnectView(APIView):
    """
    Initiates LinkedIn OAuth flow.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Redirect user to LinkedIn authorization page."""
        if not linkedin_service.is_configured:
            return Response(
                {"error": "LinkedIn integration not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Generate a unique state token and store it in database
        # This is more reliable than sessions for JWT-based apps
        state = str(uuid.uuid4())

        # Clean up any old states for this user/platform
        OAuthState.objects.filter(user=request.user, platform="linkedin").delete()

        # Create new state
        OAuthState.objects.create(state=state, user=request.user, platform="linkedin")

        # Get the authorization URL
        auth_url = linkedin_service.get_authorization_url(state)

        return Response({"authorization_url": auth_url})


class LinkedInCallbackView(APIView):
    """
    Handles LinkedIn OAuth callback.
    """

    # No authentication required - this is called by LinkedIn redirect
    permission_classes = []

    def get(self, request):
        """Handle the OAuth callback from LinkedIn."""
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")

        # Debug logging
        logger.info(
            f"LinkedIn callback received - code: {bool(code)}, "
            f"state: {state}, error: {error}"
        )

        # Get frontend URL for redirects
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

        # Handle errors from LinkedIn
        if error:
            logger.error(f"LinkedIn OAuth error: {error} - {error_description}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error={error}&message={error_description}"
            )

        # Validate state token from database (more reliable than sessions for JWT apps)
        try:
            oauth_state = OAuthState.objects.get(state=state, platform="linkedin")
        except OAuthState.DoesNotExist:
            logger.error(f"LinkedIn OAuth state not found: {state}")
            redirect_url = (
                f"{frontend_url}/automation?error=invalid_state"
                "&message=State+token+not+found+or+expired"
            )
            return HttpResponseRedirect(redirect_url)

        # Check if state is expired (10 min limit)
        if oauth_state.is_expired():
            oauth_state.delete()
            logger.error("LinkedIn OAuth state expired")
            redirect_url = (
                f"{frontend_url}/automation?error=state_expired"
                "&message=Authorization+timed+out"
            )
            return HttpResponseRedirect(redirect_url)

        user = oauth_state.user

        try:
            # Exchange code for tokens
            token_data = linkedin_service.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_at = token_data.get("expires_at")

            # Get user profile from LinkedIn
            profile_data = linkedin_service.get_user_profile(access_token)

            # Extract profile ID - the 'sub' field may be full URN or just ID
            # Store the full ID for API calls (create_share handles both formats)
            profile_id = profile_data.get("id", "")

            # LinkedIn profile URLs require vanity name which isn't available
            # from userinfo endpoint, so we link to the generic profile page
            # Note: profile_id may be in URN format, not suitable for /in/ URLs
            profile_url = "https://www.linkedin.com/feed/"

            _, created = SocialProfile.objects.update_or_create(
                user=user,
                platform="linkedin",
                defaults={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_expires_at": expires_at,
                    "profile_id": profile_id,
                    "profile_name": profile_data.get("name"),
                    "profile_url": profile_url,
                    "profile_image_url": profile_data.get("picture"),
                    "status": "connected",
                },
            )

            # Clean up the OAuth state
            oauth_state.delete()

            action = "created" if created else "updated"
            logger.info(f"LinkedIn profile {action} for user {user.email}")

            profile_name = profile_data.get("name", "")
            redirect_url = (
                f"{frontend_url}/automation?success=linkedin&name={profile_name}"
            )
            return HttpResponseRedirect(redirect_url)

        except Exception as e:
            logger.error(f"LinkedIn OAuth callback error: {e}")
            # Clean up the OAuth state even on error
            oauth_state.delete()
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=connection_failed&message={str(e)}"
            )


class LinkedInTestConnectView(APIView):
    """
    Creates a TEST LinkedIn connection for development/testing purposes.
    This bypasses OAuth and creates a mock profile - NO real LinkedIn data is used.
    Only available in DEBUG mode.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create a test LinkedIn connection."""
        if not settings.DEBUG:
            return Response(
                {"error": "Test connections only available in DEBUG mode"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Create a mock LinkedIn profile
        from django.utils import timezone
        from datetime import timedelta

        social_profile, created = SocialProfile.objects.update_or_create(
            user=request.user,
            platform="linkedin",
            defaults={
                "access_token": TEST_ACCESS_TOKEN,
                "refresh_token": TEST_REFRESH_TOKEN,
                "token_expires_at": timezone.now() + timedelta(days=60),
                "profile_id": f"test_user_{request.user.id}",
                "profile_name": request.user.get_full_name()
                or request.user.email.split("@")[0],
                "profile_url": "https://www.linkedin.com/in/test-profile",
                "profile_image_url": None,
                "status": "connected",
            },
        )

        action = "created" if created else "updated"
        logger.info(f"Test LinkedIn profile {action} for user {request.user.email}")

        return Response(
            {
                "message": f"Test LinkedIn connection {action} successfully",
                "profile_name": social_profile.profile_name,
                "is_test": True,
            }
        )


class LinkedInDisconnectView(APIView):
    """
    Disconnects LinkedIn account.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Disconnect LinkedIn account."""
        try:
            profile = SocialProfile.objects.get(user=request.user, platform="linkedin")
            profile.disconnect()
            return Response({"message": "LinkedIn disconnected successfully"})
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )


class LinkedInOrganizationsView(APIView):
    """
    Get LinkedIn Organizations (Company Pages) the user can post to.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get list of organizations the user administers."""
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            return Response(
                {
                    "organizations": [
                        {
                            "id": "test_org_123",
                            "urn": "urn:li:organization:test_org_123",
                            "name": "Test Company Page",
                            "vanity_name": "test-company",
                            "logo_url": None,
                        }
                    ],
                    "current_organization": profile.page_id,
                    "posting_as": "personal" if not profile.page_id else "organization",
                    "test_mode": True,
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            organizations = linkedin_service.get_organizations(access_token)

            return Response(
                {
                    "organizations": organizations,
                    "current_organization": profile.page_id,
                    "posting_as": "personal" if not profile.page_id else "organization",
                }
            )
        except Exception as e:
            logger.error(f"Failed to fetch LinkedIn organizations: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInSelectOrganizationView(APIView):
    """
    Select which LinkedIn entity to post as (personal profile or organization).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Select organization to post to, or clear to post as personal profile."""
        organization_id = request.data.get("organization_id")  # None = personal profile

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if organization_id:
            # Set to post as organization
            profile.page_id = organization_id
            profile.save()

            return Response(
                {
                    "message": "Now posting as organization",
                    "organization_id": organization_id,
                    "posting_as": "organization",
                }
            )
        else:
            # Clear to post as personal profile
            profile.page_id = None
            profile.save()

            return Response(
                {
                    "message": "Now posting as personal profile",
                    "posting_as": "personal",
                }
            )


class LinkedInPostView(APIView):
    """
    Create a post on LinkedIn.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create a LinkedIn post."""
        title = request.data.get("title", "").strip()
        text = request.data.get("text", "").strip()
        media_urns = request.data.get(
            "media_urns", []
        )  # List of asset URNs from media upload

        if not text:
            return Response(
                {"error": "Post text is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if len(text) > 3000:
            return Response(
                {"error": "Post text cannot exceed 3000 characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate title length if provided
        if title and len(title) > LINKEDIN_TITLE_MAX_LENGTH:
            return Response(
                {"error": f"Title cannot exceed {LINKEDIN_TITLE_MAX_LENGTH} chars"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate media_urns is a list
        if media_urns and not isinstance(media_urns, list):
            media_urns = [media_urns]

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if this is a test profile
        if profile.access_token == TEST_ACCESS_TOKEN:
            # Simulate posting for test mode
            logger.info(f"Test LinkedIn post by {request.user.email}: {text[:50]}...")

            # Create a ContentCalendar entry for the published post
            post_title = (
                title
                if title
                else f"LinkedIn Post - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            )
            content = ContentCalendar.objects.create(
                user=request.user,
                title=post_title,
                content=text,
                media_urls=media_urns,  # Store media URNs
                platforms=["linkedin"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "test_mode": True,
                    "message": "Post simulated in test mode",
                    "has_media": len(media_urns) > 0,
                },
            )
            content.social_profiles.add(profile)

            # Create an automation task record
            task = AutomationTask.objects.create(
                user=request.user,
                task_type="social_post",
                status="completed",
                payload={
                    "text": text,
                    "platform": "linkedin",
                    "media_count": len(media_urns),
                },
                result={"test_mode": True, "message": "Post simulated in test mode"},
            )

            return Response(
                {
                    "message": "Post created successfully (Test Mode)",
                    "test_mode": True,
                    "task_id": task.id,
                    "content_id": content.id,
                }
            )

        try:
            # Get valid access token (auto-refresh if needed)
            access_token = profile.get_valid_access_token()

            # Create the post (with optional media)
            result = linkedin_service.create_share(
                access_token=access_token,
                user_urn=profile.profile_id,
                text=text,
                image_urns=media_urns if media_urns else None,
            )

            # Create a ContentCalendar entry for the published post
            post_title = (
                title
                if title
                else f"LinkedIn Post - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            )
            content = ContentCalendar.objects.create(
                user=request.user,
                title=post_title,
                content=text,
                media_urls=media_urns,  # Store media URNs
                platforms=["linkedin"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results=result,
            )
            content.social_profiles.add(profile)

            # Create an automation task record
            task = AutomationTask.objects.create(
                user=request.user,
                task_type="social_post",
                status="completed",
                payload={
                    "text": text,
                    "platform": "linkedin",
                    "media_count": len(media_urns),
                },
                result=result,
            )

            logger.info(
                f"LinkedIn post created by {request.user.email} "
                f"(media: {len(media_urns)})"
            )

            return Response(
                {
                    "message": "Post created successfully",
                    "post_id": result.get("id"),
                    "task_id": task.id,
                    "content_id": content.id,
                    "has_media": len(media_urns) > 0,
                }
            )

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"LinkedIn post failed: {e}")

            # Create a failed task record
            AutomationTask.objects.create(
                user=request.user,
                task_type="social_post",
                status="failed",
                payload={
                    "text": text,
                    "platform": "linkedin",
                    "media_count": len(media_urns),
                },
                result={"error": str(e)},
            )

            return Response(
                {"error": f"Failed to create post: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInCarouselPostView(APIView):
    """
    Create a multi-image (carousel) post on LinkedIn.

    LinkedIn supports up to 9 images in a single post, allowing users
    to swipe through them. This endpoint provides a carousel experience
    similar to Facebook.

    Note: LinkedIn also supports document carousels (PDFs) which display
    as swipeable pages. For document carousels, use the regular post
    endpoint with a document URN.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create a multi-image post on LinkedIn.

        Request body:
        - text: Post text (required, max 3000 chars)
        - media_urns: List of pre-uploaded image asset URNs (2-9 items)
        - title: Optional title for the post
        """
        text = request.data.get("text", "").strip()
        media_urns = request.data.get("media_urns", [])
        title = request.data.get("title", "").strip()

        if not text:
            return Response(
                {"error": "Post text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(text) > 3000:
            return Response(
                {"error": "Post text cannot exceed 3000 characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if title and len(title) > LINKEDIN_TITLE_MAX_LENGTH:
            return Response(
                {"error": f"Title cannot exceed {LINKEDIN_TITLE_MAX_LENGTH} chars"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate media_urns
        if not media_urns:
            return Response(
                {"error": "media_urns is required for carousel posts"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(media_urns, list):
            media_urns = [media_urns]

        if len(media_urns) < 2:
            return Response(
                {"error": "Carousel posts require at least 2 images"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(media_urns) > 9:
            return Response(
                {"error": "LinkedIn supports maximum 9 images per post"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode - either test access token OR placeholder media URNs
        is_test_mode = profile.access_token == TEST_ACCESS_TOKEN or all(
            str(urn).startswith("test_") for urn in media_urns
        )

        if is_test_mode:
            test_post_id = f"test_carousel_{uuid.uuid4().hex[:8]}"
            logger.info(
                f"Test LinkedIn carousel by {request.user.email}: {text[:50]}..."
            )

            # Create a ContentCalendar entry
            post_title = (
                title
                if title
                else f"[Carousel] {text[:40]}..."
                if len(text) > 40
                else f"[Carousel] {text}"
            )
            ContentCalendar.objects.create(
                user=request.user,
                title=post_title,
                content=text,
                media_urls=media_urns,
                platforms=["linkedin"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "linkedin": {
                        "test_mode": True,
                        "post_id": test_post_id,
                        "type": "carousel",
                        "image_count": len(media_urns),
                    }
                },
            )

            return Response(
                {
                    "test_mode": True,
                    "message": "Carousel post simulated in test mode",
                    "post_id": test_post_id,
                    "id": test_post_id,
                    "image_count": len(media_urns),
                }
            )

        try:
            # Get valid access token
            access_token = profile.get_valid_access_token()

            # Create post with multiple images
            result = linkedin_service.create_share(
                access_token=access_token,
                user_urn=profile.profile_id,
                text=text,
                image_urns=media_urns,
            )

            # Store in ContentCalendar
            post_title = (
                title
                if title
                else f"[Carousel] {text[:40]}..."
                if len(text) > 40
                else f"[Carousel] {text}"
            )
            content = ContentCalendar.objects.create(
                user=request.user,
                title=post_title,
                content=text,
                media_urls=media_urns,
                platforms=["linkedin"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "linkedin": result,
                    "type": "carousel",
                    "image_count": len(media_urns),
                },
            )
            content.social_profiles.add(profile)

            logger.info(
                f"LinkedIn carousel created by {request.user.email} "
                f"(images: {len(media_urns)})"
            )

            return Response(
                {
                    "success": True,
                    "post_id": result.get("id"),
                    "message": "Carousel posted to LinkedIn successfully",
                    "image_count": len(media_urns),
                    **result,
                }
            )

        except Exception as e:
            logger.error(f"LinkedIn carousel post failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInMediaUploadView(APIView):
    """
    Upload media (images, videos, or documents) to LinkedIn for use in posts.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Upload an image or video to LinkedIn.

        Accepts either:
        - A file upload (multipart/form-data with 'media' or 'image' field)
        - An image URL (JSON with 'image_url' field)

        Returns the asset URN to use when creating a post with media.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for file upload
        # Try 'media' first, then 'image' for backward compatibility
        media_file = request.FILES.get("media") or request.FILES.get("image")

        if media_file:
            content_type = media_file.content_type
            is_video = content_type in VIDEO_TYPES
            is_image = content_type in IMAGE_TYPES
            is_document = content_type in DOCUMENT_TYPES

            if not is_video and not is_image and not is_document:
                allowed = "JPEG, PNG, GIF, MP4, PDF, DOC, DOCX, PPT, PPTX"
                return Response(
                    {"error": f"Invalid file type: {content_type}. Allowed: {allowed}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate file size
            if is_video:
                max_size = MAX_VIDEO_SIZE
                size_label = "500MB"
            elif is_document:
                max_size = MAX_DOCUMENT_SIZE
                size_label = "100MB"
            else:
                max_size = MAX_IMAGE_SIZE
                size_label = "8MB"

            if media_file.size > max_size:
                return Response(
                    {"error": f"File too large. Maximum size is {size_label}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if test mode
            if profile.access_token == TEST_ACCESS_TOKEN:
                if is_video:
                    media_type = "video"
                elif is_document:
                    media_type = "document"
                else:
                    media_type = "image"
                asset_id = f"test-{media_type}-{uuid.uuid4().hex[:12]}"
                test_asset_urn = f"urn:li:digitalmediaAsset:{asset_id}"
                logger.info(
                    f"Test LinkedIn {media_type} upload by {request.user.email}"
                )
                return Response(
                    {
                        "asset_urn": test_asset_urn,
                        "media_type": media_type,
                        "test_mode": True,
                        "status": "PROCESSING"
                        if (is_video or is_document)
                        else "READY",
                        "message": f"{media_type.capitalize()} upload simulated",
                    }
                )

            try:
                access_token = profile.get_valid_access_token()
                file_data = media_file.read()

                if is_video:
                    # Video upload
                    result = linkedin_service.upload_video_file(
                        access_token, profile.profile_id, file_data, content_type
                    )
                    logger.info(
                        f"LinkedIn video uploaded by {request.user.email}: "
                        f"{result['asset_urn']}"
                    )
                    return Response(
                        {
                            "asset_urn": result["asset_urn"],
                            "media_type": "video",
                            "status": result["status"],
                            "message": "Video uploaded. Processing may take a few min.",
                        }
                    )
                elif is_document:
                    # Document upload
                    result = linkedin_service.upload_document_file(
                        access_token,
                        profile.profile_id,
                        file_data,
                        content_type,
                        filename=media_file.name,
                    )
                    logger.info(
                        f"LinkedIn document uploaded by {request.user.email}: "
                        f"{result['document_urn']}"
                    )
                    return Response(
                        {
                            "asset_urn": result["document_urn"],
                            "media_type": "document",
                            "status": result["status"],
                            "message": "Document uploaded. Processing.",
                        }
                    )
                else:
                    # Image upload
                    upload_info = linkedin_service.register_image_upload(
                        access_token, profile.profile_id
                    )
                    upload_url = upload_info.get("upload_url")
                    asset_urn = upload_info.get("asset_urn")

                    if not upload_url or not asset_urn:
                        return Response(
                            {"error": "Failed to get upload URL from LinkedIn"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

                    linkedin_service.upload_image(upload_url, file_data, content_type)
                    logger.info(
                        f"LinkedIn image uploaded by {request.user.email}: {asset_urn}"
                    )

                    return Response(
                        {
                            "asset_urn": asset_urn,
                            "media_type": "image",
                            "status": "READY",
                            "message": "Image uploaded successfully",
                        }
                    )

            except Exception as e:
                logger.error(f"LinkedIn media upload failed: {e}")
                return Response(
                    {"error": f"Failed to upload media: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Handle URL-based upload (images only)
        image_url = request.data.get("image_url")
        if image_url:
            # Check if test mode
            if profile.access_token == TEST_ACCESS_TOKEN:
                asset_id = f"test-url-{uuid.uuid4().hex[:12]}"
                test_asset_urn = f"urn:li:digitalmediaAsset:{asset_id}"
                logger.info(f"Test LinkedIn URL upload by {request.user.email}")
                return Response(
                    {
                        "asset_urn": test_asset_urn,
                        "media_type": "image",
                        "test_mode": True,
                        "status": "READY",
                        "message": "Image upload simulated in test mode",
                    }
                )

            try:
                access_token = profile.get_valid_access_token()
                asset_urn = linkedin_service.upload_image_from_url(
                    access_token, profile.profile_id, image_url
                )

                logger.info(
                    f"LinkedIn image uploaded from URL by {request.user.email}: "
                    f"{asset_urn}"
                )

                return Response(
                    {
                        "asset_urn": asset_urn,
                        "media_type": "image",
                        "status": "READY",
                        "message": "Image uploaded successfully",
                    }
                )

            except Exception as e:
                logger.error(f"LinkedIn media upload from URL failed: {e}")
                return Response(
                    {"error": f"Failed to upload image: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {"error": "No media provided. Send 'media', 'image', or 'image_url'"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LinkedInVideoStatusView(APIView):
    """
    Check the processing status of an uploaded video.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, asset_urn):
        """
        Check video processing status.

        Args:
            asset_urn: The asset URN returned from video upload

        Returns:
            Status: PROCESSING, READY, or FAILED
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            return Response(
                {
                    "asset_urn": asset_urn,
                    "status": "READY",
                    "test_mode": True,
                    "message": "Video ready (test mode)",
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            result = linkedin_service.check_video_status(access_token, asset_urn)

            return Response(
                {
                    "asset_urn": result["asset_urn"],
                    "status": result["status"],
                    "message": f"Video status: {result['status']}",
                }
            )

        except Exception as e:
            logger.error(f"LinkedIn video status check failed: {e}")
            return Response(
                {"error": f"Failed to check video status: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInDocumentStatusView(APIView):
    """
    Check the processing status of an uploaded document.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, document_urn):
        """
        Check document processing status.

        Args:
            document_urn: The document URN returned from document upload

        Returns:
            Status: PROCESSING, AVAILABLE, or FAILED
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            return Response(
                {
                    "document_urn": document_urn,
                    "status": "AVAILABLE",
                    "test_mode": True,
                    "message": "Document ready (test mode)",
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            result = linkedin_service.check_document_status(access_token, document_urn)

            return Response(
                {
                    "document_urn": result["document_urn"],
                    "status": result["status"],
                    "download_url": result.get("download_url"),
                    "message": f"Document status: {result['status']}",
                }
            )

        except Exception as e:
            logger.error(f"LinkedIn document status check failed: {e}")
            return Response(
                {"error": f"Failed to check document status: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInAnalyticsView(APIView):
    """
    Get analytics and engagement metrics for LinkedIn posts.

    GET /linkedin/analytics/ - Get user profile and post analytics summary
    GET /linkedin/analytics/<post_urn>/ - Get metrics for a specific post
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, post_urn=None):
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            logger.info(f"Test mode analytics request by {request.user.email}")

            if post_urn:
                # Return mock metrics for a specific post
                return Response(
                    {
                        "test_mode": True,
                        "post_urn": post_urn,
                        "text": "Test post content",
                        "created_time": "2026-01-16T12:00:00Z",
                        "metrics": {
                            "likes": 28,
                            "comments": 5,
                            "shares": 3,
                            "impressions": 450,
                        },
                    }
                )
            else:
                # Return mock user analytics
                return Response(
                    {
                        "test_mode": True,
                        "profile": {
                            "name": "Test User",
                            "email": "test@example.com",
                            "picture": None,
                        },
                        "network": {
                            "connections": 500,
                        },
                        "posts": [
                            {
                                "post_urn": "urn:li:share:test1",
                                "text": "First test post on LinkedIn!",
                                "created_time": 1705402800000,
                                "metrics": {
                                    "likes": 28,
                                    "comments": 5,
                                    "shares": 3,
                                    "impressions": 450,
                                },
                            },
                            {
                                "post_urn": "urn:li:share:test2",
                                "text": "Second test post about our product",
                                "created_time": 1705316400000,
                                "metrics": {
                                    "likes": 42,
                                    "comments": 8,
                                    "shares": 6,
                                    "impressions": 720,
                                },
                            },
                        ],
                        "totals": {
                            "total_posts": 2,
                            "total_likes": 70,
                            "total_comments": 13,
                            "engagement_rate": 4.15,
                        },
                    }
                )

        try:
            access_token = profile.get_valid_access_token()
            user_urn = profile.profile_id

            if post_urn:
                # Get metrics for a specific post
                metrics = linkedin_service.get_share_statistics(access_token, post_urn)
                return Response(
                    {
                        "post_urn": post_urn,
                        "metrics": metrics,
                    }
                )
            else:
                # Get full analytics summary
                analytics = linkedin_service.get_analytics_summary(
                    access_token, user_urn
                )
                return Response(analytics)

        except Exception as e:
            logger.error(f"Failed to get LinkedIn analytics: {e}")
            return Response(
                {"error": f"Failed to get analytics: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInDeletePostView(APIView):
    """
    Delete a LinkedIn share/post.

    DELETE /linkedin/post/<post_urn>/ - Delete a post
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, post_urn):
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            logger.info(f"Test mode post deletion by {request.user.email}: {post_urn}")

            # Delete from ContentCalendar
            deleted_count = 0
            for calendar_entry in ContentCalendar.objects.filter(
                user=request.user,
                status="published",
            ):
                # Check if this is a LinkedIn post with matching URN
                if calendar_entry.post_results:
                    post_id = calendar_entry.post_results.get(
                        "id"
                    ) or calendar_entry.post_results.get("post_urn")
                    if post_id == post_urn:
                        # Verify it's a LinkedIn post
                        if hasattr(calendar_entry, "platforms") and "linkedin" in (
                            calendar_entry.platforms or []
                        ):
                            calendar_entry.delete()
                            deleted_count = 1
                            break
                        elif calendar_entry.social_profiles.filter(
                            platform="linkedin"
                        ).exists():
                            calendar_entry.delete()
                            deleted_count = 1
                            break

            return Response(
                {
                    "test_mode": True,
                    "message": "Post deleted (test mode)",
                    "post_urn": post_urn,
                    "calendar_entries_deleted": deleted_count,
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            success = linkedin_service.delete_share(access_token, post_urn)

            if success:
                # Delete from ContentCalendar
                deleted_count = 0
                for calendar_entry in ContentCalendar.objects.filter(
                    user=request.user,
                    status="published",
                ):
                    if calendar_entry.post_results:
                        post_id = calendar_entry.post_results.get(
                            "id"
                        ) or calendar_entry.post_results.get("post_urn")
                        if post_id == post_urn:
                            if hasattr(calendar_entry, "platforms") and "linkedin" in (
                                calendar_entry.platforms or []
                            ):
                                calendar_entry.delete()
                                deleted_count += 1
                                break
                            elif calendar_entry.social_profiles.filter(
                                platform="linkedin"
                            ).exists():
                                calendar_entry.delete()
                                deleted_count += 1
                                break

                logger.info(
                    f"LinkedIn post deleted by {request.user.email}: {post_urn}"
                )
                return Response(
                    {
                        "message": "Post deleted successfully",
                        "post_urn": post_urn,
                        "calendar_entries_deleted": deleted_count,
                    }
                )
            else:
                return Response(
                    {"error": "Failed to delete post"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            logger.error(f"Failed to delete LinkedIn post: {e}")
            return Response(
                {"error": f"Failed to delete post: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LinkedInWebhookView(APIView):
    """
    Handle LinkedIn webhook events.

    LinkedIn sends webhooks for:
    - Share reactions (likes)
    - Share comments
    - Mentions
    - Connection updates

    Docs: https://learn.microsoft.com/en-us/linkedin/
        marketing/integrations/community-management/webhooks

    Note: Webhooks must be registered via LinkedIn Developer Portal.
    """

    # Webhooks don't require user authentication - they use signature validation
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        """
        Handle incoming webhook events from LinkedIn.

        LinkedIn sends events in this format:
        {
            "resource": "urn:li:share:123456",
            "resourceEvent": "CREATED|UPDATED|DELETED",
            "resourceOwner": "urn:li:person:ABC123",
            "triggeredAt": 1609459200000,
            "topic": "shares|comments|reactions",
            "payload": { ... }
        }
        """
        import hmac
        import hashlib
        import base64

        # Validate LinkedIn webhook signature
        signature_header = request.headers.get("X-LI-Signature", "")

        if not signature_header:
            logger.warning("LinkedIn webhook received without signature")
            # For development, we may still process the event
            # In production, you should require signature validation

        # Get LinkedIn client secret for signature validation
        client_secret = getattr(settings, "LINKEDIN_CLIENT_SECRET", None)

        if signature_header and client_secret:
            # Verify HMAC-SHA256 signature
            expected_signature = "sha256=" + base64.b64encode(
                hmac.new(
                    client_secret.encode("utf-8"),
                    request.body,
                    hashlib.sha256,
                ).digest()
            ).decode("utf-8")

            if not hmac.compare_digest(signature_header, expected_signature):
                logger.warning("LinkedIn webhook signature validation failed")
                return Response(
                    {"error": "Invalid signature"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        # Process the webhook event
        event_data = request.data
        logger.info(f"LinkedIn webhook event received: {event_data}")

        # Store event for processing
        from .models import LinkedInWebhookEvent

        # Extract event details
        resource = event_data.get("resource", "")
        resource_owner = event_data.get("resourceOwner", "")
        topic = event_data.get("topic", "")

        # Map LinkedIn topics to our event types
        event_type_map = {
            "reactions": "share_reaction",
            "comments": "share_comment",
            "shares": "share_update",
            "mentions": "mention",
            "connections": "connection_update",
            "organizations": "organization_update",
            "messages": "message",
        }

        event_type = event_type_map.get(topic, topic)

        # Store the event
        LinkedInWebhookEvent.objects.create(
            event_type=event_type,
            for_user_id=resource_owner,
            resource_urn=resource,
            payload=event_data,
        )

        logger.info(f"LinkedIn webhook event stored: {event_type} for {resource_owner}")

        # Return 200 to acknowledge receipt
        return Response({"status": "ok"})


class LinkedInWebhookEventsView(APIView):
    """
    Get stored LinkedIn webhook events for the authenticated user.

    GET /linkedin/webhooks/events/ - List recent webhook events
    POST /linkedin/webhooks/events/ - Mark events as read
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import LinkedInWebhookEvent

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "events": [
                        {
                            "id": 1,
                            "event_type": "share_reaction",
                            "created_at": "2026-01-16T12:00:00Z",
                            "resource_urn": "urn:li:share:test123",
                            "payload": {
                                "resource": "urn:li:share:test123",
                                "resourceEvent": "CREATED",
                                "topic": "reactions",
                                "actor": {
                                    "name": "Jane Smith",
                                    "reaction_type": "LIKE",
                                },
                            },
                            "read": False,
                        },
                        {
                            "id": 2,
                            "event_type": "share_comment",
                            "created_at": "2026-01-16T11:30:00Z",
                            "resource_urn": "urn:li:comment:test456",
                            "payload": {
                                "resource": "urn:li:comment:test456",
                                "resourceEvent": "CREATED",
                                "topic": "comments",
                                "actor": {
                                    "name": "John Doe",
                                },
                                "comment": {
                                    "text": "Great post! Thanks for sharing.",
                                },
                            },
                            "read": False,
                        },
                        {
                            "id": 3,
                            "event_type": "connection_update",
                            "created_at": "2026-01-16T10:00:00Z",
                            "resource_urn": "urn:li:person:newconnection",
                            "payload": {
                                "topic": "connections",
                                "actor": {
                                    "name": "New Connection",
                                },
                            },
                            "read": True,
                        },
                    ],
                    "unread_count": 2,
                }
            )

        # Get user's LinkedIn ID from profile
        linkedin_user_id = profile.profile_id

        if not linkedin_user_id:
            return Response(
                {
                    "events": [],
                    "unread_count": 0,
                    "message": "No LinkedIn user ID associated with profile",
                }
            )

        # Get recent events for this user
        event_type = request.query_params.get("event_type")
        limit = int(request.query_params.get("limit", 50))

        events_qs = LinkedInWebhookEvent.objects.filter(
            for_user_id=linkedin_user_id
        ).order_by("-created_at")

        if event_type:
            events_qs = events_qs.filter(event_type=event_type)

        events = events_qs[:limit]

        unread_count = LinkedInWebhookEvent.objects.filter(
            for_user_id=linkedin_user_id,
            read=False,
        ).count()

        return Response(
            {
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "created_at": event.created_at.isoformat(),
                        "resource_urn": event.resource_urn,
                        "payload": event.payload,
                        "read": event.read,
                    }
                    for event in events
                ],
                "unread_count": unread_count,
            }
        )

    def post(self, request):
        """Mark events as read."""
        from .models import LinkedInWebhookEvent

        event_ids = request.data.get("event_ids", [])

        if not event_ids:
            return Response(
                {"error": "No event_ids provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="linkedin", status="connected"
            )
            linkedin_user_id = profile.profile_id

            updated = LinkedInWebhookEvent.objects.filter(
                id__in=event_ids,
                for_user_id=linkedin_user_id,
            ).update(read=True)

            return Response(
                {
                    "message": f"Marked {updated} events as read",
                    "updated_count": updated,
                }
            )

        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "LinkedIn account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )


class TwitterMediaUploadView(APIView):
    """
    Upload media (images, videos, or GIFs) to Twitter for use in tweets.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Upload an image, video, or GIF to Twitter.

        Accepts a file upload (multipart/form-data with 'media' field).

        Returns the media_id to use when creating a tweet with media.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for file upload
        media_file = request.FILES.get("media")

        if not media_file:
            return Response(
                {"error": "No media file provided. Use 'media' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = media_file.content_type
        is_image = content_type in TWITTER_IMAGE_TYPES
        is_video = content_type in TWITTER_VIDEO_TYPES
        is_gif = content_type == "image/gif"

        if not is_image and not is_video:
            allowed = "JPEG, PNG, GIF, WEBP (images); MP4, MOV (video)"
            return Response(
                {"error": f"Invalid file type: {content_type}. Allowed: {allowed}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine media category and size limit
        if is_video:
            media_category = "tweet_video"
            max_size = TWITTER_MEDIA_MAX_VIDEO_SIZE
            size_label = "512MB"
        elif is_gif:
            media_category = "tweet_gif"
            max_size = TWITTER_MEDIA_MAX_GIF_SIZE
            size_label = "15MB"
        else:
            media_category = "tweet_image"
            max_size = TWITTER_MEDIA_MAX_IMAGE_SIZE
            size_label = "5MB"

        if media_file.size > max_size:
            return Response(
                {"error": f"File too large. Maximum size is {size_label}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            media_type = "video" if is_video else ("gif" if is_gif else "image")
            test_media_id = f"test-{media_type}-{uuid.uuid4().hex[:12]}"
            logger.info(f"Test Twitter {media_type} upload by {request.user.email}")
            return Response(
                {
                    "media_id": test_media_id,
                    "media_id_string": test_media_id,
                    "media_type": media_type,
                    "test_mode": True,
                    "status": "PROCESSING" if is_video else "READY",
                    "message": f"{media_type.capitalize()} upload simulated",
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            file_data = media_file.read()

            result = twitter_service.upload_media(
                access_token=access_token,
                media_data=file_data,
                media_type=content_type,
                media_category=media_category,
            )

            media_type = "video" if is_video else ("gif" if is_gif else "image")
            processing_msg = (
                "Processing may take a few minutes."
                if result.get("status") == "PROCESSING"
                else ""
            )

            logger.info(
                f"Twitter {media_type} uploaded by {request.user.email}: "
                f"{result.get('media_id_string')}"
            )

            return Response(
                {
                    "media_id": result.get("media_id"),
                    "media_id_string": result.get("media_id_string"),
                    "media_type": media_type,
                    "status": result.get("status", "READY"),
                    "message": f"{media_type.capitalize()} uploaded. {processing_msg}",
                }
            )

        except Exception as e:
            logger.error(f"Twitter media upload failed: {e}")
            return Response(
                {"error": f"Failed to upload media: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwitterMediaStatusView(APIView):
    """
    Check the processing status of uploaded Twitter media.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, media_id):
        """
        Check media processing status.

        Args:
            media_id: The media_id_string returned from media upload

        Returns:
            Status: pending, in_progress, succeeded, failed
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            return Response(
                {
                    "media_id": media_id,
                    "state": "succeeded",
                    "test_mode": True,
                    "message": "Media ready (test mode)",
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            result = twitter_service.get_media_status(access_token, media_id)

            return Response(
                {
                    "media_id": result["media_id"],
                    "state": result["state"],
                    "check_after_secs": result.get("check_after_secs"),
                    "progress_percent": result.get("progress_percent"),
                    "error": result.get("error"),
                    "message": f"Media status: {result['state']}",
                }
            )

        except Exception as e:
            logger.error(f"Twitter media status check failed: {e}")
            return Response(
                {"error": f"Failed to check media status: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AutomationTaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing automation tasks.
    """

    serializer_class = AutomationTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AutomationTask.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ContentCalendarViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing content calendar.
    """

    serializer_class = ContentCalendarSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ContentCalendar.objects.filter(user=self.request.user)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by platform
        platform = self.request.query_params.get("platform")
        if platform:
            queryset = queryset.filter(platforms__contains=[platform])

        # Filter by date range
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(scheduled_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(scheduled_date__lte=end_date)

        queryset = queryset.order_by("-updated_at")

        # Apply limit if specified
        limit = self.request.query_params.get("limit")
        if limit:
            try:
                limit_int = int(limit)
                if limit_int > 0:
                    queryset = queryset[:limit_int]
            except ValueError:
                # If limit is not a valid integer, ignore it and return full queryset
                pass

        return queryset

    def _sync_platform_profiles(self, instance):
        """
        Sync social profiles with selected platforms.

        Adds or removes social profiles based on the platforms list.
        """
        # Handle LinkedIn platform
        linkedin_profiles_on_instance = instance.social_profiles.filter(
            platform="linkedin"
        )

        if "linkedin" in instance.platforms:
            # Ensure the user's connected LinkedIn profile is attached
            linkedin_profile = SocialProfile.objects.filter(
                user=self.request.user, platform="linkedin", status="connected"
            ).first()

            if linkedin_profile:
                # Add if not already linked
                if not linkedin_profiles_on_instance.filter(
                    id=linkedin_profile.id
                ).exists():
                    instance.social_profiles.add(linkedin_profile)
        else:
            # LinkedIn removed from platforms - remove any LinkedIn profiles
            if linkedin_profiles_on_instance.exists():
                instance.social_profiles.remove(*linkedin_profiles_on_instance)

        # Handle Twitter platform
        twitter_profiles_on_instance = instance.social_profiles.filter(
            platform="twitter"
        )

        if "twitter" in instance.platforms:
            # Ensure the user's connected Twitter profile is attached
            twitter_profile = SocialProfile.objects.filter(
                user=self.request.user, platform="twitter", status="connected"
            ).first()

            if twitter_profile:
                # Add if not already linked
                if not twitter_profiles_on_instance.filter(
                    id=twitter_profile.id
                ).exists():
                    instance.social_profiles.add(twitter_profile)
        else:
            # Twitter removed from platforms - remove any Twitter profiles
            if twitter_profiles_on_instance.exists():
                instance.social_profiles.remove(*twitter_profiles_on_instance)

        # Handle Facebook platform
        facebook_profiles_on_instance = instance.social_profiles.filter(
            platform="facebook"
        )

        if "facebook" in instance.platforms:
            # Ensure the user's connected Facebook profile is attached
            facebook_profile = SocialProfile.objects.filter(
                user=self.request.user, platform="facebook", status="connected"
            ).first()

            if facebook_profile:
                # Add if not already linked
                if not facebook_profiles_on_instance.filter(
                    id=facebook_profile.id
                ).exists():
                    instance.social_profiles.add(facebook_profile)
        else:
            # Facebook removed from platforms - remove any Facebook profiles
            if facebook_profiles_on_instance.exists():
                instance.social_profiles.remove(*facebook_profiles_on_instance)

        # Handle Instagram platform
        instagram_profiles_on_instance = instance.social_profiles.filter(
            platform="instagram"
        )

        if "instagram" in instance.platforms:
            # Ensure the user's connected Instagram profile is attached
            instagram_profile = SocialProfile.objects.filter(
                user=self.request.user, platform="instagram", status="connected"
            ).first()

            if instagram_profile:
                # Add if not already linked
                if not instagram_profiles_on_instance.filter(
                    id=instagram_profile.id
                ).exists():
                    instance.social_profiles.add(instagram_profile)
        else:
            # Instagram removed from platforms - remove any Instagram profiles
            if instagram_profiles_on_instance.exists():
                instance.social_profiles.remove(*instagram_profiles_on_instance)

    def perform_create(self, serializer):
        """Auto-link social profiles based on selected platforms."""
        instance = serializer.save(user=self.request.user)
        self._sync_platform_profiles(instance)

    def update(self, request, *args, **kwargs):
        """Update a scheduled post. Only draft/scheduled posts can be edited."""
        instance = self.get_object()

        # Prevent editing published, failed, or cancelled posts
        if instance.status not in EDITABLE_STATUSES:
            return Response(
                {"error": f"Cannot edit a post with status '{instance.status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        """Handle platform changes when updating a post."""
        instance = serializer.save()
        self._sync_platform_profiles(instance)

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """Get all scheduled posts (pending and overdue) ordered by date."""
        # Show all scheduled posts - both upcoming and overdue ones
        # that haven't been published
        upcoming = ContentCalendar.objects.filter(
            user=request.user,
            status="scheduled",
        ).order_by("scheduled_date")

        serializer = self.get_serializer(upcoming, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Manually publish a scheduled post immediately."""
        from .publish_helpers import publish_content, update_content_status

        content = self.get_object()

        if content.status == "published":
            return Response(
                {"error": "Content already published"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results, errors = publish_content(content, log_prefix="Manual ")
        update_content_status(content, results, errors)

        return Response(
            {
                "message": "Publishing completed"
                if not errors
                else "Publishing completed with some errors",
                "status": content.status,
                "results": results,
                "errors": errors,
            }
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a scheduled post."""
        content = self.get_object()

        if content.status == "published":
            return Response(
                {"error": "Cannot cancel a published post"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content.status = "cancelled"
        content.save()

        return Response(
            {"message": "Post cancelled successfully", "status": content.status}
        )


# =============================================================================
# Twitter/X Integration Views
# =============================================================================


class TwitterConnectView(APIView):
    """
    Initiate Twitter OAuth 2.0 flow with PKCE.

    Returns the authorization URL that the frontend should redirect to.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .services import twitter_service

        if not twitter_service.is_configured:
            return Response(
                {"error": "Twitter OAuth not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Generate PKCE code verifier and challenge
        code_verifier, code_challenge = twitter_service.generate_pkce_pair()

        # Generate unique state for CSRF protection
        state = str(uuid.uuid4())

        # Store state and code_verifier in session/database
        OAuthState.objects.create(
            user=request.user,
            platform="twitter",
            state=state,
            code_verifier=code_verifier,  # Store for token exchange
        )

        try:
            auth_url = twitter_service.get_authorization_url(state, code_challenge)
            return Response({"authorization_url": auth_url})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TwitterCallbackView(APIView):
    """
    Handle Twitter OAuth 2.0 callback.

    Exchanges authorization code for tokens and creates/updates SocialProfile.
    """

    # No authentication required - this is a callback from Twitter
    permission_classes = []

    def get(self, request):
        from .services import twitter_service

        code = request.GET.get("code")
        state = request.GET.get("state")
        error = request.GET.get("error")

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

        if error:
            logger.error(f"Twitter OAuth error: {error}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=twitter_auth_failed"
            )

        if not code or not state:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=missing_params"
            )

        # Validate state and get code_verifier
        try:
            oauth_state = OAuthState.objects.get(
                state=state,
                platform="twitter",
                used=False,
            )
        except OAuthState.DoesNotExist:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=invalid_state"
            )

        # Mark state as used
        oauth_state.used = True
        oauth_state.save()

        # Check if state is expired (5 minutes)
        if (timezone.now() - oauth_state.created_at).total_seconds() > 300:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=state_expired"
            )

        try:
            # Exchange code for tokens with PKCE verifier
            token_data = twitter_service.exchange_code_for_token(
                code, oauth_state.code_verifier
            )

            # Get user info
            user_info = twitter_service.get_user_info(token_data["access_token"])

            # Create or update social profile
            _, created = SocialProfile.objects.update_or_create(
                user=oauth_state.user,
                platform="twitter",
                defaults={
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token"),
                    "token_expires_at": token_data.get("expires_at"),
                    "profile_id": user_info.get("id"),
                    "profile_name": user_info.get("name"),
                    "profile_url": f"https://twitter.com/{user_info.get('username')}",
                    "profile_image_url": user_info.get("profile_image_url"),
                    "status": "connected",
                },
            )

            action = "created" if created else "updated"
            logger.info(
                f"Twitter profile {action} for user {oauth_state.user.email}: "
                f"@{user_info.get('username')}"
            )

            return HttpResponseRedirect(
                f"{frontend_url}/automation?success=true&platform=twitter"
            )

        except Exception as e:
            logger.error(f"Twitter OAuth callback failed: {e}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=twitter_token_exchange_failed"
            )


class TwitterDisconnectView(APIView):
    """Disconnect Twitter account."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services import twitter_service

        try:
            profile = SocialProfile.objects.get(user=request.user, platform="twitter")

            # Revoke token if possible
            if profile.access_token:
                try:
                    twitter_service.revoke_token(profile.access_token)
                except Exception as e:
                    logger.warning(f"Failed to revoke Twitter token: {e}")

            # Clear tokens and mark as disconnected
            profile.access_token = None
            profile.refresh_token = None
            profile.token_expires_at = None
            profile.status = "disconnected"
            profile.save()

            return Response({"message": "Twitter account disconnected successfully"})

        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "No Twitter account connected"},
                status=status.HTTP_404_NOT_FOUND,
            )


class TwitterTestConnectView(APIView):
    """
    Create a mock Twitter connection for testing (DEBUG mode only).

    This allows testing the Twitter integration without real OAuth.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not settings.DEBUG:
            return Response(
                {"error": "Test connect only available in DEBUG mode"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Create mock profile
        profile, created = SocialProfile.objects.update_or_create(
            user=request.user,
            platform="twitter",
            defaults={
                "access_token": TWITTER_TEST_ACCESS_TOKEN,
                "refresh_token": TWITTER_TEST_REFRESH_TOKEN,
                "token_expires_at": timezone.now() + timedelta(days=60),
                "profile_id": f"test_twitter_{request.user.id}",
                "profile_name": f"Test User ({request.user.email})",
                "profile_url": f"https://twitter.com/test_user_{request.user.id}",
                "profile_image_url": None,
                "status": "connected",
            },
        )

        return Response(
            {
                "message": "Test Twitter connection created",
                "profile_name": profile.profile_name,
                "is_test_mode": True,
            }
        )


class TwitterPostView(APIView):
    """
    Create a tweet on Twitter/X.

    Requires a connected Twitter account.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services import twitter_service

        title = request.data.get("title", "").strip()
        text = request.data.get("text", "").strip()
        media_ids = request.data.get("media_ids", [])

        if not text:
            return Response(
                {"error": "Tweet text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate length
        validation = twitter_service.validate_tweet_length(text)
        if not validation["is_valid"]:
            return Response(
                {
                    "error": f"Tweet exceeds max length of {validation['max_length']} "
                    f"characters (current: {validation['length']})"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate media_ids is a list
        if media_ids and not isinstance(media_ids, list):
            media_ids = [media_ids]

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            logger.info(f"Test mode tweet by {request.user.email}: {text[:50]}...")

            # Create a ContentCalendar entry for the published tweet
            post_title = (
                title
                if title
                else f"Twitter Post - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            )
            content = ContentCalendar.objects.create(
                user=request.user,
                title=post_title,
                content=text,
                media_urls=media_ids,
                platforms=["twitter"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "test_mode": True,
                    "message": "Tweet simulated in test mode",
                    "has_media": len(media_ids) > 0,
                },
            )
            content.social_profiles.add(profile)

            # Create an automation task record
            task = AutomationTask.objects.create(
                user=request.user,
                task_type="social_post",
                status="completed",
                payload={
                    "text": text,
                    "platform": "twitter",
                    "media_count": len(media_ids),
                },
                result={"test_mode": True, "message": "Tweet simulated in test mode"},
            )

            return Response(
                {
                    "message": "Tweet simulated (test mode)",
                    "test_mode": True,
                    "task_id": task.id,
                    "content_id": content.id,
                    "tweet": {
                        "id": f"test_tweet_{uuid.uuid4().hex[:12]}",
                        "text": text,
                    },
                }
            )

        try:
            # Get valid access token (refresh if needed)
            access_token = profile.get_valid_access_token()

            # Create tweet
            result = twitter_service.create_tweet(
                access_token=access_token,
                text=text,
                reply_to_id=request.data.get("reply_to_id"),
                quote_tweet_id=request.data.get("quote_tweet_id"),
                media_ids=media_ids if media_ids else None,
            )

            # Create a ContentCalendar entry for the published tweet
            post_title = (
                title
                if title
                else f"Twitter Post - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            )
            content = ContentCalendar.objects.create(
                user=request.user,
                title=post_title,
                content=text,
                media_urls=media_ids,
                platforms=["twitter"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results=result,
            )
            content.social_profiles.add(profile)

            # Create an automation task record
            task = AutomationTask.objects.create(
                user=request.user,
                task_type="social_post",
                status="completed",
                payload={
                    "text": text,
                    "platform": "twitter",
                    "media_count": len(media_ids),
                },
                result=result,
            )

            logger.info(
                f"Twitter tweet created by {request.user.email} "
                f"(media: {len(media_ids)})"
            )

            return Response(
                {
                    "message": "Tweet posted successfully",
                    "tweet_id": result.get("id"),
                    "task_id": task.id,
                    "content_id": content.id,
                    "has_media": len(media_ids) > 0,
                    "tweet": result,
                }
            )

        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            return Response(
                {"error": f"Failed to post tweet: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwitterCarouselPostView(APIView):
    """
    Create a multi-image tweet on Twitter/X.

    Twitter supports up to 4 images per tweet. This endpoint provides
    a carousel-like experience similar to Facebook's carousel posts.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create a multi-image tweet.

        Request body:
        - text: Tweet text (required)
        - media_ids: List of pre-uploaded media IDs (2-4 items)
        """
        from .services import twitter_service

        text = request.data.get("text", "").strip()
        media_ids = request.data.get("media_ids", [])

        if not text:
            return Response(
                {"error": "Tweet text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate length
        validation = twitter_service.validate_tweet_length(text)
        if not validation["is_valid"]:
            return Response(
                {
                    "error": f"Tweet exceeds max length of {validation['max_length']} "
                    f"characters (current: {validation['length']})"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate media_ids
        if not media_ids:
            return Response(
                {"error": "media_ids is required for carousel posts"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(media_ids, list):
            media_ids = [media_ids]

        if len(media_ids) < 2:
            return Response(
                {"error": "Carousel posts require at least 2 images"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(media_ids) > 4:
            return Response(
                {"error": "Twitter supports maximum 4 images per tweet"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode - either test access token OR placeholder media IDs
        is_test_mode = profile.access_token == TWITTER_TEST_ACCESS_TOKEN or all(
            str(mid).startswith("test_") for mid in media_ids
        )

        if is_test_mode:
            test_tweet_id = f"test_carousel_{uuid.uuid4().hex[:8]}"
            logger.info(f"Test carousel tweet by {request.user.email}: {text[:50]}...")

            # Create a ContentCalendar entry
            ContentCalendar.objects.create(
                user=request.user,
                title=f"[Carousel] {text[:40]}..."
                if len(text) > 40
                else f"[Carousel] {text}",
                content=text,
                media_urls=media_ids,
                platforms=["twitter"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "twitter": {
                        "test_mode": True,
                        "tweet_id": test_tweet_id,
                        "type": "carousel",
                        "image_count": len(media_ids),
                    }
                },
            )

            return Response(
                {
                    "test_mode": True,
                    "message": "Carousel tweet simulated in test mode",
                    "tweet_id": test_tweet_id,
                    "id": test_tweet_id,
                    "image_count": len(media_ids),
                }
            )

        try:
            # Get valid access token
            access_token = profile.get_valid_access_token()

            # Create tweet with multiple images
            result = twitter_service.create_tweet(
                access_token=access_token,
                text=text,
                media_ids=media_ids,
            )

            # Store in ContentCalendar
            ContentCalendar.objects.create(
                user=request.user,
                title=f"[Carousel] {text[:40]}..."
                if len(text) > 40
                else f"[Carousel] {text}",
                content=text,
                media_urls=media_ids,
                platforms=["twitter"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "twitter": result,
                    "type": "carousel",
                    "image_count": len(media_ids),
                },
            )

            return Response(
                {
                    "success": True,
                    "tweet_id": result.get("id"),
                    "message": "Carousel posted to Twitter successfully",
                    "image_count": len(media_ids),
                    **result,
                }
            )

        except Exception as e:
            logger.error(f"Twitter carousel post failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwitterValidateTweetView(APIView):
    """
    Validate tweet text without posting.

    Used for real-time validation in the UI.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services import twitter_service

        text = request.data.get("text", "")
        is_premium = request.data.get("is_premium", False)

        validation = twitter_service.validate_tweet_length(text, is_premium)

        return Response(validation)


class TwitterDeleteTweetView(APIView):
    """
    Delete a tweet by its ID.

    Requires a connected Twitter account.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, tweet_id):
        from .services import twitter_service
        from .constants import TWITTER_TEST_ACCESS_TOKEN

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            logger.info(f"Test mode tweet deletion by {request.user.email}: {tweet_id}")

            # Delete from ContentCalendar
            deleted_count = 0
            for calendar_entry in ContentCalendar.objects.filter(
                user=request.user,
                status="published",
            ):
                # Check if this is a Twitter post with matching ID
                if calendar_entry.post_results:
                    # Twitter stores as tweet.id or just id
                    post_id = None
                    if "tweet" in calendar_entry.post_results:
                        post_id = calendar_entry.post_results.get("tweet", {}).get("id")
                    else:
                        post_id = calendar_entry.post_results.get("id")

                    if post_id == tweet_id:
                        # Verify it's a Twitter post
                        if hasattr(calendar_entry, "platforms") and "twitter" in (
                            calendar_entry.platforms or []
                        ):
                            calendar_entry.delete()
                            deleted_count = 1
                            break
                        elif calendar_entry.social_profiles.filter(
                            platform="twitter"
                        ).exists():
                            calendar_entry.delete()
                            deleted_count = 1
                            break

            return Response(
                {
                    "test_mode": True,
                    "message": "Tweet deleted (test mode)",
                    "tweet_id": tweet_id,
                    "calendar_entries_deleted": deleted_count,
                }
            )

        try:
            access_token = profile.get_valid_access_token()
            success = twitter_service.delete_tweet(access_token, tweet_id)

            if success:
                # Delete from ContentCalendar
                deleted_count = 0
                for calendar_entry in ContentCalendar.objects.filter(
                    user=request.user,
                    status="published",
                ):
                    if calendar_entry.post_results:
                        post_id = None
                        if "tweet" in calendar_entry.post_results:
                            post_id = calendar_entry.post_results.get("tweet", {}).get(
                                "id"
                            )
                        else:
                            post_id = calendar_entry.post_results.get("id")

                        if post_id == tweet_id:
                            if hasattr(calendar_entry, "platforms") and "twitter" in (
                                calendar_entry.platforms or []
                            ):
                                calendar_entry.delete()
                                deleted_count += 1
                                break
                            elif calendar_entry.social_profiles.filter(
                                platform="twitter"
                            ).exists():
                                calendar_entry.delete()
                                deleted_count += 1
                                break

                logger.info(f"Tweet deleted by {request.user.email}: {tweet_id}")
                return Response(
                    {
                        "message": "Tweet deleted successfully",
                        "tweet_id": tweet_id,
                        "calendar_entries_deleted": deleted_count,
                    }
                )
            else:
                return Response(
                    {"error": "Failed to delete tweet"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            logger.error(f"Failed to delete tweet: {e}")
            return Response(
                {"error": f"Failed to delete tweet: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwitterAnalyticsView(APIView):
    """
    Get analytics and metrics for Twitter tweets.

    GET /twitter/analytics/ - Get user profile metrics and recent tweet metrics
    GET /twitter/analytics/<tweet_id>/ - Get metrics for a specific tweet
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, tweet_id=None):
        from .services import twitter_service
        from .constants import TWITTER_TEST_ACCESS_TOKEN

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            logger.info(f"Test mode analytics request by {request.user.email}")

            if tweet_id:
                # Return mock metrics for a specific tweet
                return Response(
                    {
                        "test_mode": True,
                        "tweet_id": tweet_id,
                        "text": "Test tweet content",
                        "created_at": "2026-01-16T12:00:00Z",
                        "metrics": {
                            "impressions": 1250,
                            "likes": 45,
                            "retweets": 12,
                            "replies": 8,
                            "quotes": 3,
                            "bookmarks": 5,
                        },
                    }
                )
            else:
                # Return mock user metrics and recent tweets
                return Response(
                    {
                        "test_mode": True,
                        "user": {
                            "user_id": "test_user_123",
                            "username": "testuser",
                            "name": "Test User",
                            "profile_image_url": None,
                            "metrics": {
                                "followers": 1500,
                                "following": 350,
                                "tweets": 420,
                                "listed": 12,
                            },
                        },
                        "tweets": [
                            {
                                "tweet_id": "test_tweet_1",
                                "text": "First test tweet",
                                "created_at": "2026-01-16T12:00:00Z",
                                "metrics": {
                                    "impressions": 1250,
                                    "likes": 45,
                                    "retweets": 12,
                                    "replies": 8,
                                    "quotes": 3,
                                    "bookmarks": 5,
                                },
                            },
                            {
                                "tweet_id": "test_tweet_2",
                                "text": "Second test tweet",
                                "created_at": "2026-01-15T10:00:00Z",
                                "metrics": {
                                    "impressions": 980,
                                    "likes": 32,
                                    "retweets": 8,
                                    "replies": 5,
                                    "quotes": 1,
                                    "bookmarks": 2,
                                },
                            },
                        ],
                        "totals": {
                            "total_impressions": 2230,
                            "total_likes": 77,
                            "total_retweets": 20,
                            "total_replies": 13,
                            "total_quotes": 4,
                            "total_bookmarks": 7,
                            "engagement_rate": 5.4,
                        },
                    }
                )

        try:
            access_token = profile.get_valid_access_token()

            if tweet_id:
                # Get metrics for a specific tweet
                metrics = twitter_service.get_tweet_metrics(access_token, tweet_id)
                return Response(metrics)
            else:
                # Get user metrics first (more likely to succeed)
                user_metrics = None
                rate_limited = False

                try:
                    user_metrics = twitter_service.get_user_metrics(access_token)
                except Exception as e:
                    error_str = str(e).lower()
                    if (
                        "429" in str(e)
                        or "too many requests" in error_str
                        or "rate" in error_str
                    ):
                        rate_limited = True
                        logger.warning(f"Twitter rate limit hit for user metrics: {e}")
                    else:
                        raise

                # Get tweet IDs from published posts
                published_posts = ContentCalendar.objects.filter(
                    user=request.user,
                    platforms__contains=["twitter"],
                    status="published",
                ).order_by("-published_at")[:20]

                tweet_ids = []
                for post in published_posts:
                    # post_results can have tweet id in different locations
                    post_results = post.post_results or {}
                    # Check twitter nested key first
                    twitter_data = post_results.get("twitter", {})
                    if isinstance(twitter_data, dict) and twitter_data.get("id"):
                        tweet_ids.append(twitter_data["id"])
                    elif post_results.get("id"):
                        tweet_ids.append(post_results["id"])

                # Get metrics for all tweets (skip if rate limited)
                tweets_metrics = []
                if tweet_ids and not rate_limited:
                    try:
                        tweets_metrics = twitter_service.get_multiple_tweet_metrics(
                            access_token, tweet_ids
                        )
                    except Exception as e:
                        error_str = str(e).lower()
                        if (
                            "429" in str(e)
                            or "too many requests" in error_str
                            or "rate" in error_str
                        ):
                            rate_limited = True
                            logger.warning(
                                f"Twitter rate limit hit for tweet metrics: {e}"
                            )
                        else:
                            raise

                # Calculate totals
                totals = {
                    "total_impressions": 0,
                    "total_likes": 0,
                    "total_retweets": 0,
                    "total_replies": 0,
                    "total_quotes": 0,
                    "total_bookmarks": 0,
                }
                for tweet in tweets_metrics:
                    metrics = tweet.get("metrics", {})
                    totals["total_impressions"] += metrics.get("impressions", 0)
                    totals["total_likes"] += metrics.get("likes", 0)
                    totals["total_retweets"] += metrics.get("retweets", 0)
                    totals["total_replies"] += metrics.get("replies", 0)
                    totals["total_quotes"] += metrics.get("quotes", 0)
                    totals["total_bookmarks"] += metrics.get("bookmarks", 0)

                # Calculate engagement rate
                if totals["total_impressions"] > 0:
                    engagements = (
                        totals["total_likes"]
                        + totals["total_retweets"]
                        + totals["total_replies"]
                        + totals["total_quotes"]
                    )
                    totals["engagement_rate"] = round(
                        (engagements / totals["total_impressions"]) * 100, 2
                    )
                else:
                    totals["engagement_rate"] = 0

                response_data = {
                    "user": user_metrics,
                    "tweets": tweets_metrics,
                    "totals": totals,
                }

                # Add rate limit warning if applicable
                if rate_limited:
                    response_data["rate_limited"] = True
                    response_data["rate_limit_message"] = (
                        "Twitter API rate limit reached. Some data may be unavailable. "
                        "Please try again in a few minutes."
                    )

                return Response(response_data)

        except Exception as e:
            logger.error(f"Failed to get Twitter analytics: {e}")
            error_str = str(e).lower()

            # Check if it's a rate limit error
            if (
                "429" in str(e)
                or "too many requests" in error_str
                or "rate" in error_str
            ):
                return Response(
                    {
                        "rate_limited": True,
                        "rate_limit_message": (
                            "Twitter API rate limit reached. "
                            "Please try again in 15 minutes."
                        ),
                        "user": None,
                        "tweets": [],
                        "totals": {
                            "total_impressions": 0,
                            "total_likes": 0,
                            "total_retweets": 0,
                            "total_replies": 0,
                            "total_quotes": 0,
                            "total_bookmarks": 0,
                            "engagement_rate": 0,
                        },
                    },
                    # Return 200 with warning instead of error
                    status=status.HTTP_200_OK,
                )

            return Response(
                {"error": f"Failed to get analytics: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwitterWebhookView(APIView):
    """
    Handle Twitter Account Activity API webhooks.

    GET - CRC challenge validation
    POST - Receive webhook events (likes, retweets, mentions, DMs)

    Note: Requires Twitter Premium or Enterprise tier for Account Activity API.
    """

    # Webhooks don't require user authentication - they use signature validation
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        """
        Handle CRC (Challenge Response Check) for webhook registration.

        Twitter sends a GET request with crc_token parameter.
        We must respond with a HMAC-SHA256 signature of the token.
        """
        import hmac
        import hashlib
        import base64

        crc_token = request.query_params.get("crc_token")

        if not crc_token:
            return Response(
                {"error": "Missing crc_token parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get consumer secret from settings
        consumer_secret = getattr(settings, "TWITTER_CLIENT_SECRET", None)

        if not consumer_secret:
            logger.error("Twitter webhook CRC failed: No client secret configured")
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create HMAC-SHA256 signature
        signature = hmac.new(
            consumer_secret.encode("utf-8"),
            crc_token.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        response_token = base64.b64encode(signature).decode("utf-8")

        logger.info("Twitter webhook CRC challenge validated")
        return Response({"response_token": f"sha256={response_token}"})

    def post(self, request):
        """
        Handle incoming webhook events from Twitter.

        Events can include:
        - tweet_create_events: New tweets/replies/mentions
        - favorite_events: Likes
        - follow_events: New followers
        - direct_message_events: DMs
        - tweet_delete_events: Deleted tweets
        """
        import hmac
        import hashlib
        import base64

        # Validate webhook signature
        signature_header = request.headers.get("X-Twitter-Webhooks-Signature", "")

        if not signature_header:
            logger.warning("Twitter webhook received without signature")
            return Response(
                {"error": "Missing signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        consumer_secret = getattr(settings, "TWITTER_CLIENT_SECRET", None)

        if not consumer_secret:
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Verify signature
        expected_signature = "sha256=" + base64.b64encode(
            hmac.new(
                consumer_secret.encode("utf-8"),
                request.body,
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        if not hmac.compare_digest(signature_header, expected_signature):
            logger.warning("Twitter webhook signature validation failed")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Process the webhook event
        event_data = request.data
        logger.info(f"Twitter webhook event received: {list(event_data.keys())}")

        # Store event for processing
        from .models import TwitterWebhookEvent

        # Handle different event types
        for_user_id = event_data.get("for_user_id")

        if "tweet_create_events" in event_data:
            for tweet in event_data["tweet_create_events"]:
                TwitterWebhookEvent.objects.create(
                    event_type="tweet_create",
                    for_user_id=for_user_id,
                    payload=tweet,
                )
                logger.info(f"Tweet create event stored: {tweet.get('id_str')}")

        if "favorite_events" in event_data:
            for favorite in event_data["favorite_events"]:
                TwitterWebhookEvent.objects.create(
                    event_type="favorite",
                    for_user_id=for_user_id,
                    payload=favorite,
                )
                logger.info("Favorite event stored")

        if "follow_events" in event_data:
            for follow in event_data["follow_events"]:
                TwitterWebhookEvent.objects.create(
                    event_type="follow",
                    for_user_id=for_user_id,
                    payload=follow,
                )
                logger.info("Follow event stored")

        if "direct_message_events" in event_data:
            for dm in event_data["direct_message_events"]:
                TwitterWebhookEvent.objects.create(
                    event_type="direct_message",
                    for_user_id=for_user_id,
                    payload=dm,
                )
                logger.info("DM event stored")

        return Response({"status": "ok"})


class TwitterWebhookEventsView(APIView):
    """
    Get stored webhook events for the authenticated user.

    GET /twitter/webhooks/events/ - List recent webhook events
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import TwitterWebhookEvent
        from .constants import TWITTER_TEST_ACCESS_TOKEN

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "events": [
                        {
                            "id": 1,
                            "event_type": "favorite",
                            "created_at": "2026-01-16T12:00:00Z",
                            "payload": {
                                "user": {"screen_name": "testfan"},
                                "favorited_status": {"text": "Your tweet was liked!"},
                            },
                            "read": False,
                        },
                        {
                            "id": 2,
                            "event_type": "follow",
                            "created_at": "2026-01-16T11:30:00Z",
                            "payload": {
                                "source": {"screen_name": "newfollower"},
                            },
                            "read": False,
                        },
                    ],
                    "unread_count": 2,
                }
            )

        # Get user's Twitter ID from profile
        twitter_user_id = profile.profile_id

        if not twitter_user_id:
            return Response(
                {
                    "events": [],
                    "unread_count": 0,
                    "message": "No Twitter user ID associated with profile",
                }
            )

        # Get recent events for this user
        event_type = request.query_params.get("event_type")
        limit = int(request.query_params.get("limit", 50))

        events_qs = TwitterWebhookEvent.objects.filter(
            for_user_id=twitter_user_id
        ).order_by("-created_at")

        if event_type:
            events_qs = events_qs.filter(event_type=event_type)

        events = events_qs[:limit]

        unread_count = TwitterWebhookEvent.objects.filter(
            for_user_id=twitter_user_id,
            read=False,
        ).count()

        return Response(
            {
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "created_at": event.created_at.isoformat(),
                        "payload": event.payload,
                        "read": event.read,
                    }
                    for event in events
                ],
                "unread_count": unread_count,
            }
        )

    def post(self, request):
        """Mark events as read."""
        from .models import TwitterWebhookEvent

        event_ids = request.data.get("event_ids", [])

        if not event_ids:
            return Response(
                {"error": "No event_ids provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="twitter", status="connected"
            )
            twitter_user_id = profile.profile_id

            updated = TwitterWebhookEvent.objects.filter(
                id__in=event_ids,
                for_user_id=twitter_user_id,
            ).update(read=True)

            return Response(
                {
                    "message": f"Marked {updated} events as read",
                    "updated_count": updated,
                }
            )

        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Twitter account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )


# =============================================================================
# Facebook Views
# =============================================================================


class FacebookConnectView(APIView):
    """
    Initiate Facebook OAuth 2.0 flow.

    Returns the authorization URL that the frontend should redirect to.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not facebook_service.is_configured:
            return Response(
                {"error": "Facebook OAuth not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Generate unique state for CSRF protection
        state = str(uuid.uuid4())

        # Store state in database
        OAuthState.objects.create(
            user=request.user,
            platform="facebook",
            state=state,
        )

        try:
            auth_url = facebook_service.get_authorization_url(state)
            return Response({"authorization_url": auth_url})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FacebookCallbackView(APIView):
    """
    Handle Facebook OAuth 2.0 callback.

    Exchanges authorization code for tokens, gets user pages, and stores page token.
    """

    # No authentication required - this is a callback from Facebook
    permission_classes = []

    def get(self, request):
        code = request.GET.get("code")
        state = request.GET.get("state")
        error = request.GET.get("error")
        page_id = request.GET.get("page_id")  # Optional: select specific page

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

        if error:
            error_description = request.GET.get("error_description", error)
            logger.error(f"Facebook OAuth error: {error} - {error_description}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=facebook_auth_failed"
            )

        if not code or not state:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=missing_params"
            )

        # Validate state
        try:
            oauth_state = OAuthState.objects.get(
                state=state,
                platform="facebook",
                used=False,
            )
        except OAuthState.DoesNotExist:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=invalid_state"
            )

        # Mark state as used
        oauth_state.used = True
        oauth_state.save()

        # Check if state is expired (5 minutes)
        if (timezone.now() - oauth_state.created_at).total_seconds() > 300:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=state_expired"
            )

        try:
            # Exchange code for tokens
            token_data = facebook_service.exchange_code_for_token(code)
            short_lived_token = token_data["access_token"]

            # Get long-lived token
            long_lived_data = facebook_service.get_long_lived_token(short_lived_token)
            user_token = long_lived_data["access_token"]
            token_expires = long_lived_data.get("expires_at")

            # Get user info
            user_info = facebook_service.get_user_info(user_token)

            # Get user's pages
            pages = facebook_service.get_user_pages(user_token)

            if not pages:
                error_msg = "No%20Facebook%20Pages%20found."
                error_msg += "%20Please%20create%20a%20Page%20first."
                return HttpResponseRedirect(
                    f"{frontend_url}/automation?error=no_pages_found"
                    f"&message={error_msg}"
                )

            # Select page - use provided page_id or first available page
            selected_page = None

            if page_id:
                # Try to find the requested page
                for page in pages:
                    if page.get("id") == page_id:
                        selected_page = page
                        break

            # Fall back to first page if no specific page requested or found
            if not selected_page:
                selected_page = pages[0]

            page_access_token = selected_page.get("access_token")

            # Try to get page info, but don't fail if we can't
            page_name = selected_page.get("name", "Facebook Page")
            page_picture_url = None
            page_link = f"https://facebook.com/{selected_page['id']}"

            try:
                page_info = facebook_service.get_page_info(
                    selected_page["id"], page_access_token
                )
                page_name = page_info.get("name", page_name)
                page_link = page_info.get(
                    "link", f"https://facebook.com/{selected_page['id']}"
                )
                page_picture_url = (
                    page_info.get("picture", {}).get("data", {}).get("url")
                )
            except Exception as page_info_error:
                # Log but continue - we have basic info from pages list
                logger.warning(f"Could not fetch detailed page info: {page_info_error}")

            # Create or update social profile with page token
            _, created = SocialProfile.objects.update_or_create(
                user=oauth_state.user,
                platform="facebook",
                defaults={
                    "access_token": user_token,
                    "token_expires_at": token_expires,
                    "profile_id": user_info.get("id"),
                    "profile_name": page_name,
                    "profile_url": page_link,
                    "profile_image_url": page_picture_url,
                    "page_access_token": page_access_token,
                    "page_id": selected_page["id"],
                    "status": "connected",
                },
            )

            action = "created" if created else "updated"
            logger.info(
                f"Facebook profile {action} for user {oauth_state.user.email}: "
                f"Page '{page_name}'"
            )

            return HttpResponseRedirect(
                f"{frontend_url}/automation?success=facebook&name={page_name}"
            )

        except Exception as e:
            logger.error(f"Facebook OAuth callback failed: {e}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=facebook_token_exchange_failed"
            )


class FacebookPagesView(APIView):
    """
    Get list of Facebook Pages the user can manage.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.access_token == FACEBOOK_TEST_ACCESS_TOKEN:
            # Return mock pages for test mode
            test_pages = [
                {
                    "id": profile.page_id or "test_page_1",
                    "name": profile.profile_name or "Test Page",
                    "category": "Test Category",
                    "picture": {"data": {"url": None}},
                    "is_selected": True,
                },
            ]
            return Response(
                {
                    "pages": test_pages,
                    "selected_page_id": profile.page_id,
                    "current_page": {
                        "id": profile.page_id,
                        "name": profile.profile_name,
                    }
                    if profile.page_id
                    else None,
                    "test_mode": True,
                }
            )

        try:
            pages = facebook_service.get_user_pages(profile.access_token)

            # Find current page info
            current_page = None
            for page in pages:
                if page.get("id") == profile.page_id:
                    current_page = {
                        "id": page.get("id"),
                        "name": page.get("name"),
                    }
                    break

            return Response(
                {
                    "pages": [
                        {
                            "id": page.get("id"),
                            "name": page.get("name"),
                            "category": page.get("category"),
                            "picture": page.get("picture"),
                            "is_selected": page.get("id") == profile.page_id,
                        }
                        for page in pages
                    ],
                    "selected_page_id": profile.page_id,
                    "current_page": current_page,
                }
            )
        except Exception as e:
            logger.error(f"Failed to fetch Facebook pages: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookSelectPageView(APIView):
    """
    Select a different Facebook Page to post to.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        page_id = request.data.get("page_id")

        if not page_id:
            return Response(
                {"error": "page_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            pages = facebook_service.get_user_pages(profile.access_token)
            selected_page = None
            for page in pages:
                if page.get("id") == page_id:
                    selected_page = page
                    break

            if not selected_page:
                return Response(
                    {"error": "Page not found or not accessible"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Update profile with new page
            page_info = facebook_service.get_page_info(
                page_id, selected_page.get("access_token")
            )

            profile.page_id = page_id
            profile.page_access_token = selected_page.get("access_token")
            profile.profile_name = page_info.get("name")
            profile.profile_url = page_info.get(
                "link", f"https://facebook.com/{page_id}"
            )
            profile.profile_image_url = (
                page_info.get("picture", {}).get("data", {}).get("url")
            )
            profile.save()

            return Response(
                {
                    "message": f"Selected page: {page_info.get('name')}",
                    "page": {
                        "id": page_id,
                        "name": page_info.get("name"),
                        "category": page_info.get("category"),
                    },
                }
            )

        except Exception as e:
            logger.error(f"Failed to select Facebook page: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookDisconnectView(APIView):
    """Disconnect Facebook account."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = SocialProfile.objects.get(user=request.user, platform="facebook")

            # Clear tokens and mark as disconnected
            profile.access_token = None
            profile.page_access_token = None
            profile.page_id = None
            profile.token_expires_at = None
            profile.status = "disconnected"
            profile.save()

            return Response({"message": "Facebook account disconnected successfully"})

        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "No Facebook account connected"},
                status=status.HTTP_404_NOT_FOUND,
            )


class FacebookTestConnectView(APIView):
    """
    Create a mock Facebook connection for testing (DEBUG mode only).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not settings.DEBUG:
            return Response(
                {"error": "Test connect only available in DEBUG mode"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Create mock profile
        profile, created = SocialProfile.objects.update_or_create(
            user=request.user,
            platform="facebook",
            defaults={
                "access_token": FACEBOOK_TEST_ACCESS_TOKEN,
                "page_access_token": FACEBOOK_TEST_PAGE_TOKEN,
                "page_id": "909373962269929",  # Test page ID
                "token_expires_at": timezone.now() + timedelta(days=60),
                "profile_id": f"test_facebook_{request.user.id}",
                "profile_name": "Test Page (Development)",
                "profile_url": "https://facebook.com/test_page",
                "profile_image_url": None,
                "status": "connected",
            },
        )

        action = "updated" if not created else "created"
        return Response(
            {
                "message": f"Test Facebook connection {action}",
                "profile": SocialProfileSerializer(profile).data,
            }
        )


class FacebookPostView(APIView):
    """
    Create a post on the connected Facebook Page.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = request.data.get("message", "")
        link = request.data.get("link")
        photo_url = request.data.get("photo_url")

        if not message and not photo_url:
            return Response(
                {"error": "Message or photo_url is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Check for test mode - check both page token and access token
            is_test_mode = (
                profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN
                or profile.access_token == FACEBOOK_TEST_ACCESS_TOKEN
                or profile.profile_id.startswith("test_facebook_")
            )

            if is_test_mode:
                test_post_id = f"test_post_{uuid.uuid4().hex[:8]}"
                # Store in ContentCalendar for history even in test mode
                ContentCalendar.objects.create(
                    user=request.user,
                    title=message[:50] + "..." if len(message) > 50 else message,
                    content=message,
                    platforms=["facebook"],
                    scheduled_date=timezone.now(),
                    status="published",
                    published_at=timezone.now(),
                    post_results={"facebook": {"id": test_post_id}, "id": test_post_id},
                )
                return Response(
                    {
                        "test_mode": True,
                        "message": "Post simulated in test mode",
                        "post_id": test_post_id,
                        "id": test_post_id,
                    }
                )

            # Create post
            if photo_url:
                result = facebook_service.create_page_photo_post(
                    page_id=profile.page_id,
                    page_access_token=profile.page_access_token,
                    photo_url=photo_url,
                    message=message if message else None,
                )
            else:
                result = facebook_service.create_page_post(
                    page_id=profile.page_id,
                    page_access_token=profile.page_access_token,
                    message=message,
                    link=link,
                )

            # Store in ContentCalendar for history
            ContentCalendar.objects.create(
                user=request.user,
                title=message[:50] + "..." if len(message) > 50 else message,
                content=message,
                platforms=["facebook"],
                scheduled_date=timezone.now(),
                status="published",
                published_at=timezone.now(),
                post_results={"facebook": result, "id": result.get("id")},
            )

            return Response(
                {
                    "success": True,
                    "post_id": result.get("id"),
                    "message": "Posted to Facebook successfully",
                    **result,
                }
            )

        except Exception as e:
            logger.error(f"Facebook post creation failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookMediaUploadView(APIView):
    """
    Upload media (photo/video) to Facebook.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")
        message = request.data.get("message", "")

        if not file:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "message": "Media upload simulated in test mode",
                    "id": f"test_media_{uuid.uuid4().hex[:8]}",
                }
            )

        content_type = file.content_type
        file_data = file.read()

        try:
            if content_type.startswith("image/"):
                # Upload photo
                result = facebook_service.upload_photo(
                    page_id=profile.page_id,
                    page_access_token=profile.page_access_token,
                    image_data=file_data,
                    message=message if message else None,
                )
            elif content_type.startswith("video/"):
                # Upload video
                result = facebook_service.upload_video_simple(
                    page_id=profile.page_id,
                    page_access_token=profile.page_access_token,
                    video_data=file_data,
                    description=message if message else None,
                )
            else:
                return Response(
                    {"error": f"Unsupported file type: {content_type}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(result)

        except Exception as e:
            logger.error(f"Facebook media upload failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookResumableUploadView(APIView):
    """
    Handle resumable video uploads for Facebook (> 1GB files).

    This implements Facebook's Resumable Upload API which allows:
    - Uploading large videos in chunks
    - Resuming interrupted uploads
    - Progress tracking

    Docs: https://developers.facebook.com/docs/graph-api/guides/upload

    Workflow:
    1. POST /start - Initialize upload session, get upload_session_id
    2. POST /chunk - Upload a chunk (repeat until done)
    3. POST /finish - Finalize and publish the video
    """

    permission_classes = [IsAuthenticated]

    # Default chunk size: 4MB (Facebook recommends 4MB-1GB chunks)
    DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024

    def get_profile(self, request):
        """Get the connected Facebook profile."""
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
            if not profile.page_access_token or not profile.page_id:
                return None, Response(
                    {"error": "No Facebook Page selected"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return profile, None
        except SocialProfile.DoesNotExist:
            return None, Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

    def post(self, request, action=None):
        """Handle resumable upload actions."""
        if action == "start":
            return self.start_upload(request)
        elif action == "chunk":
            return self.upload_chunk(request)
        elif action == "finish":
            return self.finish_upload(request)
        else:
            return Response(
                {"error": "Invalid action. Use: start, chunk, or finish"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def get(self, request, action=None):
        """Get upload status or list in-progress uploads."""
        profile, error_response = self.get_profile(request)
        if error_response:
            return error_response

        from .models import FacebookResumableUpload

        upload_session_id = request.query_params.get("upload_session_id")

        if upload_session_id:
            # Get specific upload status
            try:
                upload = FacebookResumableUpload.objects.get(
                    user=request.user, upload_session_id=upload_session_id
                )
                return Response(
                    {
                        "upload_session_id": upload.upload_session_id,
                        "video_id": upload.video_id,
                        "file_name": upload.file_name,
                        "file_size": upload.file_size,
                        "bytes_uploaded": upload.bytes_uploaded,
                        "progress_percent": upload.progress_percent,
                        "status": upload.status,
                        "status_display": upload.get_status_display(),
                        "start_offset": upload.start_offset,
                        "created_at": upload.created_at.isoformat(),
                        "updated_at": upload.updated_at.isoformat(),
                    }
                )
            except FacebookResumableUpload.DoesNotExist:
                return Response(
                    {"error": "Upload session not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # List in-progress uploads
            uploads = FacebookResumableUpload.objects.filter(
                user=request.user, page_id=profile.page_id
            ).filter(status__in=["pending", "uploading", "processing"])

            return Response(
                {
                    "uploads": [
                        {
                            "upload_session_id": u.upload_session_id,
                            "file_name": u.file_name,
                            "file_size": u.file_size,
                            "progress_percent": u.progress_percent,
                            "status": u.status,
                            "created_at": u.created_at.isoformat(),
                        }
                        for u in uploads
                    ],
                }
            )

    def start_upload(self, request):
        """
        Start a resumable upload session.

        Request body:
        - file_size: Total size in bytes (required)
        - file_name: Original file name (required)
        - title: Video title (optional)
        - description: Video description (optional)
        """
        profile, error_response = self.get_profile(request)
        if error_response:
            return error_response

        file_size = request.data.get("file_size")
        file_name = request.data.get("file_name", "video.mp4")
        title = request.data.get("title")
        description = request.data.get("description")

        if not file_size:
            return Response(
                {"error": "file_size is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            file_size = int(file_size)
        except (ValueError, TypeError):
            return Response(
                {"error": "file_size must be a number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            from .models import FacebookResumableUpload

            # Create a test upload session
            upload = FacebookResumableUpload.objects.create(
                user=request.user,
                page_id=profile.page_id,
                upload_session_id=f"test_session_{uuid.uuid4().hex[:16]}",
                video_id=f"test_video_{uuid.uuid4().hex[:8]}",
                file_name=file_name,
                file_size=file_size,
                title=title,
                description=description,
                status="pending",
            )

            return Response(
                {
                    "test_mode": True,
                    "upload_session_id": upload.upload_session_id,
                    "video_id": upload.video_id,
                    "chunk_size": self.DEFAULT_CHUNK_SIZE,
                    "message": "Test upload session created",
                }
            )

        try:
            # Start the upload with Facebook
            result = facebook_service.start_video_upload(
                page_id=profile.page_id,
                page_access_token=profile.page_access_token,
                file_size=file_size,
            )

            from .models import FacebookResumableUpload

            # Store the upload session
            upload = FacebookResumableUpload.objects.create(
                user=request.user,
                page_id=profile.page_id,
                upload_session_id=result.get("upload_session_id"),
                video_id=result.get("video_id"),
                file_name=file_name,
                file_size=file_size,
                title=title,
                description=description,
                status="pending",
            )

            return Response(
                {
                    "upload_session_id": upload.upload_session_id,
                    "video_id": upload.video_id,
                    "start_offset": 0,
                    "chunk_size": self.DEFAULT_CHUNK_SIZE,
                }
            )

        except Exception as e:
            logger.error(f"Facebook resumable upload start failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def upload_chunk(self, request):
        """
        Upload a chunk of the video.

        Request body:
        - upload_session_id: Session ID from start (required)
        - start_offset: Byte offset for this chunk (required)
        - file: The chunk data (required, as file upload)
        """
        profile, error_response = self.get_profile(request)
        if error_response:
            return error_response

        upload_session_id = request.data.get("upload_session_id")
        start_offset = request.data.get("start_offset")
        chunk_file = request.FILES.get("file")

        if not all([upload_session_id, chunk_file]):
            return Response(
                {"error": "upload_session_id and file are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_offset = int(start_offset or 0)
        except (ValueError, TypeError):
            return Response(
                {"error": "start_offset must be a number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import FacebookResumableUpload

        try:
            upload = FacebookResumableUpload.objects.get(
                user=request.user, upload_session_id=upload_session_id
            )
        except FacebookResumableUpload.DoesNotExist:
            return Response(
                {"error": "Upload session not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            chunk_size = len(chunk_file.read())
            new_offset = start_offset + chunk_size

            upload.update_progress(new_offset, new_offset)

            return Response(
                {
                    "test_mode": True,
                    "start_offset": new_offset,
                    "end_offset": new_offset,
                    "progress_percent": upload.progress_percent,
                }
            )

        try:
            chunk_data = chunk_file.read()

            result = facebook_service.upload_video_chunk(
                page_id=profile.page_id,
                page_access_token=profile.page_access_token,
                upload_session_id=upload_session_id,
                start_offset=start_offset,
                chunk_data=chunk_data,
            )

            # Update progress
            new_start = result.get("start_offset", start_offset + len(chunk_data))
            new_end = result.get("end_offset", new_start)
            upload.update_progress(new_start, new_end)

            return Response(
                {
                    "start_offset": new_start,
                    "end_offset": new_end,
                    "progress_percent": upload.progress_percent,
                }
            )

        except Exception as e:
            logger.error(f"Facebook chunk upload failed: {e}")
            upload.mark_failed(str(e))
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def finish_upload(self, request):
        """
        Finish the upload and publish the video.

        Request body:
        - upload_session_id: Session ID from start (required)
        - title: Video title (optional, overrides start value)
        - description: Video description (optional, overrides start value)
        """
        profile, error_response = self.get_profile(request)
        if error_response:
            return error_response

        upload_session_id = request.data.get("upload_session_id")

        if not upload_session_id:
            return Response(
                {"error": "upload_session_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import FacebookResumableUpload

        try:
            upload = FacebookResumableUpload.objects.get(
                user=request.user, upload_session_id=upload_session_id
            )
        except FacebookResumableUpload.DoesNotExist:
            return Response(
                {"error": "Upload session not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Update title/description if provided
        title = request.data.get("title", upload.title)
        description = request.data.get("description", upload.description)

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            upload.mark_completed()
            return Response(
                {
                    "test_mode": True,
                    "success": True,
                    "video_id": upload.video_id,
                    "message": "Video upload completed (test mode)",
                }
            )

        try:
            result = facebook_service.finish_video_upload(
                page_id=profile.page_id,
                page_access_token=profile.page_access_token,
                upload_session_id=upload_session_id,
                title=title,
                description=description,
            )

            upload.mark_completed()

            return Response(
                {
                    "success": result.get("success", True),
                    "video_id": upload.video_id,
                    "message": "Video upload completed",
                }
            )

        except Exception as e:
            logger.error(f"Facebook upload finish failed: {e}")
            upload.mark_failed(str(e))
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request, action=None):
        """Cancel an in-progress upload."""
        upload_session_id = request.query_params.get("upload_session_id")

        if not upload_session_id:
            return Response(
                {"error": "upload_session_id query param is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import FacebookResumableUpload

        try:
            upload = FacebookResumableUpload.objects.get(
                user=request.user, upload_session_id=upload_session_id
            )
        except FacebookResumableUpload.DoesNotExist:
            return Response(
                {"error": "Upload session not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        upload.status = "cancelled"
        upload.save()

        return Response(
            {
                "message": "Upload cancelled",
                "upload_session_id": upload_session_id,
            }
        )


class FacebookDeletePostView(APIView):
    """
    Delete a post from Facebook Page.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, post_id):
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode - handle both test page token and test_mode post IDs
        is_test_mode = (
            profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN
            or post_id.startswith("test_")
        )

        if is_test_mode:
            # In test mode, delete the ContentCalendar record
            deleted_count = 0
            # Find by searching in post_results JSON
            for calendar_entry in ContentCalendar.objects.filter(
                user=request.user,
                status="published",
            ):
                if not calendar_entry.post_results:
                    continue

                # Check multiple possible locations for the post ID
                # Direct: { "id": "..." }
                direct_id = calendar_entry.post_results.get("id")
                # Nested: { "facebook": { "id": "..." } }
                facebook_data = calendar_entry.post_results.get("facebook", {})
                nested_id = (
                    facebook_data.get("id") if isinstance(facebook_data, dict) else None
                )
                # Check for test_mode flag in nested structure
                # (for posts without ID)
                has_test_mode = (
                    facebook_data.get("test_mode")
                    if isinstance(facebook_data, dict)
                    else calendar_entry.post_results.get("test_mode")
                )

                # Match if any ID matches, or if this is a
                # test_mode post and we're deleting test_mode
                id_matches = (
                    (direct_id and direct_id == post_id)
                    or (nested_id and nested_id == post_id)
                    or (post_id == "test_mode" and has_test_mode)
                )

                if id_matches:
                    # Verify it's a Facebook post by checking platforms
                    if hasattr(calendar_entry, "platforms") and "facebook" in (
                        calendar_entry.platforms or []
                    ):
                        calendar_entry.delete()
                        deleted_count = 1
                        break
                    # Or check social_profiles
                    elif calendar_entry.social_profiles.filter(
                        platform="facebook"
                    ).exists():
                        calendar_entry.delete()
                        deleted_count = 1
                        break

            return Response(
                {
                    "test_mode": True,
                    "message": "Post deletion simulated in test mode",
                    "calendar_entries_deleted": deleted_count,
                }
            )

        try:
            success = facebook_service.delete_post(post_id, profile.page_access_token)
            if success:
                # Also delete from ContentCalendar
                deleted_count = 0
                for calendar_entry in ContentCalendar.objects.filter(
                    user=request.user,
                    status="published",
                ):
                    if (
                        calendar_entry.post_results
                        and calendar_entry.post_results.get("id") == post_id
                    ):
                        # Verify it's a Facebook post
                        if hasattr(calendar_entry, "platforms") and "facebook" in (
                            calendar_entry.platforms or []
                        ):
                            calendar_entry.delete()
                            deleted_count += 1
                            break
                        elif calendar_entry.social_profiles.filter(
                            platform="facebook"
                        ).exists():
                            calendar_entry.delete()
                            deleted_count += 1
                            break

                return Response(
                    {
                        "message": "Post deleted successfully",
                        "calendar_entries_deleted": deleted_count,
                    }
                )
            else:
                return Response(
                    {"error": "Failed to delete post"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except Exception as e:
            logger.error(f"Facebook post deletion failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookAnalyticsView(APIView):
    """
    Get Facebook Page analytics and post insights.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, post_id=None):
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "insights": {
                        "page_impressions": 1234,
                        "page_engaged_users": 567,
                        "page_fans": 890,
                        "page_fan_adds": 12,
                        "page_post_engagements": 345,
                        "page_views_total": 678,
                    },
                    "recent_posts": [],
                }
            )

        try:
            if post_id:
                # Get specific post insights
                insights = facebook_service.get_post_insights(
                    post_id, profile.page_access_token
                )
                post = facebook_service.get_post(post_id, profile.page_access_token)
                return Response(
                    {
                        "post": post,
                        "insights": insights,
                    }
                )
            else:
                # Get page insights
                insights = facebook_service.get_page_insights(
                    profile.page_id, profile.page_access_token
                )
                # Get recent posts
                posts = facebook_service.get_page_posts(
                    profile.page_id, profile.page_access_token, limit=10
                )

                return Response(
                    {
                        "page_id": profile.page_id,
                        "page_name": profile.profile_name,
                        "insights": insights,
                        "recent_posts": [
                            {
                                "id": post.get("id"),
                                "message": post.get("message", ""),
                                "created_time": post.get("created_time"),
                                "permalink_url": post.get("permalink_url"),
                                "full_picture": post.get("full_picture"),
                                "likes": post.get("likes", {})
                                .get("summary", {})
                                .get("total_count", 0),
                                "comments": post.get("comments", {})
                                .get("summary", {})
                                .get("total_count", 0),
                                "shares": post.get("shares", {}).get("count", 0),
                            }
                            for post in posts
                        ],
                    }
                )

        except Exception as e:
            logger.error(f"Facebook analytics fetch failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookLinkPreviewView(APIView):
    """
    Fetch Open Graph data for a URL to display link preview.

    This endpoint scrapes the URL for Open Graph meta tags and returns
    preview data including title, description, and image.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get link preview data for a URL.

        Query params:
        - url: The URL to fetch preview for (required)
        """
        url = request.query_params.get("url")

        if not url:
            return Response(
                {"error": "url parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            # Return mock preview data
            return Response(
                {
                    "test_mode": True,
                    "url": url,
                    "title": "Example Link Title",
                    "description": (
                        "This is a sample description for the "
                        "link preview in test mode."
                    ),
                    "image": None,
                    "site_name": "Example Site",
                    "type": "website",
                }
            )

        try:
            preview = facebook_service.get_link_preview(url, profile.page_access_token)
            return Response(preview)
        except Exception as e:
            logger.error(f"Facebook link preview fetch failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookCarouselPostView(APIView):
    """
    Create a carousel (multi-image) post on Facebook.

    Carousel posts allow up to 10 images that users can swipe through.
    Images can be provided as URLs or uploaded directly.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create a carousel post.

        Request body:
        - message: Post caption/text (required)
        - photo_urls: List of image URLs (2-10 items)
        OR
        - photo_ids: List of pre-uploaded unpublished photo IDs
        """
        message = request.data.get("message", "")
        photo_urls = request.data.get("photo_urls", [])
        photo_ids = request.data.get("photo_ids", [])

        if not message:
            return Response(
                {"error": "message is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not photo_urls and not photo_ids:
            return Response(
                {"error": "Either photo_urls or photo_ids is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_photos = len(photo_urls) + len(photo_ids)
        if total_photos < 2:
            return Response(
                {"error": "Carousel posts require at least 2 photos"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if total_photos > 10:
            return Response(
                {"error": "Carousel posts support maximum 10 photos"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode - either test token OR placeholder URLs
        is_test_mode = profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN or all(
            str(url).startswith("carousel_image_") for url in photo_urls
        )

        if is_test_mode:
            test_post_id = f"test_carousel_{uuid.uuid4().hex[:8]}"

            # Save to ContentCalendar for history (even in test mode)
            ContentCalendar.objects.create(
                user=request.user,
                title=f"[Carousel] {message[:40]}..."
                if len(message) > 40
                else f"[Carousel] {message}",
                content=message,
                platforms=["facebook"],
                scheduled_date=timezone.now(),
                published_at=timezone.now(),
                status="published",
                post_results={
                    "facebook": {
                        "test_mode": True,
                        "post_id": test_post_id,
                        "type": "carousel",
                        "photo_count": total_photos,
                    }
                },
            )

            return Response(
                {
                    "test_mode": True,
                    "message": "Carousel post simulated in test mode",
                    "post_id": test_post_id,
                    "id": test_post_id,
                    "photo_count": total_photos,
                }
            )

        try:
            # If photo_urls provided, create unpublished photos first
            all_photo_ids = list(photo_ids)

            for url in photo_urls:
                result = facebook_service.create_unpublished_photo(
                    page_id=profile.page_id,
                    page_access_token=profile.page_access_token,
                    photo_url=url,
                )
                all_photo_ids.append(result.get("id"))

            # Create the carousel post
            result = facebook_service.create_carousel_post(
                page_id=profile.page_id,
                page_access_token=profile.page_access_token,
                message=message,
                photo_ids=all_photo_ids,
            )

            # Store in ContentCalendar for history
            ContentCalendar.objects.create(
                user=request.user,
                title=message[:50] + "..." if len(message) > 50 else message,
                content=message,
                platforms=["facebook"],
                scheduled_date=timezone.now(),
                status="published",
                published_at=timezone.now(),
                post_results={
                    "facebook": result,
                    "id": result.get("id"),
                    "type": "carousel",
                    "photo_count": len(all_photo_ids),
                },
            )

            return Response(
                {
                    "success": True,
                    "post_id": result.get("id"),
                    "message": "Carousel posted to Facebook successfully",
                    "photo_count": len(all_photo_ids),
                    **result,
                }
            )

        except Exception as e:
            logger.error(f"Facebook carousel post creation failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookCarouselUploadView(APIView):
    """
    Upload photos for use in a carousel post.

    This endpoint uploads photos as unpublished, returning IDs that can
    be used with the carousel post endpoint.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Upload a photo for carousel use.

        Request:
        - file: Image file (multipart form data)

        Returns:
        - photo_id: ID to use in carousel post
        """
        file = request.FILES.get("file")

        if not file:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            return Response(
                {"error": f"Invalid file type. Allowed: {', '.join(allowed_types)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "photo_id": f"test_photo_{uuid.uuid4().hex[:8]}",
                    "message": "Photo uploaded for carousel (test mode)",
                }
            )

        try:
            image_data = file.read()
            result = facebook_service.upload_unpublished_photo(
                page_id=profile.page_id,
                page_access_token=profile.page_access_token,
                image_data=image_data,
                content_type=file.content_type,
            )

            return Response(
                {
                    "photo_id": result.get("id"),
                    "message": "Photo uploaded for carousel",
                }
            )

        except Exception as e:
            logger.error(f"Facebook carousel photo upload failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookWebhookView(APIView):
    """
    Handle Facebook webhook events.

    Facebook sends webhooks for:
    - Page feed updates (posts, comments, reactions)
    - Page mentions
    - Messaging events
    - Lead generation
    - Ratings

    Docs: https://developers.facebook.com/docs/graph-api/webhooks/

    Note: Webhooks must be configured in Facebook Developer Portal:
    1. Go to App Dashboard > Webhooks
    2. Select "Page" and subscribe to events
    3. Set callback URL to this endpoint
    4. Set verify token to match FACEBOOK_WEBHOOK_VERIFY_TOKEN in settings
    """

    # Webhooks don't require user authentication - they use signature validation
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        """
        Handle webhook verification from Facebook.

        Facebook sends a GET request with:
        - hub.mode: "subscribe"
        - hub.challenge: A random string to echo back
        - hub.verify_token: Token configured in Facebook Developer Portal
        """
        mode = request.query_params.get("hub.mode")
        challenge = request.query_params.get("hub.challenge")
        verify_token = request.query_params.get("hub.verify_token")

        logger.info(f"Facebook webhook verification: mode={mode}, token={verify_token}")

        if mode == "subscribe":
            if facebook_service.verify_webhook_token(verify_token):
                logger.info("Facebook webhook verification successful")
                # Must return the challenge as plain text
                from django.http import HttpResponse

                return HttpResponse(challenge, content_type="text/plain")
            else:
                logger.warning("Facebook webhook verification failed - invalid token")
                return Response(
                    {"error": "Invalid verify token"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        return Response(
            {"error": "Invalid mode"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def post(self, request):
        """
        Handle incoming webhook events from Facebook.

        Facebook sends events in this format:
        {
            "object": "page",
            "entry": [
                {
                    "id": "<PAGE_ID>",
                    "time": 1609459200000,
                    "changes": [
                        {
                            "field": "feed",
                            "value": {
                                "item": "post|comment|reaction",
                                "verb": "add|edit|remove",
                                "post_id": "...",
                                ...
                            }
                        }
                    ]
                }
            ]
        }
        """
        # Validate Facebook webhook signature
        signature_header = request.headers.get("X-Hub-Signature-256", "")

        if not facebook_service.verify_webhook_signature(
            request.body, signature_header
        ):
            logger.warning("Facebook webhook signature validation failed")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Process the webhook event
        event_data = request.data
        logger.info(f"Facebook webhook event received: {event_data}")

        # Import the model here to avoid circular imports
        from .models import FacebookWebhookEvent

        object_type = event_data.get("object", "")
        entries = event_data.get("entry", [])

        if object_type != "page":
            logger.warning(f"Unexpected webhook object type: {object_type}")
            return Response({"status": "ignored"})

        # Process each entry
        for entry in entries:
            page_id = entry.get("id", "")
            # timestamp available in entry.get("time") if needed

            # Handle messaging events
            messaging = entry.get("messaging", [])
            for msg in messaging:
                sender_id = msg.get("sender", {}).get("id")
                event_type = "message"
                if msg.get("postback"):
                    event_type = "messaging_postback"

                FacebookWebhookEvent.objects.create(
                    event_type=event_type,
                    page_id=page_id,
                    sender_id=sender_id,
                    payload=msg,
                )
                logger.info(f"Facebook {event_type} event stored for page {page_id}")

            # Handle feed changes
            changes = entry.get("changes", [])
            for change in changes:
                field = change.get("field", "")
                value = change.get("value", {})

                # Determine event type based on field and value
                if field == "feed":
                    item = value.get("item", "")
                    # verb = value.get("verb", "") - available if needed
                    post_id = value.get("post_id", "")
                    sender_id = value.get("sender_id") or value.get("from", {}).get(
                        "id"
                    )

                    if item == "reaction":
                        event_type = "feed_reaction"
                    elif item == "comment":
                        event_type = "feed_comment"
                    elif item == "share":
                        event_type = "feed_share"
                    else:
                        event_type = "feed"

                    FacebookWebhookEvent.objects.create(
                        event_type=event_type,
                        page_id=page_id,
                        sender_id=sender_id,
                        post_id=post_id,
                        payload=value,
                    )
                    logger.info(
                        f"Facebook {event_type} event stored for page {page_id}, "
                        f"post {post_id}"
                    )

                elif field == "mention":
                    sender_id = value.get("sender_id") or value.get("from", {}).get(
                        "id"
                    )
                    post_id = value.get("post_id", "")

                    FacebookWebhookEvent.objects.create(
                        event_type="mention",
                        page_id=page_id,
                        sender_id=sender_id,
                        post_id=post_id,
                        payload=value,
                    )
                    logger.info(f"Facebook mention event stored for page {page_id}")

                elif field == "ratings":
                    reviewer_id = value.get("reviewer_id")

                    FacebookWebhookEvent.objects.create(
                        event_type="rating",
                        page_id=page_id,
                        sender_id=reviewer_id,
                        payload=value,
                    )
                    logger.info(f"Facebook rating event stored for page {page_id}")

                elif field == "leadgen":
                    FacebookWebhookEvent.objects.create(
                        event_type="leadgen",
                        page_id=page_id,
                        payload=value,
                    )
                    logger.info(f"Facebook leadgen event stored for page {page_id}")

                elif field == "videos":
                    video_id = value.get("video_id")
                    FacebookWebhookEvent.objects.create(
                        event_type="video",
                        page_id=page_id,
                        post_id=video_id,
                        payload=value,
                    )
                    logger.info(f"Facebook video event stored for page {page_id}")

                else:
                    # Generic event storage for other fields
                    FacebookWebhookEvent.objects.create(
                        event_type=field[:30],  # Truncate to fit field
                        page_id=page_id,
                        payload=value,
                    )
                    logger.info(f"Facebook {field} event stored for page {page_id}")

        # Return 200 to acknowledge receipt
        return Response({"status": "ok"})


class FacebookWebhookEventsView(APIView):
    """
    Get stored Facebook webhook events for the authenticated user's page.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get webhook events for the user's connected Facebook Page.

        Query params:
        - event_type: Filter by event type
        - unread_only: Only show unread events
        - limit: Number of events to return (default 50)
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import FacebookWebhookEvent

        queryset = FacebookWebhookEvent.objects.filter(page_id=profile.page_id)

        # Apply filters
        event_type = request.query_params.get("event_type")
        if event_type:
            queryset = queryset.filter(event_type=event_type)

        unread_only = request.query_params.get("unread_only", "").lower() == "true"
        if unread_only:
            queryset = queryset.filter(read=False)

        limit = int(request.query_params.get("limit", 50))
        events = queryset[:limit]

        return Response(
            {
                "page_id": profile.page_id,
                "page_name": profile.profile_name,
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "event_type_display": event.get_event_type_display(),
                        "sender_id": event.sender_id,
                        "post_id": event.post_id,
                        "payload": event.payload,
                        "read": event.read,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in events
                ],
                "total_count": queryset.count(),
                "unread_count": queryset.filter(read=False).count(),
            }
        )

    def post(self, request):
        """
        Mark events as read.

        Request body:
        - event_ids: List of event IDs to mark as read
        - mark_all: If true, mark all events as read
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .models import FacebookWebhookEvent

        event_ids = request.data.get("event_ids", [])
        mark_all = request.data.get("mark_all", False)

        if mark_all:
            updated = FacebookWebhookEvent.objects.filter(
                page_id=profile.page_id, read=False
            ).update(read=True)
        elif event_ids:
            updated = FacebookWebhookEvent.objects.filter(
                page_id=profile.page_id, id__in=event_ids
            ).update(read=True)
        else:
            return Response(
                {"error": "Provide event_ids or mark_all=true"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": f"Marked {updated} events as read",
                "updated_count": updated,
            }
        )


class FacebookWebhookSubscribeView(APIView):
    """
    Subscribe/unsubscribe a Facebook Page to/from webhook events.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Subscribe the connected page to webhook events.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "success": True,
                    "message": "Webhook subscription simulated in test mode",
                }
            )

        try:
            result = facebook_service.subscribe_to_page_webhooks(
                profile.page_id, profile.page_access_token
            )
            return Response(
                {
                    "success": result.get("success", False),
                    "message": "Page subscribed to webhook events",
                }
            )
        except Exception as e:
            logger.error(f"Facebook webhook subscription failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request):
        """
        Unsubscribe the connected page from webhook events.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "success": True,
                    "message": "Webhook unsubscription simulated in test mode",
                }
            )

        try:
            result = facebook_service.unsubscribe_from_page_webhooks(
                profile.page_id, profile.page_access_token
            )
            return Response(
                {
                    "success": result.get("success", False),
                    "message": "Page unsubscribed from webhook events",
                }
            )
        except Exception as e:
            logger.error(f"Facebook webhook unsubscription failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get(self, request):
        """
        Get current webhook subscriptions for the page.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "subscriptions": [
                        {"name": "Test App", "subscribed_fields": ["feed", "mention"]},
                    ],
                }
            )

        try:
            subscriptions = facebook_service.get_page_webhook_subscriptions(
                profile.page_id, profile.page_access_token
            )
            return Response(
                {
                    "page_id": profile.page_id,
                    "subscriptions": subscriptions,
                }
            )
        except Exception as e:
            logger.error(f"Facebook webhook subscriptions fetch failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# =============================================================================
# Facebook Stories Views
# =============================================================================

# In-memory cache for test mode stories (clears on server restart)
_test_stories_cache = {}


class FacebookStoryView(APIView):
    """
    Create and manage Facebook Page Stories.

    Stories are ephemeral content that disappear after 24 hours.
    Requires pages_manage_posts permission.

    Photo Story Requirements:
    - Recommended aspect ratio: 9:16 (vertical)
    - Minimum resolution: 1080x1920 pixels
    - Supported formats: JPEG, PNG
    - Maximum file size: 4MB

    Video Story Requirements:
    - Recommended aspect ratio: 9:16 (vertical)
    - Minimum resolution: 720x1280 pixels
    - Duration: 1-60 seconds (recommended 3-15 seconds)
    - Supported formats: MP4, MOV
    - Maximum file size: 4GB
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create a new story (photo or video).

        Request (multipart/form-data):
        - type: "photo" or "video" (required)
        - file: Media file (optional, mutually exclusive with url)
        - url: URL of media (optional, mutually exclusive with file)
        - title: Title for video stories (optional)

        Returns:
        - Story ID and status
        """
        story_type = request.data.get("type", "photo")
        file = request.FILES.get("file")
        url = request.data.get("url")
        title = request.data.get("title")

        if not file and not url:
            return Response(
                {"error": "Either file or url must be provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if file and url:
            return Response(
                {"error": "Only one of file or url can be provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if story_type not in ["photo", "video"]:
            return Response(
                {"error": "Type must be 'photo' or 'video'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file type
        if file:
            if story_type == "photo":
                allowed_types = ["image/jpeg", "image/png"]
                if file.content_type not in allowed_types:
                    allowed = ", ".join(allowed_types)
                    return Response(
                        {"error": f"Invalid photo type. Allowed: {allowed}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Check file size (4MB max for photos)
                if file.size > 4 * 1024 * 1024:
                    return Response(
                        {"error": "Photo file too large. Maximum size is 4MB"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:  # video
                allowed_types = ["video/mp4", "video/quicktime"]
                if file.content_type not in allowed_types:
                    return Response(
                        {"error": "Invalid video type. Allowed: MP4, MOV"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Check file size (4GB max for videos)
                if file.size > 4 * 1024 * 1024 * 1024:
                    return Response(
                        {"error": "Video file too large. Maximum size is 4GB"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            story_id = f"test_story_{uuid.uuid4().hex[:8]}"
            created_at = timezone.now().isoformat()
            expires_at = (timezone.now() + timedelta(hours=24)).isoformat()

            # Store in test cache
            user_id = request.user.id
            if user_id not in _test_stories_cache:
                _test_stories_cache[user_id] = []

            # Add new story to cache
            _test_stories_cache[user_id].append(
                {
                    "id": story_id,
                    "media_type": story_type.upper(),
                    "status": "ACTIVE",
                    "created_at": created_at,
                    "expires_at": expires_at,
                }
            )

            # Clean up expired stories (older than 24 hours)
            now = timezone.now()
            _test_stories_cache[user_id] = [
                s
                for s in _test_stories_cache[user_id]
                if (
                    now
                    - timezone.datetime.fromisoformat(
                        s["created_at"].replace("Z", "+00:00")
                    )
                ).total_seconds()
                < 86400
            ]

            # Save to ContentCalendar for Recent Activity
            ContentCalendar.objects.create(
                user=request.user,
                title=f"Facebook Story ({story_type.title()})",
                content="Story posted via Facebook Page",
                platforms=["facebook"],
                scheduled_date=timezone.now(),
                status="published",
                post_results={
                    "facebook": {
                        "id": story_id,
                        "type": "story",
                        "media_type": story_type,
                        "created_at": created_at,
                        "expires_at": expires_at,
                        "test_mode": True,
                    }
                },
            )

            return Response(
                {
                    "test_mode": True,
                    "story_id": story_id,
                    "type": story_type,
                    "status": "created",
                    "created_at": created_at,
                    "expires_at": expires_at,
                    "message": "Story created in test mode (expires in 24 hours)",
                }
            )

        try:
            if story_type == "photo":
                if file:
                    result = facebook_service.create_photo_story(
                        page_id=profile.page_id,
                        page_access_token=profile.page_access_token,
                        photo_data=file.read(),
                    )
                else:
                    result = facebook_service.create_photo_story(
                        page_id=profile.page_id,
                        page_access_token=profile.page_access_token,
                        photo_url=url,
                    )
            else:  # video
                if file:
                    result = facebook_service.create_video_story(
                        page_id=profile.page_id,
                        page_access_token=profile.page_access_token,
                        video_data=file.read(),
                        title=title,
                    )
                else:
                    result = facebook_service.create_video_story(
                        page_id=profile.page_id,
                        page_access_token=profile.page_access_token,
                        video_url=url,
                        title=title,
                    )

            # Save to ContentCalendar for Recent Activity
            ContentCalendar.objects.create(
                user=request.user,
                title=f"Facebook Story ({story_type.title()})",
                content="Story posted via Facebook Page",
                platforms=["facebook"],
                scheduled_date=timezone.now(),
                status="published",
                post_results={
                    "facebook": {
                        "id": result.get("id"),
                        "type": "story",
                        "media_type": story_type,
                        "created_at": timezone.now().isoformat(),
                    }
                },
            )

            return Response(
                {
                    "story_id": result.get("id"),
                    "type": story_type,
                    "status": "created",
                    "message": "Story created successfully (expires in 24 hours)",
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Facebook story creation failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get(self, request):
        """
        Get active stories for the connected page.

        Returns list of current stories with their status.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token or not profile.page_id:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            user_id = request.user.id

            # Get stories from cache, filtering out expired ones
            now = timezone.now()
            cached_stories = _test_stories_cache.get(user_id, [])

            # Filter active stories (less than 24 hours old)
            active_stories = []
            for story in cached_stories:
                try:
                    created = timezone.datetime.fromisoformat(
                        story["created_at"].replace("Z", "+00:00")
                    )
                    if (now - created).total_seconds() < 86400:
                        active_stories.append(story)
                except (ValueError, KeyError):
                    # Skip malformed or incomplete cached stories
                    # This can happen if cache contains stale/corrupted data
                    continue

            # Update cache with only active stories
            _test_stories_cache[user_id] = active_stories

            return Response(
                {
                    "test_mode": True,
                    "page_id": profile.page_id,
                    "stories": active_stories,
                }
            )

        try:
            stories = facebook_service.get_page_stories(
                page_id=profile.page_id,
                page_access_token=profile.page_access_token,
            )
            return Response(
                {
                    "page_id": profile.page_id,
                    "stories": stories,
                }
            )

        except Exception as e:
            logger.error(f"Facebook stories fetch failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FacebookStoryDeleteView(APIView):
    """
    Delete a Facebook Page Story.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, story_id):
        """
        Delete a story by ID.

        URL params:
        - story_id: The story ID to delete

        Returns:
        - Deletion status
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Facebook account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.page_access_token:
            return Response(
                {"error": "No Facebook Page selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for test mode
        if profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN:
            # Remove from test cache
            user_id = request.user.id
            if user_id in _test_stories_cache:
                _test_stories_cache[user_id] = [
                    s for s in _test_stories_cache[user_id] if s["id"] != story_id
                ]

            return Response(
                {
                    "test_mode": True,
                    "success": True,
                    "story_id": story_id,
                    "message": "Story deleted in test mode",
                }
            )

        try:
            result = facebook_service.delete_story(
                story_id=story_id,
                page_access_token=profile.page_access_token,
            )
            return Response(
                {
                    "success": result.get("success", True),
                    "story_id": story_id,
                    "message": "Story deleted successfully",
                }
            )

        except Exception as e:
            logger.error(f"Facebook story deletion failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# =============================================================================
# Instagram Views
# =============================================================================

# Test mode cache for Instagram posts and stories
_test_instagram_posts_cache = {}
_test_instagram_stories_cache = {}


class InstagramConnectView(APIView):
    """
    Initiate Instagram OAuth 2.0 flow.

    Returns the authorization URL that the frontend should redirect to.
    Instagram uses Facebook OAuth since it's accessed via Graph API.

    NOTE: Instagram API scopes require Meta App Review approval before
    production use. For development/testing, use the "Test Connect" button
    which creates a mock connection.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not instagram_service.is_configured:
            return Response(
                {
                    "error": (
                        "Instagram OAuth not configured. "
                        "Use 'Test Connect' for development testing."
                    ),
                    "hint": (
                        "Instagram API requires Meta App Review for production. "
                        "Click 'Test Connect (No Real Data)' to test the integration."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Generate unique state for CSRF protection
        state = str(uuid.uuid4())

        # Store state in database
        OAuthState.objects.create(
            user=request.user,
            platform="instagram",
            state=state,
        )

        try:
            auth_url = instagram_service.get_authorization_url(state)
            return Response(
                {
                    "authorization_url": auth_url,
                    "note": (
                        "Instagram API scopes may require Meta App Review. "
                        "If you see a permissions error, use 'Test Connect' instead."
                    ),
                }
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InstagramCallbackView(APIView):
    """
    Handle Instagram OAuth 2.0 callback.

    Exchanges authorization code for tokens, finds Instagram Business Account.
    """

    # No authentication required - this is a callback from Facebook
    permission_classes = []

    def get(self, request):
        code = request.GET.get("code")
        state = request.GET.get("state")
        error = request.GET.get("error")

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

        if error:
            error_description = request.GET.get("error_description", error)
            logger.error(f"Instagram OAuth error: {error} - {error_description}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=instagram_auth_failed"
            )

        if not code or not state:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=missing_params"
            )

        # Validate state
        try:
            oauth_state = OAuthState.objects.get(
                state=state,
                platform="instagram",
                used=False,
            )
        except OAuthState.DoesNotExist:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=invalid_state"
            )

        # Mark state as used
        oauth_state.used = True
        oauth_state.save()

        # Check if state is expired (5 minutes)
        if (timezone.now() - oauth_state.created_at).total_seconds() > 300:
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=state_expired"
            )

        try:
            # Exchange code for tokens
            token_data = instagram_service.exchange_code_for_token(code)
            short_lived_token = token_data["access_token"]

            # Get long-lived token
            long_lived_data = instagram_service.get_long_lived_token(short_lived_token)
            user_token = long_lived_data["access_token"]
            token_expires = long_lived_data.get("expires_at")

            # Get user's pages with Instagram Business accounts
            pages = instagram_service.get_user_pages(user_token)

            # Find pages with linked Instagram accounts
            pages_with_instagram = [
                p for p in pages if p.get("instagram_business_account")
            ]

            if not pages_with_instagram:
                error_msg = "No%20Instagram%20Business%20Account%20found."
                error_msg += (
                    "%20Please%20link%20your%20Instagram%20to%20a%20Facebook%20Page."
                )
                return HttpResponseRedirect(
                    f"{frontend_url}/automation?error=no_instagram_found"
                    f"&message={error_msg}"
                )

            # Use first page with Instagram (user can switch later)
            selected_page = pages_with_instagram[0]
            ig_account = selected_page.get("instagram_business_account", {})

            # Create or update the Instagram social profile
            SocialProfile.objects.update_or_create(
                user=oauth_state.user,
                platform="instagram",
                defaults={
                    "access_token": user_token,
                    "token_expires_at": token_expires,
                    "profile_id": ig_account.get("id"),
                    "profile_name": ig_account.get("username"),
                    "profile_url": (
                        f"https://instagram.com/{ig_account.get('username')}"
                    ),
                    "profile_image_url": ig_account.get("profile_picture_url"),
                    "status": "connected",
                    "page_id": selected_page.get("id"),
                    "page_access_token": selected_page.get("access_token"),
                    "instagram_user_id": ig_account.get("id"),
                    "instagram_username": ig_account.get("username"),
                    "instagram_access_token": selected_page.get("access_token"),
                    "last_synced_at": timezone.now(),
                },
            )

            logger.info(
                f"Instagram connected for user {oauth_state.user.email}: "
                f"@{ig_account.get('username')}"
            )
            return HttpResponseRedirect(
                f"{frontend_url}/automation?success=instagram_connected"
            )

        except Exception as e:
            logger.error(f"Instagram OAuth callback failed: {e}")
            return HttpResponseRedirect(
                f"{frontend_url}/automation?error=instagram_callback_failed"
            )


class InstagramDisconnectView(APIView):
    """Disconnect Instagram account."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = SocialProfile.objects.get(user=request.user, platform="instagram")
            profile.disconnect()
            return Response({"message": "Instagram disconnected successfully"})
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )


class InstagramTestConnectView(APIView):
    """
    Create a test Instagram connection for development.

    This allows testing the UI without real Instagram credentials.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, created = SocialProfile.objects.update_or_create(
            user=request.user,
            platform="instagram",
            defaults={
                "access_token": INSTAGRAM_TEST_ACCESS_TOKEN,
                "token_expires_at": timezone.now() + timedelta(days=60),
                "profile_id": "test_ig_user_id",
                "profile_name": "Test Instagram User",
                "profile_url": "https://instagram.com/test_ig_user",
                "profile_image_url": "https://via.placeholder.com/150",
                "status": "connected",
                "instagram_user_id": "test_ig_business_id",
                "instagram_username": "test_ig_user",
                "instagram_access_token": INSTAGRAM_TEST_USER_TOKEN,
                "page_id": "test_fb_page_id",
                "page_access_token": INSTAGRAM_TEST_USER_TOKEN,
                "last_synced_at": timezone.now(),
            },
        )

        return Response(
            {
                "message": "Instagram test account connected",
                "test_mode": True,
                "profile": SocialProfileSerializer(profile).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class InstagramAccountsView(APIView):
    """
    List Instagram Business Accounts available via connected Facebook Pages.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for test mode
        if profile.instagram_access_token == INSTAGRAM_TEST_USER_TOKEN:
            # Return the current account if one is selected
            current_account = None
            if profile.instagram_user_id:
                current_account = {
                    "id": profile.instagram_user_id,
                    "username": profile.instagram_username or "test_ig_user",
                }
            else:
                # Set a default current account in test mode
                current_account = {
                    "id": "test_ig_business_id",
                    "username": "test_ig_user",
                }

            return Response(
                {
                    "test_mode": True,
                    "accounts": [
                        {
                            "id": "test_ig_business_id",
                            "username": "test_ig_user",
                            "name": "Test Instagram Business",
                            "profile_picture_url": "https://via.placeholder.com/150",
                            "followers_count": 10000,
                            "media_count": 50,
                        }
                    ],
                    "current_account": current_account,
                }
            )

        try:
            pages = instagram_service.get_user_pages(profile.access_token)
            accounts = []

            for page in pages:
                ig_account = page.get("instagram_business_account")
                if ig_account:
                    accounts.append(
                        {
                            "id": ig_account.get("id"),
                            "username": ig_account.get("username"),
                            "profile_picture_url": ig_account.get(
                                "profile_picture_url"
                            ),
                            "followers_count": ig_account.get("followers_count"),
                            "page_id": page.get("id"),
                            "page_name": page.get("name"),
                            "page_access_token": page.get("access_token"),
                        }
                    )

            # Include current account info if one is selected
            current_account = None
            if profile.instagram_user_id and profile.instagram_username:
                current_account = {
                    "id": profile.instagram_user_id,
                    "username": profile.instagram_username,
                }
            elif accounts:
                # If no account selected but accounts are available, use the first one
                current_account = {
                    "id": accounts[0]["id"],
                    "username": accounts[0]["username"],
                }

            return Response(
                {
                    "accounts": accounts,
                    "current_account": current_account,
                }
            )

        except Exception as e:
            logger.error(f"Failed to fetch Instagram accounts: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramSelectAccountView(APIView):
    """
    Select which Instagram Business Account to use.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        instagram_user_id = request.data.get("instagram_user_id")
        page_id = request.data.get("page_id")
        page_access_token = request.data.get("page_access_token")

        if not instagram_user_id:
            return Response(
                {"error": "instagram_user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            # Get Instagram account info
            ig_info = instagram_service.get_user_profile(
                instagram_user_id,
                page_access_token or profile.access_token,
            )

            # Update profile with selected account
            profile.instagram_user_id = instagram_user_id
            profile.instagram_username = ig_info.get("username")
            profile.profile_id = instagram_user_id
            profile.profile_name = ig_info.get("username")
            profile.profile_url = f"https://instagram.com/{ig_info.get('username')}"
            profile.profile_image_url = ig_info.get("profile_picture_url")

            if page_id:
                profile.page_id = page_id
            if page_access_token:
                profile.page_access_token = page_access_token
                profile.instagram_access_token = page_access_token

            profile.last_synced_at = timezone.now()
            profile.save()

            return Response(
                {
                    "message": f"Instagram @{ig_info.get('username')} selected",
                    "profile": SocialProfileSerializer(profile).data,
                }
            )

        except Exception as e:
            logger.error(f"Failed to select Instagram account: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramPostView(APIView):
    """
    Create posts on Instagram.

    Instagram publishing is a 2-step process:
    1. Create a media container with the image/video URL
    2. Publish the container

    For scheduled posts, saves to ContentCalendar for Celery processing.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        caption = request.data.get("caption", "")
        title = request.data.get("title", "")  # Optional title for organization
        image_url = request.data.get("image_url")
        video_url = request.data.get("video_url")
        media_type = request.data.get("media_type", "IMAGE")  # IMAGE, VIDEO, REELS
        scheduled_time = request.data.get("scheduled_time")
        share_to_feed = request.data.get("share_to_feed", True)

        if not image_url and not video_url:
            return Response(
                {"error": "image_url or video_url is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.instagram_user_id:
            return Response(
                {"error": "No Instagram Business Account selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get access token
        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            post_id = f"test_ig_post_{uuid.uuid4().hex[:8]}"

            # Store in test cache
            user_id = request.user.id
            if user_id not in _test_instagram_posts_cache:
                _test_instagram_posts_cache[user_id] = []

            _test_instagram_posts_cache[user_id].append(
                {
                    "id": post_id,
                    "caption": caption,
                    "media_type": media_type,
                    "media_url": image_url or video_url,
                    "permalink": f"https://instagram.com/p/{post_id}",
                    "timestamp": timezone.now().isoformat(),
                    "like_count": 0,
                    "comments_count": 0,
                }
            )

            # Store in ContentCalendar for history (same as Facebook test mode)
            # Use provided title, or fallback to caption excerpt, or default
            display_title = (
                title
                if title
                else (
                    caption[:50] + "..."
                    if len(caption) > 50
                    else (caption or "Instagram Post")
                )
            )
            ContentCalendar.objects.create(
                user=request.user,
                title=display_title,
                content=caption,
                platforms=["instagram"],
                scheduled_date=timezone.now(),
                status="published",
                published_at=timezone.now(),
                post_results={"instagram": {"id": post_id}, "id": post_id},
            )

            return Response(
                {
                    "test_mode": True,
                    "id": post_id,
                    "media_type": media_type,
                    "permalink": f"https://instagram.com/p/{post_id}",
                    "message": "Post created in test mode",
                }
            )

        # Handle scheduled posts
        if scheduled_time:
            try:
                from django.utils.dateparse import parse_datetime

                scheduled_dt = parse_datetime(scheduled_time)
                if not scheduled_dt:
                    return Response(
                        {"error": "Invalid scheduled_time format"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Create content calendar entry
                calendar_entry = ContentCalendar.objects.create(
                    user=request.user,
                    title=caption[:100] if caption else "Instagram Post",
                    content=caption,
                    media_urls=[image_url or video_url],
                    platforms=["instagram"],
                    scheduled_date=scheduled_dt,
                    status="scheduled",
                    post_results={
                        "media_type": media_type,
                        "share_to_feed": share_to_feed,
                    },
                )
                calendar_entry.social_profiles.add(profile)

                return Response(
                    {
                        "scheduled": True,
                        "calendar_id": calendar_entry.id,
                        "scheduled_date": scheduled_dt.isoformat(),
                        "message": "Post scheduled for Instagram",
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                logger.error(f"Failed to schedule Instagram post: {e}")
                return Response(
                    {"error": f"Failed to schedule post: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Immediate post
        try:
            # Step 1: Create container
            if media_type == "REELS":
                container = instagram_service.create_reel_container(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    video_url=video_url,
                    caption=caption,
                    share_to_feed=share_to_feed,
                )
            else:
                container = instagram_service.create_media_container(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    image_url=image_url,
                    video_url=video_url,
                    caption=caption,
                    media_type=media_type,
                )

            container_id = container.get("id")

            # For videos, we need to wait for processing
            if media_type in ("VIDEO", "REELS"):
                # Poll for status (in production, use Celery task)
                import time

                for _ in range(30):  # Wait up to 30 seconds
                    status_resp = instagram_service.check_container_status(
                        container_id, access_token
                    )
                    status_code = status_resp.get("status_code")

                    if status_code == "FINISHED":
                        break
                    elif status_code == "ERROR":
                        return Response(
                            {
                                "error": "Video processing failed",
                                "details": status_resp.get("status"),
                            },
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )
                    time.sleep(1)

            # Step 2: Publish
            result = instagram_service.publish_media(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
                container_id=container_id,
            )

            media_id = result.get("id")

            # Get published media details
            media = instagram_service.get_media(media_id, access_token)

            return Response(
                {
                    "id": media_id,
                    "media_type": media.get("media_type"),
                    "permalink": media.get("permalink"),
                    "media_url": media.get("media_url"),
                    "timestamp": media.get("timestamp"),
                    "message": "Post published to Instagram",
                }
            )

        except Exception as e:
            logger.error(f"Instagram post creation failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramCarouselPostView(APIView):
    """
    Create carousel (multi-image) posts on Instagram.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        caption = request.data.get("caption", "")
        title = request.data.get("title", "")  # Optional title for organization
        # Accept both image_urls (frontend) and media_urls (API docs) for flexibility
        media_urls = request.data.get("media_urls") or request.data.get(
            "image_urls", []
        )

        if len(media_urls) < 2:
            return Response(
                {"error": "Carousel requires at least 2 images"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(media_urls) > 10:
            return Response(
                {"error": "Carousel supports maximum 10 images"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not profile.instagram_user_id:
            return Response(
                {"error": "No Instagram Business Account selected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            post_id = f"test_ig_carousel_{uuid.uuid4().hex[:8]}"

            user_id = request.user.id
            if user_id not in _test_instagram_posts_cache:
                _test_instagram_posts_cache[user_id] = []

            _test_instagram_posts_cache[user_id].append(
                {
                    "id": post_id,
                    "caption": caption,
                    "media_type": "CAROUSEL_ALBUM",
                    "media_url": media_urls[0],
                    "children": [{"media_url": url} for url in media_urls],
                    "permalink": f"https://instagram.com/p/{post_id}",
                    "timestamp": timezone.now().isoformat(),
                    "like_count": 0,
                    "comments_count": 0,
                }
            )

            # Store in ContentCalendar for history (same as Facebook test mode)
            display_title = (
                title
                if title
                else (
                    caption[:50] + "..."
                    if len(caption) > 50
                    else (caption or "Instagram Carousel")
                )
            )
            ContentCalendar.objects.create(
                user=request.user,
                title=display_title,
                content=caption,
                platforms=["instagram"],
                scheduled_date=timezone.now(),
                status="published",
                published_at=timezone.now(),
                post_results={
                    "instagram": {"id": post_id, "media_type": "CAROUSEL_ALBUM"},
                    "id": post_id,
                },
            )

            return Response(
                {
                    "test_mode": True,
                    "id": post_id,
                    "media_type": "CAROUSEL_ALBUM",
                    "permalink": f"https://instagram.com/p/{post_id}",
                    "message": "Carousel created in test mode",
                }
            )

        try:
            # Step 1: Create carousel item containers
            item_ids = []
            for url in media_urls:
                is_video = any(ext in url.lower() for ext in [".mp4", ".mov", ".avi"])
                item = instagram_service.create_carousel_item_container(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    image_url=None if is_video else url,
                    video_url=url if is_video else None,
                )
                item_ids.append(item.get("id"))

            # Step 2: Create carousel container
            carousel = instagram_service.create_carousel_container(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
                children=item_ids,
                caption=caption,
            )

            # Step 3: Publish
            result = instagram_service.publish_media(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
                container_id=carousel.get("id"),
            )

            media_id = result.get("id")
            media = instagram_service.get_media(media_id, access_token)

            return Response(
                {
                    "id": media_id,
                    "media_type": "CAROUSEL_ALBUM",
                    "permalink": media.get("permalink"),
                    "timestamp": media.get("timestamp"),
                    "message": "Carousel published to Instagram",
                }
            )

        except Exception as e:
            logger.error(f"Instagram carousel creation failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramStoryView(APIView):
    """
    Create and list Instagram Stories.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get active stories."""
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            user_id = request.user.id
            stories = _test_instagram_stories_cache.get(user_id, [])
            return Response(
                {
                    "test_mode": True,
                    "stories": stories,
                }
            )

        try:
            stories = instagram_service.get_stories(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
            )
            return Response({"stories": stories})

        except Exception as e:
            logger.error(f"Failed to fetch Instagram stories: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        """Create a new story."""
        image_url = request.data.get("image_url")
        video_url = request.data.get("video_url")

        if not image_url and not video_url:
            return Response(
                {"error": "image_url or video_url is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            story_id = f"test_ig_story_{uuid.uuid4().hex[:8]}"

            user_id = request.user.id
            if user_id not in _test_instagram_stories_cache:
                _test_instagram_stories_cache[user_id] = []

            _test_instagram_stories_cache[user_id].append(
                {
                    "id": story_id,
                    "media_type": "VIDEO" if video_url else "IMAGE",
                    "media_url": video_url or image_url,
                    "timestamp": timezone.now().isoformat(),
                }
            )

            # Save to ContentCalendar for Recent Activity
            ContentCalendar.objects.create(
                user=request.user,
                title=f"Instagram Story ({'Video' if video_url else 'Image'})",
                content="Story posted via Instagram",
                platforms=["instagram"],
                media_urls=[video_url or image_url],
                scheduled_date=timezone.now(),
                status="published",
                post_results={
                    "instagram": {
                        "id": story_id,
                        "type": "story",
                        "media_type": "VIDEO" if video_url else "IMAGE",
                        "media_url": video_url or image_url,
                        "test_mode": True,
                    }
                },
            )

            return Response(
                {
                    "test_mode": True,
                    "id": story_id,
                    "message": "Story created in test mode",
                }
            )

        try:
            # Create story container
            container = instagram_service.create_story_container(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
                image_url=image_url,
                video_url=video_url,
            )

            container_id = container.get("id")

            # For videos, wait for processing
            if video_url:
                import time

                for _ in range(30):
                    status_resp = instagram_service.check_container_status(
                        container_id, access_token
                    )
                    if status_resp.get("status_code") == "FINISHED":
                        break
                    elif status_resp.get("status_code") == "ERROR":
                        return Response(
                            {"error": "Story video processing failed"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )
                    time.sleep(1)

            # Publish story
            result = instagram_service.publish_media(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
                container_id=container_id,
            )

            # Save to ContentCalendar for Recent Activity
            ContentCalendar.objects.create(
                user=request.user,
                title=f"Instagram Story ({'Video' if video_url else 'Image'})",
                content="Story posted via Instagram",
                platforms=["instagram"],
                media_urls=[video_url or image_url],
                scheduled_date=timezone.now(),
                status="published",
                post_results={
                    "instagram": {
                        "id": result.get("id"),
                        "type": "story",
                        "media_type": "VIDEO" if video_url else "IMAGE",
                        "media_url": video_url or image_url,
                    }
                },
            )

            return Response(
                {
                    "id": result.get("id"),
                    "message": "Story published to Instagram",
                }
            )

        except Exception as e:
            logger.error(f"Instagram story creation failed: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramAnalyticsView(APIView):
    """
    Get Instagram account and media insights.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, media_id=None):
        """
        Get account insights or specific media insights.

        If media_id is provided, returns insights for that media.
        Otherwise, returns account-level insights.
        """
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            if media_id:
                return Response(
                    {
                        "test_mode": True,
                        "media_id": media_id,
                        "insights": {
                            "engagement": 150,
                            "impressions": 1500,
                            "reach": 1200,
                            "saved": 25,
                        },
                    }
                )
            else:
                return Response(
                    {
                        "test_mode": True,
                        "account": {
                            "id": profile.instagram_user_id,
                            "username": profile.instagram_username,
                            "followers_count": 10000,
                            "follows_count": 500,
                            "media_count": 50,
                        },
                        "insights": {
                            "impressions": 50000,
                            "reach": 40000,
                            "follower_count": 10000,
                            "profile_views": 1200,
                            "website_clicks": 150,
                        },
                        "recent_posts": _test_instagram_posts_cache.get(
                            request.user.id, []
                        )[:6],
                    }
                )

        try:
            if media_id:
                # Get media info first to determine type
                media = instagram_service.get_media(media_id, access_token)
                media_type = media.get("media_type", "IMAGE")

                insights = instagram_service.get_media_insights(
                    media_id=media_id,
                    access_token=access_token,
                    media_type=media_type,
                )

                return Response(
                    {
                        "media_id": media_id,
                        "media_type": media_type,
                        "insights": insights,
                        "media": media,
                    }
                )
            else:
                # Get account info and insights
                account = instagram_service.get_user_profile(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                )

                insights = instagram_service.get_account_insights(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    period="day",
                )

                # Get recent posts
                recent_posts = instagram_service.get_user_media(
                    instagram_user_id=profile.instagram_user_id,
                    access_token=access_token,
                    limit=6,
                )

                return Response(
                    {
                        "account": account,
                        "insights": insights,
                        "recent_posts": recent_posts,
                    }
                )

        except Exception as e:
            logger.error(f"Failed to fetch Instagram analytics: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramMediaView(APIView):
    """
    Get Instagram media (posts) for the connected account.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = request.query_params.get("limit", 25)

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            posts = _test_instagram_posts_cache.get(request.user.id, [])
            return Response(
                {
                    "test_mode": True,
                    "media": posts,
                }
            )

        try:
            media = instagram_service.get_user_media(
                instagram_user_id=profile.instagram_user_id,
                access_token=access_token,
                limit=int(limit),
            )
            return Response({"media": media})

        except Exception as e:
            logger.error(f"Failed to fetch Instagram media: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramCommentsView(APIView):
    """
    Get and reply to comments on Instagram media.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, media_id):
        """Get comments on a media item."""
        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "media_id": media_id,
                    "comments": [
                        {
                            "id": "test_comment_1",
                            "text": "Great post!",
                            "username": "test_follower",
                            "timestamp": timezone.now().isoformat(),
                            "like_count": 5,
                        }
                    ],
                }
            )

        try:
            comments = instagram_service.get_media_comments(
                media_id=media_id,
                access_token=access_token,
            )
            return Response(
                {
                    "media_id": media_id,
                    "comments": comments,
                }
            )

        except Exception as e:
            logger.error(f"Failed to fetch Instagram comments: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request, media_id):
        """Reply to a comment."""
        comment_id = request.data.get("comment_id")
        message = request.data.get("message")

        if not comment_id or not message:
            return Response(
                {"error": "comment_id and message are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        access_token = profile.instagram_access_token or profile.page_access_token

        # Check for test mode
        if access_token == INSTAGRAM_TEST_USER_TOKEN:
            return Response(
                {
                    "test_mode": True,
                    "id": f"test_reply_{uuid.uuid4().hex[:8]}",
                    "message": "Reply created in test mode",
                }
            )

        try:
            result = instagram_service.reply_to_comment(
                comment_id=comment_id,
                access_token=access_token,
                message=message,
            )
            return Response(
                {
                    "id": result.get("id"),
                    "message": "Reply posted successfully",
                }
            )

        except Exception as e:
            logger.error(f"Failed to reply to Instagram comment: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InstagramWebhookView(APIView):
    """
    Handle Instagram webhook verification and events.
    """

    permission_classes = []  # Webhooks don't use authentication

    def get(self, request):
        """Handle webhook verification challenge."""
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and instagram_service.verify_webhook_token(token):
            logger.info("Instagram webhook verified")
            return Response(int(challenge))
        else:
            logger.warning("Instagram webhook verification failed")
            return Response(
                {"error": "Verification failed"},
                status=status.HTTP_403_FORBIDDEN,
            )

    def post(self, request):
        """Handle incoming webhook events."""
        from .models import InstagramWebhookEvent

        # Verify signature
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not instagram_service.verify_webhook_signature(request.body, signature):
            logger.warning("Instagram webhook signature verification failed")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Process webhook payload
        payload = request.data

        # Instagram webhooks come under 'instagram' object
        if payload.get("object") == "instagram":
            for entry in payload.get("entry", []):
                ig_user_id = entry.get("id")

                for change in entry.get("changes", []):
                    field = change.get("field")
                    value = change.get("value")

                    # Create webhook event record
                    InstagramWebhookEvent.objects.create(
                        event_type=field,
                        instagram_user_id=ig_user_id,
                        sender_id=value.get("from", {}).get("id") if value else None,
                        media_id=value.get("media_id") if value else None,
                        payload=change,
                    )

                    logger.info(
                        f"Instagram webhook event: {field} for user {ig_user_id}"
                    )

        return Response({"received": True})


class InstagramWebhookEventsView(APIView):
    """
    Get webhook events for the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import InstagramWebhookEvent
        from datetime import datetime, timedelta

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        limit = request.query_params.get("limit", 50)
        unread_only = request.query_params.get("unread_only", "false").lower() == "true"

        # Check for test mode
        if profile.instagram_access_token == INSTAGRAM_TEST_USER_TOKEN:
            # Return simulated webhook events for test mode
            now = datetime.now()
            test_events = [
                {
                    "id": 1,
                    "event_type": "comments",
                    "event_type_display": "Comment on Post",
                    "sender_id": "test_user_123",
                    "media_id": "17895695668004555",
                    "payload": {
                        "text": "Great content! 🔥",
                        "from": {"id": "test_user_123", "username": "test_follower"},
                    },
                    "read": False,
                    "created_at": (now - timedelta(minutes=15)).isoformat(),
                },
                {
                    "id": 2,
                    "event_type": "mentions",
                    "event_type_display": "Mentioned",
                    "sender_id": "test_user_456",
                    "media_id": "17895695668004556",
                    "payload": {
                        "text": "Check out @your_brand!",
                        "from": {"id": "test_user_456", "username": "influencer"},
                    },
                    "read": False,
                    "created_at": (now - timedelta(hours=2)).isoformat(),
                },
                {
                    "id": 3,
                    "event_type": "story_mentions",
                    "event_type_display": "Story Mention",
                    "sender_id": "test_user_789",
                    "media_id": None,
                    "payload": {
                        "story_id": "story_123",
                        "from": {"id": "test_user_789", "username": "fan_account"},
                    },
                    "read": True,
                    "created_at": (now - timedelta(hours=5)).isoformat(),
                },
                {
                    "id": 4,
                    "event_type": "comments",
                    "event_type_display": "Comment on Post",
                    "sender_id": "test_user_101",
                    "media_id": "17895695668004557",
                    "payload": {
                        "text": "Love this! Where can I get one?",
                        "from": {
                            "id": "test_user_101",
                            "username": "potential_customer",
                        },
                    },
                    "read": True,
                    "created_at": (now - timedelta(days=1)).isoformat(),
                },
            ]

            if unread_only:
                test_events = [e for e in test_events if not e["read"]]

            return Response(
                {
                    "test_mode": True,
                    "events": test_events[: int(limit)],
                    "total_count": len(test_events),
                    "unread_count": len([e for e in test_events if not e["read"]]),
                }
            )

        events = InstagramWebhookEvent.objects.filter(
            instagram_user_id=profile.instagram_user_id
        )

        if unread_only:
            events = events.filter(read=False)

        events = events.order_by("-created_at")[: int(limit)]

        return Response(
            {
                "events": [
                    {
                        "id": e.id,
                        "event_type": e.event_type,
                        "event_type_display": e.get_event_type_display(),
                        "sender_id": e.sender_id,
                        "media_id": e.media_id,
                        "payload": e.payload,
                        "read": e.read,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in events
                ],
                "total_count": InstagramWebhookEvent.objects.filter(
                    instagram_user_id=profile.instagram_user_id
                ).count(),
                "unread_count": InstagramWebhookEvent.objects.filter(
                    instagram_user_id=profile.instagram_user_id, read=False
                ).count(),
            }
        )

    def post(self, request):
        """Mark events as read."""
        from .models import InstagramWebhookEvent

        event_ids = request.data.get("event_ids", [])
        mark_all = request.data.get("mark_all", False)

        try:
            profile = SocialProfile.objects.get(
                user=request.user, platform="instagram", status="connected"
            )
        except SocialProfile.DoesNotExist:
            return Response(
                {"error": "Instagram account not connected"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if mark_all:
            updated = InstagramWebhookEvent.objects.filter(
                instagram_user_id=profile.instagram_user_id, read=False
            ).update(read=True)
        else:
            updated = InstagramWebhookEvent.objects.filter(
                id__in=event_ids,
                instagram_user_id=profile.instagram_user_id,
            ).update(read=True)

        return Response(
            {
                "marked_read": updated,
                "message": f"{updated} events marked as read",
            }
        )
