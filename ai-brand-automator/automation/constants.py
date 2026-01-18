"""
Constants for the automation app.
"""
from typing import List

# Test mode constants - used for development without real credentials
TEST_ACCESS_TOKEN = "test_access_token_not_real"
TEST_REFRESH_TOKEN = "test_refresh_token_not_real"

# Twitter test mode constants
TWITTER_TEST_ACCESS_TOKEN = "test_twitter_access_token_not_real"
TWITTER_TEST_REFRESH_TOKEN = "test_twitter_refresh_token_not_real"

# Facebook test mode constants
FACEBOOK_TEST_ACCESS_TOKEN = "test_facebook_access_token_not_real"
FACEBOOK_TEST_PAGE_TOKEN = "test_facebook_page_token_not_real"

# Instagram test mode constants
INSTAGRAM_TEST_ACCESS_TOKEN = "test_instagram_access_token_not_real"
INSTAGRAM_TEST_USER_TOKEN = "test_instagram_user_token_not_real"

# LinkedIn API limits
LINKEDIN_POST_MAX_LENGTH = 3000
LINKEDIN_TITLE_MAX_LENGTH = 200

# Twitter/X API limits
TWITTER_POST_MAX_LENGTH = 280  # Standard tweet limit
TWITTER_POST_MAX_LENGTH_PREMIUM = 25000  # X Premium subscribers
TWITTER_MEDIA_MAX_IMAGES = 4  # Max images per tweet
TWITTER_MEDIA_MAX_VIDEO_SIZE = 512 * 1024 * 1024  # 512MB for video
TWITTER_MEDIA_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB for images
TWITTER_MEDIA_MAX_GIF_SIZE = 15 * 1024 * 1024  # 15MB for GIFs

# Facebook API limits
FACEBOOK_POST_MAX_LENGTH = 63206  # Facebook page post limit
FACEBOOK_MEDIA_MAX_IMAGES = 10  # Max images per post
FACEBOOK_MEDIA_MAX_VIDEO_SIZE = 1024 * 1024 * 1024  # 1GB for video
FACEBOOK_MEDIA_MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4MB for images

# Twitter supported media types
TWITTER_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/gif", "image/webp"]
TWITTER_VIDEO_TYPES: List[str] = ["video/mp4", "video/quicktime"]

# Facebook supported media types
FACEBOOK_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/gif", "image/bmp"]
FACEBOOK_VIDEO_TYPES: List[str] = ["video/mp4", "video/mov", "video/avi"]

# Instagram API limits
INSTAGRAM_POST_MAX_LENGTH = 2200  # Instagram caption limit
INSTAGRAM_MEDIA_MAX_IMAGES = 10  # Max images per carousel post
INSTAGRAM_MEDIA_MAX_VIDEO_SIZE = 1024 * 1024 * 1024  # 1GB for video (Reels)
INSTAGRAM_MEDIA_MAX_IMAGE_SIZE = 8 * 1024 * 1024  # 8MB for images
INSTAGRAM_STORY_MAX_VIDEO_DURATION = 60  # 60 seconds for stories
INSTAGRAM_REEL_MAX_VIDEO_DURATION = 90  # 90 seconds for reels
INSTAGRAM_HASHTAG_MAX = 30  # Max hashtags per post

# Instagram supported media types
INSTAGRAM_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png"]
INSTAGRAM_VIDEO_TYPES: List[str] = ["video/mp4", "video/mov"]

# Editable post statuses - posts with these statuses can be edited
EDITABLE_STATUSES: List[str] = ["draft", "scheduled"]

# Supported media types (LinkedIn standards)
IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/gif"]
VIDEO_TYPES: List[str] = ["video/mp4"]  # LinkedIn standard: MP4 only
DOCUMENT_TYPES: List[str] = [
    "application/pdf",
    "application/msword",
    # docx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    # pptx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]

# Size limits (LinkedIn standards)
MAX_IMAGE_SIZE: int = 8 * 1024 * 1024  # 8MB
MAX_VIDEO_SIZE: int = 500 * 1024 * 1024  # 500MB (LinkedIn max for organic posts)
MAX_DOCUMENT_SIZE: int = 100 * 1024 * 1024  # 100MB (LinkedIn max for documents)
