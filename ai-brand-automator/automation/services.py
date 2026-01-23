"""
LinkedIn OAuth and API service.
"""

import requests
import logging
from typing import Optional, List
from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class LinkedInService:
    """
    Service for LinkedIn OAuth 2.0 authentication and API interactions.

    LinkedIn API v2 with OAuth 2.0 (3-legged)
    Documentation:
    https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
    """

    AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    PROFILE_URL = "https://api.linkedin.com/v2/userinfo"

    # Scopes for basic profile access
    SCOPES = [
        "openid",
        "profile",
        "email",
        "w_member_social",  # For posting content
    ]

    def __init__(self):
        self.client_id = getattr(settings, "LINKEDIN_CLIENT_ID", None)
        self.client_secret = getattr(settings, "LINKEDIN_CLIENT_SECRET", None)
        self.redirect_uri = getattr(
            settings,
            "LINKEDIN_REDIRECT_URI",
            "http://localhost:8000/api/v1/automation/linkedin/callback/",
        )

    @property
    def is_configured(self) -> bool:
        """Check if LinkedIn credentials are configured."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str) -> str:
        """
        Generate the LinkedIn OAuth authorization URL.

        Args:
            state: A unique state token to prevent CSRF attacks

        Returns:
            The full authorization URL to redirect the user to
        """
        if not self.is_configured:
            raise ValueError("LinkedIn credentials not configured")

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": " ".join(self.SCOPES),
        }

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange the authorization code for access and refresh tokens.

        Args:
            code: The authorization code from LinkedIn callback

        Returns:
            Dictionary with access_token, expires_in, refresh_token, etc.
        """
        if not self.is_configured:
            raise ValueError("LinkedIn credentials not configured")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiration time
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn token exchange failed: {e}")
            raise Exception(f"Failed to exchange code for token: {str(e)}")

    def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token from the original OAuth flow

        Returns:
            Dictionary with new access_token, expires_in, etc.
        """
        if not self.is_configured:
            raise ValueError("LinkedIn credentials not configured")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiration time
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn token refresh failed: {e}")
            raise Exception(f"Failed to refresh token: {str(e)}")

    def get_user_profile(self, access_token: str) -> dict:
        """
        Fetch the user's LinkedIn profile.

        Args:
            access_token: Valid LinkedIn access token

        Returns:
            Dictionary with user profile information
        """
        try:
            response = requests.get(
                self.PROFILE_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            profile_data = response.json()

            # Normalize the profile data
            return {
                "id": profile_data.get("sub"),
                "name": profile_data.get("name"),
                "email": profile_data.get("email"),
                "picture": profile_data.get("picture"),
                "given_name": profile_data.get("given_name"),
                "family_name": profile_data.get("family_name"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn profile fetch failed: {e}")
            raise Exception(f"Failed to fetch profile: {str(e)}")

    def get_organizations(self, access_token: str) -> list:
        """
        Get LinkedIn Organizations (Company Pages) the user can post to.

        Requires 'w_organization_social' scope to post to organizations.

        Args:
            access_token: Valid LinkedIn access token

        Returns:
            List of organizations the user can administer
        """
        # Get organization access control (pages user can post to)
        base_url = "https://api.linkedin.com/v2/organizationAcls"
        query = "q=roleAssignee&role=ADMINISTRATOR"
        projection = (
            "projection=(elements*"
            "(organization~(id,localizedName,vanityName,"
            "logoV2(original~:playableStreams))))"
        )
        url = f"{base_url}?{query}&{projection}"

        try:
            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )

            if response.status_code == 403:
                # User doesn't have permission or no organization scope
                logger.info("User does not have organization access permissions")
                return []

            response.raise_for_status()
            data = response.json()

            organizations = []
            for element in data.get("elements", []):
                org = element.get("organization~", {})
                if org:
                    org_id = org.get("id")
                    logo_url = None
                    logo_v2 = org.get("logoV2", {})
                    if logo_v2:
                        original = logo_v2.get("original~", {})
                        elements = original.get("elements", [])
                        if elements:
                            logo_url = (
                                elements[0]
                                .get("identifiers", [{}])[0]
                                .get("identifier")
                            )

                    organizations.append(
                        {
                            "id": org_id,
                            "urn": f"urn:li:organization:{org_id}",
                            "name": org.get("localizedName"),
                            "vanity_name": org.get("vanityName"),
                            "logo_url": logo_url,
                        }
                    )

            return organizations

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn organizations fetch failed: {e}")
            return []

    def create_share(
        self,
        access_token: str,
        user_urn: str,
        text: str,
        image_urns: Optional[List[str]] = None,
        video_urn: Optional[str] = None,
    ) -> dict:
        """
        Create a share (post) on LinkedIn.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN (may be just ID or full URN format)
            text: The post content
            image_urns: Optional list of image asset URNs for media posts
            video_urn: Optional video asset URN for video posts
                (takes precedence over images)

        Returns:
            Dictionary with the created post information
        """
        share_url = "https://api.linkedin.com/v2/ugcPosts"

        # Handle URN format: user_urn may be just ID or full URN
        # Normalize to full URN format
        if user_urn.startswith("urn:li:person:"):
            author_urn = user_urn
        else:
            author_urn = f"urn:li:person:{user_urn}"

        # Video takes precedence over images
        if video_urn:
            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "VIDEO",
                        "media": [
                            {
                                "status": "READY",
                                "media": video_urn,
                            }
                        ],
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }
        # Build media content if images provided
        elif image_urns and len(image_urns) > 0:
            # Build media array for the share
            media_items = []
            for urn in image_urns:
                media_items.append(
                    {
                        "status": "READY",
                        "media": urn,
                    }
                )

            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "IMAGE",
                        "media": media_items,
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }
        else:
            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }

        try:
            response = requests.post(
                share_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn share creation failed: {e}")
            raise Exception(f"Failed to create share: {str(e)}")

    def register_image_upload(self, access_token: str, user_urn: str) -> dict:
        """
        Register an image upload with LinkedIn to get an upload URL.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN

        Returns:
            Dictionary with upload URL and asset URN
        """
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"

        # Normalize URN format
        if user_urn.startswith("urn:li:person:"):
            owner_urn = user_urn
        else:
            owner_urn = f"urn:li:person:{user_urn}"

        payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": owner_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        try:
            response = requests.post(
                register_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Extract upload URL and asset URN
            value = data.get("value", {})
            upload_mechanism = value.get("uploadMechanism", {})
            media_artifact = upload_mechanism.get(
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
            )

            return {
                "upload_url": media_artifact.get("uploadUrl"),
                "asset_urn": value.get("asset"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn image registration failed: {e}")
            raise Exception(f"Failed to register image upload: {str(e)}")

    def upload_image(
        self, upload_url: str, image_data: bytes, content_type: str = "image/jpeg"
    ) -> bool:
        """
        Upload image binary data to LinkedIn's upload URL.

        Args:
            upload_url: The upload URL from register_image_upload
            image_data: Binary image data
            content_type: MIME type of the image

        Returns:
            True if upload was successful
        """
        try:
            response = requests.put(
                upload_url,
                data=image_data,
                headers={
                    "Content-Type": content_type,
                },
                timeout=60,  # Longer timeout for uploads
            )
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn image upload failed: {e}")
            raise Exception(f"Failed to upload image: {str(e)}")

    def upload_image_from_url(
        self, access_token: str, user_urn: str, image_url: str
    ) -> str:
        """
        Upload an image from a URL to LinkedIn.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN
            image_url: URL of the image to upload

        Returns:
            The asset URN for the uploaded image
        """
        # Download the image
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image_data = response.content
            content_type = response.headers.get("Content-Type", "image/jpeg")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download image from URL: {e}")
            raise Exception(f"Failed to download image: {str(e)}")

        # Register the upload
        upload_info = self.register_image_upload(access_token, user_urn)
        upload_url = upload_info.get("upload_url")
        asset_urn = upload_info.get("asset_urn")

        if not upload_url or not asset_urn:
            raise Exception("Failed to get upload URL from LinkedIn")

        # Upload the image
        self.upload_image(upload_url, image_data, content_type)

        return asset_urn

    # ==================== VIDEO UPLOAD METHODS ====================

    def register_video_upload(
        self, access_token: str, user_urn: str, file_size: int
    ) -> dict:
        """
        Register a video upload with LinkedIn to get upload instructions.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN
            file_size: Size of the video file in bytes

        Returns:
            Dictionary with upload URLs and asset URN
        """
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"

        # Normalize URN format
        if user_urn.startswith("urn:li:person:"):
            owner_urn = user_urn
        else:
            owner_urn = f"urn:li:person:{user_urn}"

        payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "owner": owner_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
                "supportedUploadMechanism": ["SINGLE_REQUEST_UPLOAD"],
            }
        }

        try:
            response = requests.post(
                register_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Extract upload URL and asset URN
            value = data.get("value", {})
            upload_mechanism = value.get("uploadMechanism", {})
            media_artifact = upload_mechanism.get(
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
            )

            return {
                "upload_url": media_artifact.get("uploadUrl"),
                "asset_urn": value.get("asset"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn video registration failed: {e}")
            raise Exception(f"Failed to register video upload: {str(e)}")

    def upload_video(
        self, upload_url: str, video_data: bytes, content_type: str = "video/mp4"
    ) -> bool:
        """
        Upload video binary data to LinkedIn's upload URL.

        Args:
            upload_url: The upload URL from register_video_upload
            video_data: Binary video data
            content_type: MIME type of the video

        Returns:
            True if upload was successful
        """
        try:
            response = requests.put(
                upload_url,
                data=video_data,
                headers={
                    "Content-Type": content_type,
                },
                timeout=300,  # 5 minutes timeout for video uploads
            )
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn video upload failed: {e}")
            raise Exception(f"Failed to upload video: {str(e)}")

    def check_video_status(self, access_token: str, asset_urn: str) -> dict:
        """
        Check the processing status of an uploaded video.

        Args:
            access_token: Valid LinkedIn access token
            asset_urn: The asset URN from video registration

        Returns:
            Dictionary with status information
        """
        # URL-encode the asset URN
        encoded_urn = asset_urn.replace(":", "%3A")
        status_url = f"https://api.linkedin.com/v2/assets/{encoded_urn}"

        try:
            response = requests.get(
                status_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            recipes = data.get("recipes", [])
            status = "PROCESSING"

            for recipe in recipes:
                recipe_status = recipe.get("status")
                if recipe_status == "AVAILABLE":
                    status = "READY"
                    break
                elif recipe_status == "PROCESSING":
                    status = "PROCESSING"
                elif recipe_status == "FAILED":
                    status = "FAILED"
                    break

            return {
                "status": status,
                "asset_urn": asset_urn,
                "raw_response": data,
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn video status check failed: {e}")
            raise Exception(f"Failed to check video status: {str(e)}")

    def upload_video_file(
        self,
        access_token: str,
        user_urn: str,
        video_data: bytes,
        content_type: str = "video/mp4",
    ) -> dict:
        """
        Upload a video file to LinkedIn.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN
            video_data: Binary video data
            content_type: MIME type of the video

        Returns:
            Dictionary with asset_urn and initial status
        """
        file_size = len(video_data)

        # Register the upload
        upload_info = self.register_video_upload(access_token, user_urn, file_size)
        upload_url = upload_info.get("upload_url")
        asset_urn = upload_info.get("asset_urn")

        if not upload_url or not asset_urn:
            raise Exception("Failed to get upload URL from LinkedIn")

        # Upload the video
        self.upload_video(upload_url, video_data, content_type)

        return {
            "asset_urn": asset_urn,
            "status": "PROCESSING",  # Videos start in processing state
        }

    # ==================== DOCUMENT UPLOAD METHODS ====================

    def register_document_upload(self, access_token: str, user_urn: str) -> dict:
        """
        Register a document upload with LinkedIn to get upload URL.

        LinkedIn Documents API: https://api.linkedin.com/rest/documents

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN

        Returns:
            Dictionary with upload_url and document_urn
        """
        register_url = "https://api.linkedin.com/rest/documents?action=initializeUpload"

        # Normalize URN format
        if user_urn.startswith("urn:li:person:"):
            owner_urn = user_urn
        else:
            owner_urn = f"urn:li:person:{user_urn}"

        payload = {
            "initializeUploadRequest": {
                "owner": owner_urn,
            }
        }

        try:
            response = requests.post(
                register_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202501",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            value = data.get("value", {})
            return {
                "upload_url": value.get("uploadUrl"),
                "document_urn": value.get("document"),
                "upload_url_expires_at": value.get("uploadUrlExpiresAt"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn document registration failed: {e}")
            raise Exception(f"Failed to register document upload: {str(e)}")

    def upload_document(
        self, upload_url: str, document_data: bytes, content_type: str
    ) -> bool:
        """
        Upload document binary data to LinkedIn's upload URL.

        Args:
            upload_url: The upload URL from register_document_upload
            document_data: Binary document data
            content_type: MIME type of the document

        Returns:
            True if upload was successful
        """
        try:
            response = requests.put(
                upload_url,
                data=document_data,
                headers={
                    "Content-Type": content_type,
                },
                timeout=120,  # 2 minutes timeout for document uploads
            )
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn document upload failed: {e}")
            raise Exception(f"Failed to upload document: {str(e)}")

    def check_document_status(self, access_token: str, document_urn: str) -> dict:
        """
        Check the processing status of an uploaded document.

        Args:
            access_token: Valid LinkedIn access token
            document_urn: The document URN from registration

        Returns:
            Dictionary with status information
        """
        # URL-encode the document URN
        encoded_urn = document_urn.replace(":", "%3A")
        status_url = f"https://api.linkedin.com/rest/documents/{encoded_urn}"

        try:
            response = requests.get(
                status_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202501",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status", "PROCESSING")

            return {
                "status": status,
                "document_urn": document_urn,
                "download_url": data.get("downloadUrl"),
                "raw_response": data,
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn document status check failed: {e}")
            raise Exception(f"Failed to check document status: {str(e)}")

    def upload_document_file(
        self,
        access_token: str,
        user_urn: str,
        document_data: bytes,
        content_type: str,
        filename: str = None,
    ) -> dict:
        """
        Upload a document file to LinkedIn.

        Supported formats: PDF, DOC, DOCX, PPT, PPTX
        Max size: 100MB, Max pages: 300

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN
            document_data: Binary document data
            content_type: MIME type of the document
            filename: Optional filename for the document

        Returns:
            Dictionary with document_urn and initial status
        """
        # Register the upload
        upload_info = self.register_document_upload(access_token, user_urn)
        upload_url = upload_info.get("upload_url")
        document_urn = upload_info.get("document_urn")

        if not upload_url or not document_urn:
            raise Exception("Failed to get upload URL from LinkedIn")

        # Upload the document
        self.upload_document(upload_url, document_data, content_type)

        return {
            "document_urn": document_urn,
            "status": "PROCESSING",  # Documents start in processing state
            "filename": filename,
        }

    def get_organization_followers(self, access_token: str, org_id: str = None) -> dict:
        """
        Get follower statistics for the user's network.

        Note: For personal profiles, LinkedIn API v2 doesn't expose follower counts
        directly. This method provides what's available through the API.

        Args:
            access_token: Valid LinkedIn access token
            org_id: Optional organization ID for company page metrics

        Returns:
            Dictionary with follower/connection information
        """
        # For personal profiles, we can get 1st-degree connections count
        # through the connections API (if authorized)
        try:
            # Get network size (connections)
            network_url = (
                "https://api.linkedin.com/v2/networkSizes/"
                "urn:li:person:me?edgeType=CompanyFollowedByMember"
            )

            response = requests.get(
                network_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )

            if response.ok:
                data = response.json()
                return {
                    "first_degree_size": data.get("firstDegreeSize", 0),
                }
            else:
                # API might not be available for this user/scope
                return {"first_degree_size": 0, "note": "Network size unavailable"}

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn network size fetch failed: {e}")
            return {"first_degree_size": 0, "error": str(e)}

    def get_share_statistics(self, access_token: str, share_urn: str) -> dict:
        """
        Get engagement statistics for a specific share/post.

        Args:
            access_token: Valid LinkedIn access token
            share_urn: The share URN (e.g., urn:li:share:12345 or urn:li:ugcPost:12345)

        Returns:
            Dictionary with engagement metrics (likes, comments, shares, impressions)
        """
        # LinkedIn API v2 uses organizationalEntityShareStatistics for org pages
        # For personal shares, we use socialActions API

        try:
            # Get social actions (likes, comments) for the post
            # URL encode the URN
            encoded_urn = share_urn.replace(":", "%3A")

            # Get likes count
            likes_url = (
                f"https://api.linkedin.com/v2/socialActions/{encoded_urn}/likes?count=0"
            )
            comments_url = (
                f"https://api.linkedin.com/v2/socialActions/{encoded_urn}"
                f"/comments?count=0"
            )

            likes_count = 0
            comments_count = 0

            # Fetch likes
            likes_response = requests.get(
                likes_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            if likes_response.ok:
                likes_data = likes_response.json()
                # The paging total gives us the count
                likes_count = likes_data.get("paging", {}).get("total", 0)

            # Fetch comments
            comments_response = requests.get(
                comments_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            if comments_response.ok:
                comments_data = comments_response.json()
                comments_count = comments_data.get("paging", {}).get("total", 0)

            return {
                "share_urn": share_urn,
                "likes": likes_count,
                "comments": comments_count,
                "shares": 0,  # Reshares not easily accessible via v2 API
                "impressions": 0,  # Impressions require organization analytics
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn share statistics fetch failed: {e}")
            return {
                "share_urn": share_urn,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "impressions": 0,
                "error": str(e),
            }

    def get_user_posts(self, access_token: str, user_urn: str, count: int = 20) -> list:
        """
        Get recent posts by the user.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN
            count: Number of posts to fetch (max 100)

        Returns:
            List of post dictionaries with basic info
        """
        # Normalize URN format
        if user_urn.startswith("urn:li:person:"):
            author_urn = user_urn
        else:
            author_urn = f"urn:li:person:{user_urn}"

        encoded_author = author_urn.replace(":", "%3A")

        try:
            # Fetch UGC posts by the author
            base_url = "https://api.linkedin.com/v2/ugcPosts"
            url = (
                f"{base_url}?q=authors&authors=List({encoded_author})"
                f"&count={min(count, 100)}"
            )

            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )

            if response.ok:
                data = response.json()
                posts = []

                for element in data.get("elements", []):
                    post_urn = element.get("id", "")
                    specific_content = element.get("specificContent", {})
                    share_content = specific_content.get(
                        "com.linkedin.ugc.ShareContent", {}
                    )
                    commentary = share_content.get("shareCommentary", {})

                    posts.append(
                        {
                            "post_urn": post_urn,
                            "text": commentary.get("text", ""),
                            "created_time": element.get("created", {}).get("time"),
                            "lifecycle_state": element.get("lifecycleState"),
                        }
                    )

                return posts
            else:
                logger.error(f"Failed to fetch user posts: {response.status_code}")
                return []

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn user posts fetch failed: {e}")
            return []

    def get_analytics_summary(self, access_token: str, user_urn: str) -> dict:
        """
        Get a summary of analytics for the user including profile and post metrics.

        Args:
            access_token: Valid LinkedIn access token
            user_urn: The user's URN

        Returns:
            Dictionary with user metrics and recent post performance
        """
        # Get user profile info
        profile = self.get_user_profile(access_token)

        # Get recent posts
        posts = self.get_user_posts(access_token, user_urn, count=20)

        # Get metrics for each post
        posts_with_metrics = []
        total_likes = 0
        total_comments = 0

        for post in posts[:10]:  # Limit to 10 to avoid rate limits
            post_urn = post.get("post_urn")
            if post_urn:
                metrics = self.get_share_statistics(access_token, post_urn)
                post["metrics"] = metrics
                posts_with_metrics.append(post)
                total_likes += metrics.get("likes", 0)
                total_comments += metrics.get("comments", 0)

        # Get network info
        network = self.get_organization_followers(access_token)

        return {
            "profile": {
                "name": profile.get("name"),
                "email": profile.get("email"),
                "picture": profile.get("picture"),
            },
            "network": {
                "connections": network.get("first_degree_size", 0),
            },
            "posts": posts_with_metrics,
            "totals": {
                "total_posts": len(posts),
                "total_likes": total_likes,
                "total_comments": total_comments,
                "engagement_rate": (
                    round(
                        (
                            (total_likes + total_comments)
                            / max(len(posts_with_metrics), 1)
                        )
                        * 100,
                        2,
                    )
                    if posts_with_metrics
                    else 0
                ),
            },
        }

    def delete_share(self, access_token: str, share_urn: str) -> bool:
        """
        Delete a LinkedIn share/post.

        LinkedIn API v2 allows deleting shares via DELETE request.
        The share URN format is: urn:li:share:12345 or urn:li:ugcPost:12345

        Args:
            access_token: Valid LinkedIn access token
            share_urn: The share URN to delete

        Returns:
            True if deletion was successful
        """
        try:
            # URL encode the URN for the API call
            encoded_urn = share_urn.replace(":", "%3A")

            # LinkedIn uses different endpoints for different post types
            if "ugcPost" in share_urn:
                url = f"https://api.linkedin.com/v2/ugcPosts/{encoded_urn}"
            else:
                url = f"https://api.linkedin.com/v2/shares/{encoded_urn}"

            response = requests.delete(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )

            if response.status_code in [200, 204]:
                logger.info(f"LinkedIn share deleted: {share_urn}")
                return True
            else:
                logger.error(
                    f"LinkedIn share deletion failed: "
                    f"{response.status_code} - {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn share deletion failed: {e}")
            raise Exception(f"Failed to delete share: {str(e)}")


# Singleton instance
linkedin_service = LinkedInService()


class TwitterService:
    """
    Service for Twitter/X OAuth 2.0 authentication and API interactions.

    Twitter API v2 with OAuth 2.0 + PKCE (Proof Key for Code Exchange)
    Documentation:
    https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code
    """

    AUTHORIZATION_URL = "https://twitter.com/i/oauth2/authorize"
    TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
    REVOKE_URL = "https://api.twitter.com/2/oauth2/revoke"
    USER_INFO_URL = "https://api.twitter.com/2/users/me"
    TWEET_URL = "https://api.twitter.com/2/tweets"

    # Scopes for Twitter API v2
    # tweet.read - View Tweets
    # tweet.write - Post Tweets
    # users.read - View user profile
    # offline.access - Get refresh token
    SCOPES = [
        "tweet.read",
        "tweet.write",
        "users.read",
        "offline.access",
    ]

    def __init__(self):
        self.client_id = getattr(settings, "TWITTER_CLIENT_ID", None)
        self.client_secret = getattr(settings, "TWITTER_CLIENT_SECRET", None)
        self.redirect_uri = getattr(
            settings,
            "TWITTER_REDIRECT_URI",
            "http://localhost:8000/api/v1/automation/twitter/callback/",
        )

    @property
    def is_configured(self) -> bool:
        """Check if Twitter credentials are configured."""
        return bool(self.client_id and self.client_secret)

    def generate_pkce_pair(self) -> tuple:
        """
        Generate PKCE code verifier and code challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        import hashlib
        import base64
        import secrets

        # Generate code verifier (43-128 characters, URL-safe)
        code_verifier = secrets.token_urlsafe(64)[:128]

        # Generate code challenge (SHA256 hash of verifier, base64url encoded)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        return code_verifier, code_challenge

    def get_authorization_url(self, state: str, code_challenge: str) -> str:
        """
        Generate the Twitter OAuth 2.0 authorization URL with PKCE.

        Args:
            state: A unique state token to prevent CSRF attacks
            code_challenge: PKCE code challenge

        Returns:
            The full authorization URL to redirect the user to
        """
        if not self.is_configured:
            raise ValueError("Twitter credentials not configured")

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, code_verifier: str) -> dict:
        """
        Exchange the authorization code for access and refresh tokens.

        Args:
            code: The authorization code from Twitter callback
            code_verifier: The PKCE code verifier

        Returns:
            Dictionary with access_token, expires_in, refresh_token, etc.
        """
        if not self.is_configured:
            raise ValueError("Twitter credentials not configured")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }

        # Twitter requires Basic Auth with client_id:client_secret
        import base64

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {credentials}",
                },
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiration time
            expires_in = token_data.get("expires_in", 7200)  # Default 2 hours
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter token exchange failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to exchange code for token: {str(e)}")

    def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token from the original OAuth flow

        Returns:
            Dictionary with new access_token, expires_in, etc.
        """
        if not self.is_configured:
            raise ValueError("Twitter credentials not configured")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        import base64

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {credentials}",
                },
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiration time
            expires_in = token_data.get("expires_in", 7200)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter token refresh failed: {e}")
            raise Exception(f"Failed to refresh token: {str(e)}")

    def revoke_token(self, token: str, token_type: str = "access_token") -> bool:
        """
        Revoke an access or refresh token.

        Args:
            token: The token to revoke
            token_type: Either 'access_token' or 'refresh_token'

        Returns:
            True if revocation was successful
        """
        if not self.is_configured:
            raise ValueError("Twitter credentials not configured")

        data = {
            "token": token,
            "token_type_hint": token_type,
        }

        import base64

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        try:
            response = requests.post(
                self.REVOKE_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {credentials}",
                },
                timeout=30,
            )
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter token revocation failed: {e}")
            return False

    def get_user_info(self, access_token: str) -> dict:
        """
        Get the authenticated user's profile information.

        Args:
            access_token: Valid Twitter access token

        Returns:
            Dictionary with user profile data (id, name, username, etc.)
        """
        try:
            response = requests.get(
                self.USER_INFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "user.fields": "id,name,username,profile_image_url,description",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {})

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter user info fetch failed: {e}")
            raise Exception(f"Failed to fetch user info: {str(e)}")

    def create_tweet(
        self,
        access_token: str,
        text: str,
        reply_to_id: Optional[str] = None,
        quote_tweet_id: Optional[str] = None,
        media_ids: Optional[List[str]] = None,
    ) -> dict:
        """
        Create a tweet (post) on Twitter/X.

        Args:
            access_token: Valid Twitter access token
            text: The tweet content (max 280 chars for regular, 25000 for Premium)
            reply_to_id: Optional tweet ID to reply to
            quote_tweet_id: Optional tweet ID to quote
            media_ids: Optional list of media IDs for attachments

        Returns:
            Dictionary with the created tweet information
        """
        payload = {"text": text}

        # Add reply settings if replying to a tweet
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        # Add quote tweet settings
        if quote_tweet_id:
            payload["quote_tweet_id"] = quote_tweet_id

        # Add media if provided
        if media_ids:
            payload["media"] = {"media_ids": media_ids}

        try:
            response = requests.post(
                self.TWEET_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Tweet created successfully: {data.get('data', {})}")
            return data.get("data", {})

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter tweet creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create tweet: {str(e)}")

    def delete_tweet(self, access_token: str, tweet_id: str) -> bool:
        """
        Delete a tweet.

        Args:
            access_token: Valid Twitter access token
            tweet_id: The ID of the tweet to delete

        Returns:
            True if deletion was successful
        """
        try:
            response = requests.delete(
                f"{self.TWEET_URL}/{tweet_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=30,
            )
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter tweet deletion failed: {e}")
            return False

    def get_tweet_metrics(self, access_token: str, tweet_id: str) -> dict:
        """
        Get public metrics for a specific tweet.

        Args:
            access_token: Valid Twitter access token
            tweet_id: The ID of the tweet to get metrics for

        Returns:
            Dictionary with tweet metrics
            (impressions, likes, retweets, replies, quotes)
        """
        try:
            response = requests.get(
                f"{self.TWEET_URL}/{tweet_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "tweet.fields": "public_metrics,created_at,text",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            tweet_data = data.get("data", {})
            metrics = tweet_data.get("public_metrics", {})

            return {
                "tweet_id": tweet_id,
                "text": tweet_data.get("text", ""),
                "created_at": tweet_data.get("created_at"),
                "metrics": {
                    "impressions": metrics.get("impression_count", 0),
                    "likes": metrics.get("like_count", 0),
                    "retweets": metrics.get("retweet_count", 0),
                    "replies": metrics.get("reply_count", 0),
                    "quotes": metrics.get("quote_count", 0),
                    "bookmarks": metrics.get("bookmark_count", 0),
                },
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get tweet metrics: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to get tweet metrics: {str(e)}")

    def get_multiple_tweet_metrics(self, access_token: str, tweet_ids: list) -> list:
        """
        Get public metrics for multiple tweets at once.

        Args:
            access_token: Valid Twitter access token
            tweet_ids: List of tweet IDs to get metrics for (max 100)

        Returns:
            List of tweet metrics dictionaries
        """
        if not tweet_ids:
            return []

        # Twitter API allows max 100 tweets per request
        tweet_ids = tweet_ids[:100]

        try:
            response = requests.get(
                self.TWEET_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "ids": ",".join(tweet_ids),
                    "tweet.fields": "public_metrics,created_at,text",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for tweet_data in data.get("data", []):
                metrics = tweet_data.get("public_metrics", {})
                results.append(
                    {
                        "tweet_id": tweet_data.get("id"),
                        "text": tweet_data.get("text", ""),
                        "created_at": tweet_data.get("created_at"),
                        "metrics": {
                            "impressions": metrics.get("impression_count", 0),
                            "likes": metrics.get("like_count", 0),
                            "retweets": metrics.get("retweet_count", 0),
                            "replies": metrics.get("reply_count", 0),
                            "quotes": metrics.get("quote_count", 0),
                            "bookmarks": metrics.get("bookmark_count", 0),
                        },
                    }
                )

            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get multiple tweet metrics: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to get tweet metrics: {str(e)}")

    def get_user_metrics(self, access_token: str) -> dict:
        """
        Get the authenticated user's profile metrics.

        Args:
            access_token: Valid Twitter access token

        Returns:
            Dictionary with user metrics (followers, following, tweet count)
        """
        try:
            response = requests.get(
                self.USER_INFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "user.fields": (
                        "public_metrics,created_at,description,profile_image_url"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            user_data = data.get("data", {})
            metrics = user_data.get("public_metrics", {})

            return {
                "user_id": user_data.get("id"),
                "username": user_data.get("username"),
                "name": user_data.get("name"),
                "description": user_data.get("description"),
                "profile_image_url": user_data.get("profile_image_url"),
                "created_at": user_data.get("created_at"),
                "metrics": {
                    "followers": metrics.get("followers_count", 0),
                    "following": metrics.get("following_count", 0),
                    "tweets": metrics.get("tweet_count", 0),
                    "listed": metrics.get("listed_count", 0),
                },
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get user metrics: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to get user metrics: {str(e)}")

    def validate_tweet_length(self, text: str, is_premium: bool = False) -> dict:
        """
        Validate tweet length against Twitter's limits.

        Args:
            text: The tweet text to validate
            is_premium: Whether the user has Twitter/X Premium

        Returns:
            Dictionary with is_valid, length, max_length, remaining
        """
        max_length = 25000 if is_premium else 280
        length = len(text)

        return {
            "is_valid": length <= max_length,
            "length": length,
            "max_length": max_length,
            "remaining": max_length - length,
        }

    def upload_media(
        self,
        access_token: str,
        media_data: bytes,
        media_type: str,
        media_category: str = "tweet_image",
    ) -> dict:
        """
        Upload media to Twitter for use in tweets.

        Twitter uses v1.1 media upload endpoint (still required for v2 tweets).
        Documentation: https://developer.twitter.com/en/docs/twitter-api/
            v1/media/upload-media/overview

        Args:
            access_token: Valid Twitter access token
            media_data: The raw bytes of the media file
            media_type: The MIME type (e.g., "image/jpeg", "image/png", "video/mp4")
            media_category: One of "tweet_image", "tweet_gif", "tweet_video"

        Returns:
            Dictionary with media_id and media_id_string
        """
        import base64

        MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"

        # For images under 5MB, use simple upload
        if media_category == "tweet_image" and len(media_data) <= 5 * 1024 * 1024:
            # Simple upload (base64 encoded)
            media_b64 = base64.b64encode(media_data).decode()

            try:
                response = requests.post(
                    MEDIA_UPLOAD_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "media_data": media_b64,
                        "media_category": media_category,
                    },
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()

                logger.info(f"Twitter media uploaded: {data.get('media_id_string')}")
                return {
                    "media_id": data.get("media_id"),
                    "media_id_string": data.get("media_id_string"),
                    "type": data.get("type"),
                    "expires_after_secs": data.get("expires_after_secs"),
                }

            except requests.exceptions.RequestException as e:
                logger.error(f"Twitter media upload failed: {e}")
                if hasattr(e, "response") and e.response is not None:
                    logger.error(f"Response: {e.response.text}")
                    # Check for 403 Forbidden - usually means missing permissions
                    if e.response.status_code == 403:
                        raise Exception(
                            "Twitter media upload forbidden (403). "
                            "Your Twitter Developer app needs 'Basic' "
                            "tier ($100/mo) or ensure 'Read and Write' "
                            "permissions are enabled in the Developer Portal."
                        )
                raise Exception(f"Failed to upload media: {str(e)}")

        # For larger files or videos, use chunked upload
        return self._chunked_media_upload(
            access_token, media_data, media_type, media_category
        )

    def _chunked_media_upload(
        self,
        access_token: str,
        media_data: bytes,
        media_type: str,
        media_category: str,
    ) -> dict:
        """
        Chunked media upload for large files and videos.

        Uses INIT, APPEND, FINALIZE flow.
        """
        import base64

        MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
        total_bytes = len(media_data)

        # INIT phase
        try:
            init_response = requests.post(
                MEDIA_UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                data={
                    "command": "INIT",
                    "total_bytes": total_bytes,
                    "media_type": media_type,
                    "media_category": media_category,
                },
                timeout=30,
            )
            init_response.raise_for_status()
            init_data = init_response.json()
            media_id = init_data["media_id_string"]

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter media INIT failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 403:
                    raise Exception(
                        "Twitter media upload forbidden (403). "
                        "Your Twitter Developer app needs 'Basic' "
                        "tier ($100/mo) or ensure 'Read and Write' "
                        "permissions are enabled in the Developer Portal."
                    )
            raise Exception(f"Failed to initialize media upload: {str(e)}")

        # APPEND phase - upload in chunks
        chunk_size = 4 * 1024 * 1024  # 4MB chunks
        segment_index = 0

        for i in range(0, total_bytes, chunk_size):
            chunk = media_data[i : i + chunk_size]
            chunk_b64 = base64.b64encode(chunk).decode()

            try:
                append_response = requests.post(
                    MEDIA_UPLOAD_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                    data={
                        "command": "APPEND",
                        "media_id": media_id,
                        "media_data": chunk_b64,
                        "segment_index": segment_index,
                    },
                    timeout=120,
                )
                append_response.raise_for_status()
                segment_index += 1

            except requests.exceptions.RequestException as e:
                logger.error(
                    f"Twitter media APPEND failed at segment {segment_index}: {e}"
                )
                raise Exception(f"Failed to upload media chunk: {str(e)}")

        # FINALIZE phase
        try:
            finalize_response = requests.post(
                MEDIA_UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                data={
                    "command": "FINALIZE",
                    "media_id": media_id,
                },
                timeout=30,
            )
            finalize_response.raise_for_status()
            finalize_data = finalize_response.json()

            # Check for async processing (videos/GIFs)
            processing_info = finalize_data.get("processing_info")
            if processing_info:
                logger.info(
                    f"Twitter media {media_id} is processing: {processing_info}"
                )
                return {
                    "media_id": finalize_data.get("media_id"),
                    "media_id_string": media_id,
                    "processing_info": processing_info,
                    "status": "PROCESSING",
                }

            logger.info(f"Twitter media uploaded and ready: {media_id}")
            return {
                "media_id": finalize_data.get("media_id"),
                "media_id_string": media_id,
                "status": "READY",
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter media FINALIZE failed: {e}")
            raise Exception(f"Failed to finalize media upload: {str(e)}")

    def get_media_status(self, access_token: str, media_id: str) -> dict:
        """
        Check the processing status of uploaded media.

        Args:
            access_token: Valid Twitter access token
            media_id: The media_id_string from upload

        Returns:
            Dictionary with processing status
        """
        MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"

        try:
            response = requests.get(
                MEDIA_UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "command": "STATUS",
                    "media_id": media_id,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            processing_info = data.get("processing_info", {})
            state = processing_info.get("state", "succeeded")

            return {
                "media_id": media_id,
                "state": state,
                "check_after_secs": processing_info.get("check_after_secs"),
                "progress_percent": processing_info.get("progress_percent"),
                "error": processing_info.get("error"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter media status check failed: {e}")
            raise Exception(f"Failed to get media status: {str(e)}")


# Singleton instance
twitter_service = TwitterService()


class FacebookService:
    """
    Service for Facebook OAuth 2.0 authentication and Graph API interactions.

    Facebook Graph API for Page management and posting.
    Documentation:
    https://developers.facebook.com/docs/facebook-login/guides/access-tokens
    https://developers.facebook.com/docs/pages-api/
    """

    AUTHORIZATION_URL = "https://www.facebook.com/v18.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
    GRAPH_API_URL = "https://graph.facebook.com/v18.0"

    # Scopes for Facebook Page management
    # Note: Advanced permissions (pages_manage_posts, pages_manage_engagement,
    # pages_read_user_content) require App Review. For development, we use only
    # the basic permissions available without review.
    # See: https://developers.facebook.com/docs/permissions/reference
    #
    # For test users added in the app's Roles section, all permissions work.
    # For production, submit for App Review to get advanced permissions.
    SCOPES = [
        "public_profile",
        "pages_show_list",  # List pages the user manages (no review needed)
    ]

    def __init__(self):
        self.app_id = getattr(settings, "FACEBOOK_APP_ID", None)
        self.app_secret = getattr(settings, "FACEBOOK_APP_SECRET", None)
        self.redirect_uri = getattr(
            settings,
            "FACEBOOK_REDIRECT_URI",
            "http://localhost:8000/api/v1/automation/facebook/callback/",
        )

    @property
    def is_configured(self) -> bool:
        """Check if Facebook credentials are configured."""
        return bool(self.app_id and self.app_secret)

    def get_authorization_url(self, state: str) -> str:
        """
        Generate the Facebook OAuth authorization URL.

        Args:
            state: A unique state token to prevent CSRF attacks

        Returns:
            The full authorization URL to redirect the user to
        """
        if not self.is_configured:
            raise ValueError("Facebook credentials not configured")

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": ",".join(self.SCOPES),
            "response_type": "code",
        }

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange the authorization code for access token.

        Args:
            code: The authorization code from Facebook callback

        Returns:
            Dictionary with access_token, expires_in, etc.
        """
        if not self.is_configured:
            raise ValueError("Facebook credentials not configured")

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "client_secret": self.app_secret,
            "code": code,
        }

        try:
            response = requests.get(
                self.TOKEN_URL,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiration time
            expires_in = token_data.get("expires_in", 5184000)  # Default 60 days
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook token exchange failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to exchange code for token: {str(e)}")

    def get_long_lived_token(self, short_lived_token: str) -> dict:
        """
        Exchange a short-lived token for a long-lived token (60 days).

        Args:
            short_lived_token: The short-lived access token

        Returns:
            Dictionary with long-lived access_token
        """
        if not self.is_configured:
            raise ValueError("Facebook credentials not configured")

        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "fb_exchange_token": short_lived_token,
        }

        try:
            response = requests.get(
                self.TOKEN_URL,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Long-lived tokens last ~60 days
            expires_in = token_data.get("expires_in", 5184000)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook long-lived token exchange failed: {e}")
            raise Exception(f"Failed to get long-lived token: {str(e)}")

    def get_user_info(self, access_token: str) -> dict:
        """
        Get the authenticated user's profile information.

        Args:
            access_token: Valid Facebook access token

        Returns:
            Dictionary with user profile data (id, name, etc.)
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/me",
                params={
                    "access_token": access_token,
                    "fields": "id,name,email,picture.type(large)",
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook user info fetch failed: {e}")
            raise Exception(f"Failed to fetch user info: {str(e)}")

    def get_user_pages(self, access_token: str) -> list:
        """
        Get the list of pages the user manages.

        Args:
            access_token: Valid Facebook user access token

        Returns:
            List of pages with id, name, access_token, category
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/me/accounts",
                params={
                    "access_token": access_token,
                    "fields": "id,name,access_token,category,picture.type(large)",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook pages fetch failed: {e}")
            raise Exception(f"Failed to fetch user pages: {str(e)}")

    def get_page_info(self, page_id: str, page_access_token: str) -> dict:
        """
        Get detailed page information.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token

        Returns:
            Dictionary with page details
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{page_id}",
                params={
                    "access_token": page_access_token,
                    "fields": (
                        "id,name,about,category,fan_count,followers_count,"
                        "picture.type(large),link,username"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook page info fetch failed: {e}")
            raise Exception(f"Failed to fetch page info: {str(e)}")

    def create_page_post(
        self,
        page_id: str,
        page_access_token: str,
        message: str,
        link: Optional[str] = None,
        published: bool = True,
        scheduled_publish_time: Optional[int] = None,
        no_story: bool = False,
    ) -> dict:
        """
        Create a text or link post on a Facebook Page.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            message: The post content
            link: Optional URL to share (generates link preview)
            published: If False, post is unpublished (draft)
            scheduled_publish_time: Unix timestamp for scheduled post
            no_story: If True, the post won't appear in the Page's story

        Returns:
            Dictionary with the created post id
        """
        payload = {
            "message": message,
            "access_token": page_access_token,
            "published": str(published).lower(),
        }

        if link:
            payload["link"] = link

        if scheduled_publish_time and not published:
            payload["scheduled_publish_time"] = scheduled_publish_time

        if no_story:
            payload["no_story"] = "true"

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/feed",
                data=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook post created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook post creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create post: {str(e)}")

    def get_link_preview(self, url: str, access_token: str) -> dict:
        """
        Fetch Open Graph data for a URL to show link preview.

        Args:
            url: The URL to fetch preview for
            access_token: A valid access token

        Returns:
            Dictionary with Open Graph data (title, description, image)
        """
        try:
            # Use the Facebook scrape endpoint to get OG data
            response = requests.post(
                f"{self.GRAPH_API_URL}/",
                data={
                    "id": url,
                    "scrape": "true",
                    "access_token": access_token,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            return {
                "url": url,
                "title": data.get("og_object", {}).get("title", ""),
                "description": data.get("og_object", {}).get("description", ""),
                "image": (
                    data.get("og_object", {}).get("image", [{}])[0].get("url")
                    if isinstance(data.get("og_object", {}).get("image"), list)
                    else data.get("og_object", {}).get("image", {}).get("url")
                ),
                "site_name": data.get("og_object", {}).get("site_name", ""),
                "type": data.get("og_object", {}).get("type", "website"),
                "id": data.get("id"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook link preview fetch failed: {e}")
            # Return basic data if scrape fails
            return {
                "url": url,
                "title": "",
                "description": "",
                "image": None,
                "error": str(e),
            }

    def create_page_photo_post(
        self,
        page_id: str,
        page_access_token: str,
        photo_url: str,
        message: Optional[str] = None,
        published: bool = True,
    ) -> dict:
        """
        Create a photo post on a Facebook Page.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            photo_url: URL of the image to post
            message: Optional caption
            published: If False, post is unpublished

        Returns:
            Dictionary with the created photo post id
        """
        payload = {
            "url": photo_url,
            "access_token": page_access_token,
            "published": str(published).lower(),
        }

        if message:
            payload["message"] = message

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/photos",
                data=payload,
                timeout=60,  # Longer timeout for media
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook photo post created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook photo post creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create photo post: {str(e)}")

    def upload_photo(
        self,
        page_id: str,
        page_access_token: str,
        image_data: bytes,
        message: Optional[str] = None,
    ) -> dict:
        """
        Upload a photo directly from bytes.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            image_data: Raw bytes of the image
            message: Optional caption

        Returns:
            Dictionary with the created photo id
        """
        files = {"source": ("image.jpg", image_data, "image/jpeg")}
        payload = {
            "access_token": page_access_token,
        }

        if message:
            payload["message"] = message

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/photos",
                data=payload,
                files=files,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook photo uploaded: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook photo upload failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to upload photo: {str(e)}")

    def create_unpublished_photo(
        self,
        page_id: str,
        page_access_token: str,
        photo_url: str,
    ) -> dict:
        """
        Create an unpublished photo for use in carousel posts.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            photo_url: URL of the image

        Returns:
            Dictionary with the photo id (for use in attached_media)
        """
        payload = {
            "url": photo_url,
            "access_token": page_access_token,
            "published": "false",  # Must be unpublished for carousel
        }

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/photos",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook unpublished photo created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook unpublished photo creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create unpublished photo: {str(e)}")

    def upload_unpublished_photo(
        self,
        page_id: str,
        page_access_token: str,
        image_data: bytes,
        content_type: str = "image/jpeg",
    ) -> dict:
        """
        Upload an unpublished photo from bytes for use in carousel posts.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            image_data: Raw bytes of the image
            content_type: MIME type of the image

        Returns:
            Dictionary with the photo id (for use in attached_media)
        """
        extension = content_type.split("/")[-1] if "/" in content_type else "jpg"
        files = {"source": (f"image.{extension}", image_data, content_type)}
        payload = {
            "access_token": page_access_token,
            "published": "false",  # Must be unpublished for carousel
        }

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/photos",
                data=payload,
                files=files,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook unpublished photo uploaded: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook unpublished photo upload failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to upload unpublished photo: {str(e)}")

    def create_carousel_post(
        self,
        page_id: str,
        page_access_token: str,
        message: str,
        photo_ids: List[str],
    ) -> dict:
        """
        Create a carousel (multi-photo) post on a Facebook Page.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            message: The post caption/text
            photo_ids: List of unpublished photo IDs (2-10 photos)

        Returns:
            Dictionary with the created post id
        """
        if len(photo_ids) < 2:
            raise ValueError("Carousel posts require at least 2 photos")
        if len(photo_ids) > 10:
            raise ValueError("Carousel posts support maximum 10 photos")

        # Build attached_media parameter
        attached_media = [{"media_fbid": photo_id} for photo_id in photo_ids]

        payload = {
            "message": message,
            "attached_media": attached_media,
            "access_token": page_access_token,
        }

        try:
            # Use json for complex nested data
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/feed",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook carousel post created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook carousel post creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create carousel post: {str(e)}")

    def start_video_upload(
        self,
        page_id: str,
        page_access_token: str,
        file_size: int,
    ) -> dict:
        """
        Start a resumable video upload session.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            file_size: Size of the video in bytes

        Returns:
            Dictionary with upload_session_id and video_id
        """
        payload = {
            "upload_phase": "start",
            "file_size": file_size,
            "access_token": page_access_token,
        }

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/videos",
                data=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook video upload started: {data.get('video_id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook video upload start failed: {e}")
            raise Exception(f"Failed to start video upload: {str(e)}")

    def upload_video_chunk(
        self,
        page_id: str,
        page_access_token: str,
        upload_session_id: str,
        start_offset: int,
        chunk_data: bytes,
    ) -> dict:
        """
        Upload a video chunk in a resumable upload session.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            upload_session_id: The upload session ID
            start_offset: Byte offset to start from
            chunk_data: The chunk bytes

        Returns:
            Dictionary with start_offset and end_offset for next chunk
        """
        files = {"video_file_chunk": ("chunk", chunk_data, "application/octet-stream")}
        payload = {
            "upload_phase": "transfer",
            "upload_session_id": upload_session_id,
            "start_offset": start_offset,
            "access_token": page_access_token,
        }

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/videos",
                data=payload,
                files=files,
                timeout=120,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook video chunk upload failed: {e}")
            raise Exception(f"Failed to upload video chunk: {str(e)}")

    def finish_video_upload(
        self,
        page_id: str,
        page_access_token: str,
        upload_session_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """
        Finish a resumable video upload and publish.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            upload_session_id: The upload session ID
            title: Optional video title
            description: Optional video description

        Returns:
            Dictionary with the video post success status
        """
        payload = {
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "access_token": page_access_token,
        }

        if title:
            payload["title"] = title
        if description:
            payload["description"] = description

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/videos",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook video upload finished: {data}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook video upload finish failed: {e}")
            raise Exception(f"Failed to finish video upload: {str(e)}")

    def upload_video_simple(
        self,
        page_id: str,
        page_access_token: str,
        video_data: bytes,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """
        Simple video upload (for smaller videos under 1GB).

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            video_data: Raw bytes of the video
            title: Optional video title
            description: Optional video description

        Returns:
            Dictionary with the video id
        """
        files = {"source": ("video.mp4", video_data, "video/mp4")}
        payload = {
            "access_token": page_access_token,
        }

        if title:
            payload["title"] = title
        if description:
            payload["description"] = description

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/videos",
                data=payload,
                files=files,
                timeout=600,  # 10 minutes for video upload
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook video uploaded: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook video upload failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to upload video: {str(e)}")

    def get_post(self, post_id: str, access_token: str) -> dict:
        """
        Get details of a specific post.

        Args:
            post_id: The post ID
            access_token: Page access token

        Returns:
            Dictionary with post details
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{post_id}",
                params={
                    "access_token": access_token,
                    "fields": (
                        "id,message,created_time,permalink_url,"
                        "shares,likes.summary(true),comments.summary(true)"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook post fetch failed: {e}")
            raise Exception(f"Failed to fetch post: {str(e)}")

    def delete_post(self, post_id: str, access_token: str) -> bool:
        """
        Delete a post from a Facebook Page.

        Args:
            post_id: The post ID
            access_token: Page access token

        Returns:
            True if deletion was successful
        """
        try:
            response = requests.delete(
                f"{self.GRAPH_API_URL}/{post_id}",
                params={"access_token": access_token},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook post deleted: {post_id}")
            return data.get("success", False)

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook post deletion failed: {e}")
            raise Exception(f"Failed to delete post: {str(e)}")

    def get_page_insights(
        self,
        page_id: str,
        page_access_token: str,
        period: str = "day",
        metrics: Optional[List[str]] = None,
    ) -> dict:
        """
        Get page insights/analytics.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            period: Time period (day, week, days_28)
            metrics: List of metrics to retrieve

        Returns:
            Dictionary with page insights
        """
        if metrics is None:
            metrics = [
                "page_impressions",
                "page_engaged_users",
                "page_fans",
                "page_fan_adds",
                "page_post_engagements",
                "page_views_total",
            ]

        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{page_id}/insights",
                params={
                    "access_token": page_access_token,
                    "metric": ",".join(metrics),
                    "period": period,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Parse the insights into a more usable format
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    insights[metric_name] = values[-1].get("value", 0)

            return insights

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook page insights fetch failed: {e}")
            raise Exception(f"Failed to fetch page insights: {str(e)}")

    def get_post_insights(
        self,
        post_id: str,
        page_access_token: str,
    ) -> dict:
        """
        Get insights for a specific post.

        Args:
            post_id: The post ID
            page_access_token: The page access token

        Returns:
            Dictionary with post insights
        """
        metrics = [
            "post_impressions",
            "post_impressions_unique",
            "post_engaged_users",
            "post_clicks",
            "post_reactions_like_total",
            "post_reactions_love_total",
        ]

        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{post_id}/insights",
                params={
                    "access_token": page_access_token,
                    "metric": ",".join(metrics),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Parse the insights
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    insights[metric_name] = values[0].get("value", 0)

            return insights

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook post insights fetch failed: {e}")
            raise Exception(f"Failed to fetch post insights: {str(e)}")

    def get_page_posts(
        self,
        page_id: str,
        page_access_token: str,
        limit: int = 25,
    ) -> list:
        """
        Get recent posts from a Facebook Page.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            limit: Number of posts to retrieve

        Returns:
            List of posts with engagement metrics
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{page_id}/posts",
                params={
                    "access_token": page_access_token,
                    "fields": (
                        "id,message,created_time,permalink_url,full_picture,"
                        "shares,likes.summary(true),comments.summary(true)"
                    ),
                    "limit": limit,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook page posts fetch failed: {e}")
            raise Exception(f"Failed to fetch page posts: {str(e)}")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify the webhook signature from Facebook.

        Facebook sends a SHA256 signature in the X-Hub-Signature-256 header.

        Args:
            payload: Raw request body
            signature: The X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        import hmac
        import hashlib

        if not self.app_secret:
            logger.warning(
                "Facebook app secret not configured, skipping signature check"
            )
            return True  # Allow in development

        if not signature or not signature.startswith("sha256="):
            logger.warning("Invalid Facebook webhook signature format")
            return False

        expected_signature = (
            "sha256="
            + hmac.new(
                self.app_secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(signature, expected_signature)

    def verify_webhook_token(self, verify_token: str) -> bool:
        """
        Verify the webhook subscription verify token.

        Args:
            verify_token: The hub.verify_token from Facebook

        Returns:
            True if token matches configured value
        """
        configured_token = getattr(settings, "FACEBOOK_WEBHOOK_VERIFY_TOKEN", None)
        if not configured_token:
            logger.warning("FACEBOOK_WEBHOOK_VERIFY_TOKEN not configured")
            return False
        return verify_token == configured_token

    def subscribe_to_page_webhooks(
        self,
        page_id: str,
        page_access_token: str,
        subscribed_fields: Optional[List[str]] = None,
    ) -> dict:
        """
        Subscribe a page to receive webhook events.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            subscribed_fields: List of fields to subscribe to

        Returns:
            Dictionary with subscription status
        """
        if subscribed_fields is None:
            subscribed_fields = [
                "feed",  # Post updates (likes, comments, shares)
                "mention",  # Page mentions
                "ratings",  # Page ratings
            ]

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{page_id}/subscribed_apps",
                data={
                    "access_token": page_access_token,
                    "subscribed_fields": ",".join(subscribed_fields),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook page {page_id} subscribed to webhooks: {data}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook webhook subscription failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to subscribe to webhooks: {str(e)}")

    def unsubscribe_from_page_webhooks(
        self,
        page_id: str,
        page_access_token: str,
    ) -> dict:
        """
        Unsubscribe a page from webhook events.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token

        Returns:
            Dictionary with unsubscription status
        """
        try:
            response = requests.delete(
                f"{self.GRAPH_API_URL}/{page_id}/subscribed_apps",
                params={"access_token": page_access_token},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook page {page_id} unsubscribed from webhooks: {data}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook webhook unsubscription failed: {e}")
            raise Exception(f"Failed to unsubscribe from webhooks: {str(e)}")

    def get_page_webhook_subscriptions(
        self,
        page_id: str,
        page_access_token: str,
    ) -> list:
        """
        Get current webhook subscriptions for a page.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token

        Returns:
            List of subscribed apps with their fields
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{page_id}/subscribed_apps",
                params={"access_token": page_access_token},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook webhook subscriptions fetch failed: {e}")
            raise Exception(f"Failed to get webhook subscriptions: {str(e)}")

    # =========================================================================
    # Facebook Stories Support
    # =========================================================================

    def create_photo_story(
        self,
        page_id: str,
        page_access_token: str,
        photo_url: Optional[str] = None,
        photo_data: Optional[bytes] = None,
    ) -> dict:
        """
        Create a photo story on a Facebook Page.

        Facebook Page Stories require the pages_manage_posts permission.
        Photo requirements:
        - Recommended aspect ratio: 9:16 (vertical)
        - Minimum resolution: 1080x1920 pixels
        - Supported formats: JPEG, PNG
        - Maximum file size: 4MB

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            photo_url: URL of the photo (mutually exclusive with photo_data)
            photo_data: Raw bytes of the photo (mutually exclusive with photo_url)

        Returns:
            Dictionary with the story id
        """
        if not photo_url and not photo_data:
            raise ValueError("Either photo_url or photo_data must be provided")
        if photo_url and photo_data:
            raise ValueError("Only one of photo_url or photo_data can be provided")

        try:
            if photo_url:
                # Create story from URL
                response = requests.post(
                    f"{self.GRAPH_API_URL}/{page_id}/photo_stories",
                    data={
                        "photo_url": photo_url,
                        "access_token": page_access_token,
                    },
                    timeout=60,
                )
            else:
                # Create story from uploaded file
                files = {"photo": ("story.jpg", photo_data, "image/jpeg")}
                response = requests.post(
                    f"{self.GRAPH_API_URL}/{page_id}/photo_stories",
                    data={"access_token": page_access_token},
                    files=files,
                    timeout=120,
                )

            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook photo story created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook photo story creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create photo story: {str(e)}")

    def create_video_story(
        self,
        page_id: str,
        page_access_token: str,
        video_url: Optional[str] = None,
        video_data: Optional[bytes] = None,
        title: Optional[str] = None,
    ) -> dict:
        """
        Create a video story on a Facebook Page.

        Facebook Page Stories require the pages_manage_posts permission.
        Video requirements:
        - Recommended aspect ratio: 9:16 (vertical)
        - Minimum resolution: 720x1280 pixels
        - Duration: 1-60 seconds (recommended 3-15 seconds)
        - Supported formats: MP4, MOV
        - Maximum file size: 4GB

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            video_url: URL of the video (mutually exclusive with video_data)
            video_data: Raw bytes of the video (mutually exclusive with video_url)
            title: Optional title for the video

        Returns:
            Dictionary with the story id and status
        """
        if not video_url and not video_data:
            raise ValueError("Either video_url or video_data must be provided")
        if video_url and video_data:
            raise ValueError("Only one of video_url or video_data can be provided")

        try:
            if video_url:
                # Create story from URL
                payload = {
                    "video_url": video_url,
                    "access_token": page_access_token,
                }
                if title:
                    payload["title"] = title

                response = requests.post(
                    f"{self.GRAPH_API_URL}/{page_id}/video_stories",
                    data=payload,
                    timeout=60,
                )
            else:
                # Create story from uploaded file
                files = {"video": ("story.mp4", video_data, "video/mp4")}
                payload = {"access_token": page_access_token}
                if title:
                    payload["title"] = title

                response = requests.post(
                    f"{self.GRAPH_API_URL}/{page_id}/video_stories",
                    data=payload,
                    files=files,
                    timeout=300,  # 5 minutes for video upload
                )

            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook video story created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook video story creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create video story: {str(e)}")

    def get_page_stories(
        self,
        page_id: str,
        page_access_token: str,
        limit: int = 25,
    ) -> list:
        """
        Get active stories from a Facebook Page.

        Stories are ephemeral and expire after 24 hours.

        Args:
            page_id: The Facebook Page ID
            page_access_token: The page access token
            limit: Number of stories to retrieve

        Returns:
            List of story objects with their status
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{page_id}/stories",
                params={
                    "access_token": page_access_token,
                    "fields": "id,media_type,status,creation_time,url",
                    "limit": limit,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook page stories fetch failed: {e}")
            raise Exception(f"Failed to fetch page stories: {str(e)}")

    def delete_story(
        self,
        story_id: str,
        page_access_token: str,
    ) -> dict:
        """
        Delete a story from a Facebook Page.

        Args:
            story_id: The story ID to delete
            page_access_token: The page access token

        Returns:
            Dictionary with deletion status
        """
        try:
            response = requests.delete(
                f"{self.GRAPH_API_URL}/{story_id}",
                params={"access_token": page_access_token},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Facebook story {story_id} deleted")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook story deletion failed: {e}")
            raise Exception(f"Failed to delete story: {str(e)}")


# Singleton instance
facebook_service = FacebookService()


class InstagramService:
    """
    Service for Instagram Business Account integration via Facebook Graph API.

    Instagram API requires:
    1. A Facebook App with Instagram Graph API enabled
    2. A Facebook Page linked to an Instagram Business Account
    3. User authentication via Facebook OAuth

    Documentation:
    https://developers.facebook.com/docs/instagram-api
    https://developers.facebook.com/docs/instagram-api/guides/content-publishing
    """

    GRAPH_API_URL = "https://graph.facebook.com/v18.0"
    AUTHORIZATION_URL = "https://www.facebook.com/v18.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"

    # Scopes needed for Instagram Business Account access
    # NOTE: Instagram-specific scopes (instagram_basic, instagram_content_publish, etc.)
    # require Meta App Review approval. For development/testing, use the "Test Connect"
    # button in the UI which creates a mock connection without real OAuth.
    #
    # For production with approved app, uncomment the full SCOPES list below.
    # Full scopes (requires App Review):
    # - instagram_basic - Read profile info and media
    # - instagram_content_publish - Publish posts, stories, reels
    # - instagram_manage_comments - Read and reply to comments
    # - instagram_manage_insights - Read insights/analytics
    # - pages_show_list - List Facebook Pages (needed to get IG account)
    # - pages_read_engagement - Read page engagement

    # Development scopes (available without App Review for app admins/testers)
    SCOPES = [
        "public_profile",
        "pages_show_list",
        "pages_read_engagement",
    ]

    # Production scopes (uncomment after Meta App Review approval)
    # SCOPES = [
    #     "public_profile",
    #     "pages_show_list",
    #     "instagram_basic",
    #     "instagram_content_publish",
    #     "instagram_manage_comments",
    #     "instagram_manage_insights",
    #     "pages_read_engagement",
    # ]

    def __init__(self):
        self.app_id = getattr(settings, "INSTAGRAM_APP_ID", None)
        self.app_secret = getattr(settings, "INSTAGRAM_APP_SECRET", None)
        self.redirect_uri = getattr(
            settings,
            "INSTAGRAM_REDIRECT_URI",
            "http://localhost:8000/api/v1/automation/instagram/callback/",
        )

    @property
    def is_configured(self) -> bool:
        """Check if Instagram credentials are configured."""
        return bool(self.app_id and self.app_secret)

    def get_authorization_url(self, state: str) -> str:
        """
        Generate the Instagram OAuth authorization URL.

        Uses Facebook OAuth since Instagram API is accessed via Graph API.

        Args:
            state: A unique state token to prevent CSRF attacks

        Returns:
            The full authorization URL to redirect the user to
        """
        if not self.is_configured:
            raise ValueError("Instagram credentials not configured")

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": ",".join(self.SCOPES),
            "response_type": "code",
        }

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange the authorization code for access token.

        Args:
            code: The authorization code from callback

        Returns:
            Dictionary with access_token, expires_in, etc.
        """
        if not self.is_configured:
            raise ValueError("Instagram credentials not configured")

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "client_secret": self.app_secret,
            "code": code,
        }

        try:
            response = requests.get(
                self.TOKEN_URL,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiration time
            expires_in = token_data.get("expires_in", 5184000)  # Default 60 days
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram token exchange failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to exchange code for token: {str(e)}")

    def get_long_lived_token(self, short_lived_token: str) -> dict:
        """
        Exchange a short-lived token for a long-lived token (60 days).

        Args:
            short_lived_token: The short-lived access token

        Returns:
            Dictionary with long-lived access_token
        """
        if not self.is_configured:
            raise ValueError("Instagram credentials not configured")

        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "fb_exchange_token": short_lived_token,
        }

        try:
            response = requests.get(
                self.TOKEN_URL,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Long-lived tokens last ~60 days
            expires_in = token_data.get("expires_in", 5184000)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram long-lived token exchange failed: {e}")
            raise Exception(f"Failed to get long-lived token: {str(e)}")

    def get_user_pages(self, access_token: str) -> list:
        """
        Get the list of Facebook Pages the user manages.

        Instagram Business accounts are linked to Facebook Pages.

        Args:
            access_token: Valid Facebook user access token

        Returns:
            List of pages with their Instagram Business accounts
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/me/accounts",
                params={
                    "access_token": access_token,
                    "fields": (
                        "id,name,access_token,instagram_business_account"
                        "{id,username,profile_picture_url,followers_count}"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram pages fetch failed: {e}")
            raise Exception(f"Failed to fetch user pages: {str(e)}")

    def get_instagram_account(self, page_id: str, access_token: str) -> dict:
        """
        Get the Instagram Business Account linked to a Facebook Page.

        Args:
            page_id: The Facebook Page ID
            access_token: Page access token

        Returns:
            Dictionary with Instagram account info
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{page_id}",
                params={
                    "access_token": access_token,
                    "fields": (
                        "instagram_business_account"
                        "{id,username,name,profile_picture_url,"
                        "followers_count,follows_count,media_count,biography}"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("instagram_business_account", {})

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram account fetch failed: {e}")
            raise Exception(f"Failed to fetch Instagram account: {str(e)}")

    def get_user_profile(self, instagram_user_id: str, access_token: str) -> dict:
        """
        Get Instagram Business Account profile information.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token

        Returns:
            Dictionary with profile data
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{instagram_user_id}",
                params={
                    "access_token": access_token,
                    "fields": (
                        "id,username,name,profile_picture_url,"
                        "followers_count,follows_count,media_count,biography"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram profile fetch failed: {e}")
            raise Exception(f"Failed to fetch profile: {str(e)}")

    # =========================================================================
    # Content Publishing - Single Image/Video Posts
    # =========================================================================

    def create_media_container(
        self,
        instagram_user_id: str,
        access_token: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        caption: Optional[str] = None,
        media_type: str = "IMAGE",
    ) -> dict:
        """
        Create a media container for publishing.

        Instagram publishing is a 2-step process:
        1. Create a container with the media URL
        2. Publish the container

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            image_url: URL of the image (for IMAGE type)
            video_url: URL of the video (for VIDEO/REELS type)
            caption: Post caption (max 2200 characters)
            media_type: IMAGE, VIDEO, or REELS

        Returns:
            Dictionary with container id
        """
        payload = {
            "access_token": access_token,
        }

        if caption:
            payload["caption"] = caption[:2200]  # Instagram caption limit

        if media_type == "IMAGE" and image_url:
            payload["image_url"] = image_url
        elif media_type in ("VIDEO", "REELS") and video_url:
            payload["video_url"] = video_url
            payload["media_type"] = media_type
        else:
            raise ValueError(f"Invalid media type or missing URL: {media_type}")

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram container created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram container creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create media container: {str(e)}")

    def check_container_status(
        self,
        container_id: str,
        access_token: str,
    ) -> dict:
        """
        Check the status of a media container.

        Video containers take time to process. Poll this endpoint until
        status is FINISHED or ERROR.

        Args:
            container_id: The media container ID
            access_token: Valid access token

        Returns:
            Dictionary with status_code and status
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{container_id}",
                params={
                    "access_token": access_token,
                    "fields": "status_code,status",
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram container status check failed: {e}")
            raise Exception(f"Failed to check container status: {str(e)}")

    def publish_media(
        self,
        instagram_user_id: str,
        access_token: str,
        container_id: str,
    ) -> dict:
        """
        Publish a media container to Instagram.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            container_id: The media container ID to publish

        Returns:
            Dictionary with published media id
        """
        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": access_token,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram media published: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram media publish failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to publish media: {str(e)}")

    # =========================================================================
    # Carousel Posts (Multi-Image)
    # =========================================================================

    def create_carousel_item_container(
        self,
        instagram_user_id: str,
        access_token: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        is_carousel_item: bool = True,
    ) -> dict:
        """
        Create a carousel item container (unpublished).

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            image_url: URL of the image
            video_url: URL of the video
            is_carousel_item: Must be True for carousel items

        Returns:
            Dictionary with container id
        """
        payload = {
            "access_token": access_token,
            "is_carousel_item": "true",
        }

        if image_url:
            payload["image_url"] = image_url
        elif video_url:
            payload["video_url"] = video_url
            payload["media_type"] = "VIDEO"
        else:
            raise ValueError("Either image_url or video_url must be provided")

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram carousel item created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram carousel item creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create carousel item: {str(e)}")

    def create_carousel_container(
        self,
        instagram_user_id: str,
        access_token: str,
        children: List[str],
        caption: Optional[str] = None,
    ) -> dict:
        """
        Create a carousel container with multiple items.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            children: List of carousel item container IDs (2-10 items)
            caption: Post caption

        Returns:
            Dictionary with carousel container id
        """
        if len(children) < 2:
            raise ValueError("Carousel requires at least 2 items")
        if len(children) > 10:
            raise ValueError("Carousel supports maximum 10 items")

        payload = {
            "access_token": access_token,
            "media_type": "CAROUSEL",
            "children": ",".join(children),
        }

        if caption:
            payload["caption"] = caption[:2200]

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram carousel container created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram carousel creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create carousel: {str(e)}")

    # =========================================================================
    # Stories
    # =========================================================================

    def create_story_container(
        self,
        instagram_user_id: str,
        access_token: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
    ) -> dict:
        """
        Create a story media container.

        Stories are vertical (9:16 aspect ratio) and expire after 24 hours.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            image_url: URL of the image
            video_url: URL of the video (max 60 seconds)

        Returns:
            Dictionary with container id
        """
        payload = {
            "access_token": access_token,
            "media_type": "STORIES",
        }

        if image_url:
            payload["image_url"] = image_url
        elif video_url:
            payload["video_url"] = video_url
        else:
            raise ValueError("Either image_url or video_url must be provided")

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram story container created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram story container creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create story container: {str(e)}")

    def get_stories(
        self,
        instagram_user_id: str,
        access_token: str,
    ) -> list:
        """
        Get active stories for the Instagram account.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token

        Returns:
            List of active stories
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/stories",
                params={
                    "access_token": access_token,
                    "fields": "id,media_type,media_url,timestamp,permalink",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram stories fetch failed: {e}")
            raise Exception(f"Failed to fetch stories: {str(e)}")

    # =========================================================================
    # Reels
    # =========================================================================

    def create_reel_container(
        self,
        instagram_user_id: str,
        access_token: str,
        video_url: str,
        caption: Optional[str] = None,
        cover_url: Optional[str] = None,
        share_to_feed: bool = True,
    ) -> dict:
        """
        Create a Reel media container.

        Reels are short-form videos (max 90 seconds).

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            video_url: URL of the video
            caption: Reel caption
            cover_url: URL of the cover image (optional)
            share_to_feed: Whether to also share to feed

        Returns:
            Dictionary with container id
        """
        payload = {
            "access_token": access_token,
            "media_type": "REELS",
            "video_url": video_url,
            "share_to_feed": str(share_to_feed).lower(),
        }

        if caption:
            payload["caption"] = caption[:2200]

        if cover_url:
            payload["cover_url"] = cover_url

        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media",
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram reel container created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram reel container creation failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create reel container: {str(e)}")

    # =========================================================================
    # Media Management
    # =========================================================================

    def get_user_media(
        self,
        instagram_user_id: str,
        access_token: str,
        limit: int = 25,
    ) -> list:
        """
        Get recent media (posts) from the Instagram account.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            limit: Number of posts to retrieve

        Returns:
            List of media objects
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/media",
                params={
                    "access_token": access_token,
                    "fields": (
                        "id,caption,media_type,media_url,permalink,"
                        "thumbnail_url,timestamp,like_count,comments_count"
                    ),
                    "limit": limit,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram media fetch failed: {e}")
            raise Exception(f"Failed to fetch media: {str(e)}")

    def get_media(
        self,
        media_id: str,
        access_token: str,
    ) -> dict:
        """
        Get details of a specific media item.

        Args:
            media_id: The media ID
            access_token: Valid access token

        Returns:
            Dictionary with media details
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{media_id}",
                params={
                    "access_token": access_token,
                    "fields": (
                        "id,caption,media_type,media_url,permalink,"
                        "thumbnail_url,timestamp,like_count,comments_count,"
                        "children{id,media_type,media_url}"
                    ),
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram media fetch failed: {e}")
            raise Exception(f"Failed to fetch media: {str(e)}")

    def delete_media(
        self,
        media_id: str,
        access_token: str,
    ) -> bool:
        """
        Delete a media item.

        Note: Instagram API doesn't support deleting via Graph API.
        This will return False with a warning.

        Args:
            media_id: The media ID to delete
            access_token: Valid access token

        Returns:
            False (deletion not supported via API)
        """
        # Instagram Graph API doesn't support media deletion
        logger.warning(
            f"Instagram media deletion not supported via API. "
            f"Media {media_id} must be deleted from the Instagram app."
        )
        return False

    # =========================================================================
    # Comments
    # =========================================================================

    def get_media_comments(
        self,
        media_id: str,
        access_token: str,
        limit: int = 50,
    ) -> list:
        """
        Get comments on a media item.

        Args:
            media_id: The media ID
            access_token: Valid access token
            limit: Number of comments to retrieve

        Returns:
            List of comments
        """
        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{media_id}/comments",
                params={
                    "access_token": access_token,
                    "fields": "id,text,timestamp,username,like_count,replies{id,text}",
                    "limit": limit,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram comments fetch failed: {e}")
            raise Exception(f"Failed to fetch comments: {str(e)}")

    def reply_to_comment(
        self,
        comment_id: str,
        access_token: str,
        message: str,
    ) -> dict:
        """
        Reply to a comment.

        Args:
            comment_id: The comment ID to reply to
            access_token: Valid access token
            message: The reply message

        Returns:
            Dictionary with created reply id
        """
        try:
            response = requests.post(
                f"{self.GRAPH_API_URL}/{comment_id}/replies",
                data={
                    "access_token": access_token,
                    "message": message,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram reply created: {data.get('id')}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram reply creation failed: {e}")
            raise Exception(f"Failed to reply to comment: {str(e)}")

    def delete_comment(
        self,
        comment_id: str,
        access_token: str,
    ) -> bool:
        """
        Delete a comment or reply.

        Args:
            comment_id: The comment ID to delete
            access_token: Valid access token

        Returns:
            True if deletion was successful
        """
        try:
            response = requests.delete(
                f"{self.GRAPH_API_URL}/{comment_id}",
                params={"access_token": access_token},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"Instagram comment deleted: {comment_id}")
            return data.get("success", False)

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram comment deletion failed: {e}")
            raise Exception(f"Failed to delete comment: {str(e)}")

    # =========================================================================
    # Analytics / Insights
    # =========================================================================

    def get_account_insights(
        self,
        instagram_user_id: str,
        access_token: str,
        period: str = "day",
        metrics: Optional[List[str]] = None,
    ) -> dict:
        """
        Get account-level insights.

        Args:
            instagram_user_id: Instagram Business Account ID
            access_token: Valid access token
            period: Time period (day, week, days_28, lifetime)
            metrics: List of metrics to retrieve

        Returns:
            Dictionary with account insights
        """
        if metrics is None:
            metrics = [
                "impressions",
                "reach",
                "follower_count",
                "profile_views",
                "website_clicks",
            ]

        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{instagram_user_id}/insights",
                params={
                    "access_token": access_token,
                    "metric": ",".join(metrics),
                    "period": period,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Parse insights into a more usable format
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    insights[metric_name] = values[-1].get("value", 0)

            return insights

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram account insights fetch failed: {e}")
            raise Exception(f"Failed to fetch account insights: {str(e)}")

    def get_media_insights(
        self,
        media_id: str,
        access_token: str,
        media_type: str = "IMAGE",
    ) -> dict:
        """
        Get insights for a specific media item.

        Args:
            media_id: The media ID
            access_token: Valid access token
            media_type: Type of media (IMAGE, VIDEO, CAROUSEL_ALBUM, REELS)

        Returns:
            Dictionary with media insights
        """
        # Different metrics available based on media type
        if media_type == "VIDEO":
            metrics = [
                "engagement",
                "impressions",
                "reach",
                "saved",
                "video_views",
            ]
        elif media_type == "REELS":
            metrics = [
                "comments",
                "likes",
                "reach",
                "saved",
                "shares",
                "plays",
                "total_interactions",
            ]
        elif media_type == "CAROUSEL_ALBUM":
            metrics = [
                "carousel_album_engagement",
                "carousel_album_impressions",
                "carousel_album_reach",
                "carousel_album_saved",
            ]
        else:  # IMAGE
            metrics = [
                "engagement",
                "impressions",
                "reach",
                "saved",
            ]

        try:
            response = requests.get(
                f"{self.GRAPH_API_URL}/{media_id}/insights",
                params={
                    "access_token": access_token,
                    "metric": ",".join(metrics),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Parse insights
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    insights[metric_name] = values[0].get("value", 0)

            return insights

        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram media insights fetch failed: {e}")
            raise Exception(f"Failed to fetch media insights: {str(e)}")

    # =========================================================================
    # Webhooks
    # =========================================================================

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify the webhook signature from Instagram/Facebook.

        Args:
            payload: Raw request body
            signature: The X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        import hmac
        import hashlib

        if not self.app_secret:
            logger.warning(
                "Instagram app secret not configured, skipping signature check"
            )
            return True  # Allow in development

        if not signature or not signature.startswith("sha256="):
            logger.warning("Invalid Instagram webhook signature format")
            return False

        expected_signature = (
            "sha256="
            + hmac.new(
                self.app_secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(signature, expected_signature)

    def verify_webhook_token(self, verify_token: str) -> bool:
        """
        Verify the webhook subscription verify token.

        Args:
            verify_token: The hub.verify_token from the request

        Returns:
            True if token matches configured value
        """
        configured_token = getattr(settings, "INSTAGRAM_WEBHOOK_VERIFY_TOKEN", None)
        if not configured_token:
            logger.warning("INSTAGRAM_WEBHOOK_VERIFY_TOKEN not configured")
            return False
        return verify_token == configured_token


# Singleton instance
instagram_service = InstagramService()


class GoogleBusinessService:
    """
    Service for Google Business Profile API integration.

    Supports dual-mode operation:
    - Mock Mode: Works without API credentials (for development/testing)
    - Real Mode: Uses actual GBP APIs (requires approved credentials)

    APIs Used (Real Mode):
    - Account Management API: List/manage GBP accounts
    - Business Information API: Create/update locations

    Docs: https://developers.google.com/my-business/content/overview
    """

    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    # GBP API endpoints
    ACCOUNT_MANAGEMENT_URL = "https://mybusinessaccountmanagement.googleapis.com/v1"
    BUSINESS_INFO_URL = "https://mybusinessbusinessinformation.googleapis.com/v1"

    # OAuth scopes for GBP
    SCOPES = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/business.manage",  # Full GBP access
    ]

    # Mock data constants
    MOCK_ACCESS_TOKEN = "gbp_mock_access_token_12345"
    MOCK_REFRESH_TOKEN = "gbp_mock_refresh_token_67890"

    def __init__(self):
        self.client_id = getattr(settings, "GOOGLE_BUSINESS_CLIENT_ID", None)
        self.client_secret = getattr(settings, "GOOGLE_BUSINESS_CLIENT_SECRET", None)
        self.redirect_uri = getattr(
            settings,
            "GOOGLE_BUSINESS_REDIRECT_URI",
            "http://localhost:8000/api/v1/automation/google-business/callback/",
        )

    @property
    def is_configured(self) -> bool:
        """Check if real GBP API credentials are configured."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode."""
        return not self.is_configured

    # ============= MOCK DATA GENERATORS =============

    def _get_mock_accounts(self) -> List[dict]:
        """Return mock GBP accounts for testing."""
        return [
            {
                "name": "accounts/123456789",
                "accountName": "My Business Account",
                "type": "PERSONAL",
                "role": "PRIMARY_OWNER",
                "state": {"status": "VERIFIED"},
            },
            {
                "name": "accounts/987654321",
                "accountName": "Secondary Business",
                "type": "LOCATION_GROUP",
                "role": "OWNER",
                "state": {"status": "VERIFIED"},
            },
        ]

    def _get_mock_locations(self, account_id: str) -> List[dict]:
        """Return mock locations for testing."""
        # Extract numeric ID from account_id like "accounts/123456789"
        numeric_id = account_id.split("/")[-1] if "/" in account_id else account_id
        return [
            {
                "name": f"locations/loc_{numeric_id}_001",
                "title": "Downtown Coffee Shop",
                "storefrontAddress": {
                    "addressLines": ["123 Main Street"],
                    "locality": "San Francisco",
                    "administrativeArea": "CA",
                    "postalCode": "94102",
                    "regionCode": "US",
                },
                "primaryPhone": "+1-415-555-0100",
                "websiteUri": "https://example.com",
                "primaryCategory": {
                    "name": "categories/gcid:coffee_shop",
                    "displayName": "Coffee shop",
                },
                "metadata": {
                    "hasGoogleUpdated": False,
                    "canOperateLodgingData": False,
                },
            },
            {
                "name": f"locations/loc_{numeric_id}_002",
                "title": "Uptown Bakery",
                "storefrontAddress": {
                    "addressLines": ["456 Oak Avenue", "Suite 100"],
                    "locality": "San Francisco",
                    "administrativeArea": "CA",
                    "postalCode": "94108",
                    "regionCode": "US",
                },
                "primaryPhone": "+1-415-555-0200",
                "websiteUri": "https://bakery.example.com",
                "primaryCategory": {
                    "name": "categories/gcid:bakery",
                    "displayName": "Bakery",
                },
                "metadata": {
                    "hasGoogleUpdated": False,
                    "canOperateLodgingData": False,
                },
            },
        ]

    def _get_mock_categories(self, query: str = "") -> List[dict]:
        """Return mock business categories for testing."""
        categories = [
            {"name": "categories/gcid:restaurant", "displayName": "Restaurant"},
            {"name": "categories/gcid:coffee_shop", "displayName": "Coffee shop"},
            {"name": "categories/gcid:bakery", "displayName": "Bakery"},
            {"name": "categories/gcid:bar", "displayName": "Bar"},
            {"name": "categories/gcid:cafe", "displayName": "Cafe"},
            {
                "name": "categories/gcid:pizza_restaurant",
                "displayName": "Pizza restaurant",
            },
            {
                "name": "categories/gcid:fast_food_restaurant",
                "displayName": "Fast food restaurant",
            },
            {"name": "categories/gcid:hair_salon", "displayName": "Hair salon"},
            {"name": "categories/gcid:spa", "displayName": "Spa"},
            {"name": "categories/gcid:gym", "displayName": "Gym"},
            {"name": "categories/gcid:dentist", "displayName": "Dentist"},
            {"name": "categories/gcid:doctor", "displayName": "Doctor"},
            {"name": "categories/gcid:lawyer", "displayName": "Lawyer"},
            {"name": "categories/gcid:accountant", "displayName": "Accountant"},
            {
                "name": "categories/gcid:real_estate_agency",
                "displayName": "Real estate agency",
            },
            {
                "name": "categories/gcid:software_company",
                "displayName": "Software company",
            },
            {
                "name": "categories/gcid:marketing_agency",
                "displayName": "Marketing agency",
            },
            {
                "name": "categories/gcid:consulting_firm",
                "displayName": "Consulting firm",
            },
        ]
        if query:
            query_lower = query.lower()
            return [c for c in categories if query_lower in c["displayName"].lower()]
        return categories

    def _get_mock_user_info(self) -> dict:
        """Return mock Google user info for testing."""
        return {
            "sub": "mock_google_user_id_12345",
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "email": "testuser@gmail.com",
            "email_verified": True,
            "picture": "https://example.com/photo.jpg",
        }

    # ============= OAUTH METHODS =============

    def get_authorization_url(self, state: str) -> str:
        """Generate OAuth authorization URL."""
        if self.is_mock_mode:
            # Return a mock URL that frontend can detect
            frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
            return f"{frontend_url}/automation?" f"mock_gbp_auth=true&state={state}"

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }
        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        if self.is_mock_mode or code == "mock_code":
            return self._mock_exchange_code_for_token(code)
        return self._real_exchange_code_for_token(code)

    def _mock_exchange_code_for_token(self, code: str) -> dict:
        """Mock token exchange for testing."""
        return {
            "access_token": self.MOCK_ACCESS_TOKEN,
            "refresh_token": self.MOCK_REFRESH_TOKEN,
            "expires_in": 3600,
            "expires_at": timezone.now() + timedelta(hours=1),
            "token_type": "Bearer",
            "scope": " ".join(self.SCOPES),
        }

    def _real_exchange_code_for_token(self, code: str) -> dict:
        """Real token exchange with Google OAuth."""
        if not self.is_configured:
            raise ValueError("Google Business credentials not configured")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Google OAuth token exchange failed: {e}")
            raise ValueError(f"Failed to exchange code for token: {str(e)}")

    def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh expired access token."""
        if self.is_mock_mode or refresh_token == self.MOCK_REFRESH_TOKEN:
            return self._mock_exchange_code_for_token("refresh")

        if not self.is_configured:
            raise ValueError("Google Business credentials not configured")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = timezone.now() + timedelta(seconds=expires_in)

            return token_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Google OAuth token refresh failed: {e}")
            raise ValueError(f"Failed to refresh token: {str(e)}")

    def get_user_info(self, access_token: str) -> dict:
        """Get Google user profile info."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            return self._get_mock_user_info()

        try:
            response = requests.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get Google user info: {e}")
            raise ValueError(f"Failed to get user info: {str(e)}")

    # ============= ACCOUNT METHODS =============

    def list_accounts(self, access_token: str) -> List[dict]:
        """List GBP accounts the user has access to."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            return self._get_mock_accounts()
        return self._real_list_accounts(access_token)

    def _real_list_accounts(self, access_token: str) -> List[dict]:
        """Real API call to list accounts."""
        try:
            response = requests.get(
                f"{self.ACCOUNT_MANAGEMENT_URL}/accounts",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("accounts", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list GBP accounts: {e}")
            raise ValueError(f"Failed to list accounts: {str(e)}")

    # ============= LOCATION METHODS =============

    def list_locations(self, access_token: str, account_id: str) -> List[dict]:
        """List locations for a GBP account."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            return self._get_mock_locations(account_id)
        return self._real_list_locations(access_token, account_id)

    def _real_list_locations(self, access_token: str, account_id: str) -> List[dict]:
        """Real API call to list locations."""
        # Ensure account_id is in the correct format
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        try:
            response = requests.get(
                f"{self.BUSINESS_INFO_URL}/{account_id}/locations",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "readMask": "name,title,storefrontAddress,primaryPhone,websiteUri,primaryCategory"
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("locations", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list GBP locations: {e}")
            raise ValueError(f"Failed to list locations: {str(e)}")

    def get_location(self, access_token: str, location_id: str) -> dict:
        """Get a specific location's details."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            # Return first mock location
            locations = self._get_mock_locations("123456789")
            for loc in locations:
                if loc["name"] == location_id:
                    return loc
            return locations[0] if locations else {}
        return self._real_get_location(access_token, location_id)

    def _real_get_location(self, access_token: str, location_id: str) -> dict:
        """Real API call to get location details."""
        if not location_id.startswith("locations/"):
            location_id = f"locations/{location_id}"

        try:
            response = requests.get(
                f"{self.BUSINESS_INFO_URL}/{location_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "readMask": "name,title,storefrontAddress,primaryPhone,websiteUri,primaryCategory,regularHours"
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get GBP location: {e}")
            raise ValueError(f"Failed to get location: {str(e)}")

    def create_location(
        self, access_token: str, account_id: str, location_data: dict
    ) -> dict:
        """Create a new business location."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            return self._mock_create_location(account_id, location_data)
        return self._real_create_location(access_token, account_id, location_data)

    def _mock_create_location(self, account_id: str, location_data: dict) -> dict:
        """Mock location creation for testing."""
        import uuid

        location_id = f"locations/mock_{uuid.uuid4().hex[:8]}"
        return {
            "name": location_id,
            "title": location_data.get("business_name", "New Business"),
            "storefrontAddress": {
                "addressLines": [
                    location_data.get("address_line1", ""),
                    location_data.get("address_line2", ""),
                ],
                "locality": location_data.get("city", ""),
                "administrativeArea": location_data.get("state", ""),
                "postalCode": location_data.get("postal_code", ""),
                "regionCode": location_data.get("country", "US"),
            },
            "primaryPhone": location_data.get("phone_number", ""),
            "websiteUri": location_data.get("website_url", ""),
            "primaryCategory": {
                "name": location_data.get(
                    "primary_category_id", "categories/gcid:business"
                ),
                "displayName": location_data.get("primary_category", "Business"),
            },
        }

    def _real_create_location(
        self, access_token: str, account_id: str, location_data: dict
    ) -> dict:
        """Real API call to create a location."""
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        # Build the location payload per GBP API spec
        payload = {
            "title": location_data.get("business_name"),
            "storefrontAddress": {
                "addressLines": [
                    location_data.get("address_line1", ""),
                ],
                "locality": location_data.get("city", ""),
                "administrativeArea": location_data.get("state", ""),
                "postalCode": location_data.get("postal_code", ""),
                "regionCode": location_data.get("country", "US"),
            },
        }

        if location_data.get("address_line2"):
            payload["storefrontAddress"]["addressLines"].append(
                location_data["address_line2"]
            )

        if location_data.get("phone_number"):
            payload["primaryPhone"] = location_data["phone_number"]

        if location_data.get("website_url"):
            payload["websiteUri"] = location_data["website_url"]

        if location_data.get("primary_category_id"):
            payload["primaryCategory"] = {"name": location_data["primary_category_id"]}

        try:
            response = requests.post(
                f"{self.BUSINESS_INFO_URL}/{account_id}/locations",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create GBP location: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise ValueError(f"Failed to create location: {str(e)}")

    def update_location(
        self, access_token: str, location_id: str, update_data: dict
    ) -> dict:
        """Update an existing location."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            return self._mock_create_location("mock_account", update_data)
        return self._real_update_location(access_token, location_id, update_data)

    def _real_update_location(
        self, access_token: str, location_id: str, update_data: dict
    ) -> dict:
        """Real API call to update a location."""
        if not location_id.startswith("locations/"):
            location_id = f"locations/{location_id}"

        # Build update mask based on what's being updated
        update_mask_fields = []
        payload = {}

        if "business_name" in update_data:
            payload["title"] = update_data["business_name"]
            update_mask_fields.append("title")

        if "phone_number" in update_data:
            payload["primaryPhone"] = update_data["phone_number"]
            update_mask_fields.append("primaryPhone")

        if "website_url" in update_data:
            payload["websiteUri"] = update_data["website_url"]
            update_mask_fields.append("websiteUri")

        # Handle address updates
        address_fields = ["address_line1", "city", "state", "postal_code", "country"]
        if any(f in update_data for f in address_fields):
            payload["storefrontAddress"] = {
                "addressLines": [update_data.get("address_line1", "")],
                "locality": update_data.get("city", ""),
                "administrativeArea": update_data.get("state", ""),
                "postalCode": update_data.get("postal_code", ""),
                "regionCode": update_data.get("country", "US"),
            }
            if update_data.get("address_line2"):
                payload["storefrontAddress"]["addressLines"].append(
                    update_data["address_line2"]
                )
            update_mask_fields.append("storefrontAddress")

        try:
            response = requests.patch(
                f"{self.BUSINESS_INFO_URL}/{location_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                params={"updateMask": ",".join(update_mask_fields)},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update GBP location: {e}")
            raise ValueError(f"Failed to update location: {str(e)}")

    def delete_location(self, access_token: str, location_id: str) -> bool:
        """Delete a location."""
        if self.is_mock_mode or access_token == self.MOCK_ACCESS_TOKEN:
            logger.info(f"Mock: Deleted location {location_id}")
            return True
        return self._real_delete_location(access_token, location_id)

    def _real_delete_location(self, access_token: str, location_id: str) -> bool:
        """Real API call to delete a location."""
        if not location_id.startswith("locations/"):
            location_id = f"locations/{location_id}"

        try:
            response = requests.delete(
                f"{self.BUSINESS_INFO_URL}/{location_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete GBP location: {e}")
            raise ValueError(f"Failed to delete location: {str(e)}")

    # ============= CATEGORY METHODS =============

    def list_categories(
        self,
        region_code: str = "US",
        language_code: str = "en",
        query: str = "",
    ) -> List[dict]:
        """List available business categories."""
        if self.is_mock_mode:
            return self._get_mock_categories(query)
        return self._real_list_categories(region_code, language_code, query)

    def _real_list_categories(
        self, region_code: str, language_code: str, query: str = ""
    ) -> List[dict]:
        """Real API call to list categories."""
        params = {
            "regionCode": region_code,
            "languageCode": language_code,
            "view": "FULL",
        }
        if query:
            params["filter"] = f'displayName:"{query}"'

        try:
            response = requests.get(
                f"{self.BUSINESS_INFO_URL}/categories",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("categories", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list GBP categories: {e}")
            # Return mock categories as fallback
            return self._get_mock_categories(query)


# Singleton instance
google_business_service = GoogleBusinessService()
