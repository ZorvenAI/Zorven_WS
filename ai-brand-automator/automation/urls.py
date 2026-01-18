"""
URL configuration for the automation app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SocialProfileViewSet,
    AutomationTaskViewSet,
    ContentCalendarViewSet,
    # LinkedIn views
    LinkedInConnectView,
    LinkedInCallbackView,
    LinkedInDisconnectView,
    LinkedInTestConnectView,
    LinkedInOrganizationsView,
    LinkedInSelectOrganizationView,
    LinkedInPostView,
    LinkedInCarouselPostView,
    LinkedInMediaUploadView,
    LinkedInVideoStatusView,
    LinkedInDocumentStatusView,
    LinkedInAnalyticsView,
    LinkedInDeletePostView,
    LinkedInWebhookView,
    LinkedInWebhookEventsView,
    # Twitter views
    TwitterConnectView,
    TwitterCallbackView,
    TwitterDisconnectView,
    TwitterTestConnectView,
    TwitterPostView,
    TwitterCarouselPostView,
    TwitterValidateTweetView,
    TwitterMediaUploadView,
    TwitterMediaStatusView,
    TwitterDeleteTweetView,
    TwitterAnalyticsView,
    TwitterWebhookView,
    TwitterWebhookEventsView,
    # Facebook views
    FacebookConnectView,
    FacebookCallbackView,
    FacebookDisconnectView,
    FacebookTestConnectView,
    FacebookPagesView,
    FacebookSelectPageView,
    FacebookPostView,
    FacebookMediaUploadView,
    FacebookResumableUploadView,
    FacebookDeletePostView,
    FacebookAnalyticsView,
    FacebookLinkPreviewView,
    FacebookCarouselPostView,
    FacebookCarouselUploadView,
    FacebookStoryView,
    FacebookStoryDeleteView,
    FacebookWebhookView,
    FacebookWebhookEventsView,
    FacebookWebhookSubscribeView,
    # Instagram views
    InstagramConnectView,
    InstagramCallbackView,
    InstagramDisconnectView,
    InstagramTestConnectView,
    InstagramAccountsView,
    InstagramSelectAccountView,
    InstagramPostView,
    InstagramCarouselPostView,
    InstagramStoryView,
    InstagramMediaView,
    InstagramAnalyticsView,
    InstagramCommentsView,
    InstagramWebhookView,
    InstagramWebhookEventsView,
)

router = DefaultRouter()
router.register(r"social-profiles", SocialProfileViewSet, basename="social-profile")
router.register(r"tasks", AutomationTaskViewSet, basename="automation-task")
router.register(
    r"content-calendar", ContentCalendarViewSet, basename="content-calendar"
)

urlpatterns = [
    # LinkedIn OAuth
    path("linkedin/connect/", LinkedInConnectView.as_view(), name="linkedin-connect"),
    path(
        "linkedin/callback/", LinkedInCallbackView.as_view(), name="linkedin-callback"
    ),
    path(
        "linkedin/disconnect/",
        LinkedInDisconnectView.as_view(),
        name="linkedin-disconnect",
    ),
    path(
        "linkedin/test-connect/",
        LinkedInTestConnectView.as_view(),
        name="linkedin-test-connect",
    ),
    # LinkedIn Organizations (Company Pages)
    path(
        "linkedin/organizations/",
        LinkedInOrganizationsView.as_view(),
        name="linkedin-organizations",
    ),
    path(
        "linkedin/organizations/select/",
        LinkedInSelectOrganizationView.as_view(),
        name="linkedin-select-organization",
    ),
    path("linkedin/post/", LinkedInPostView.as_view(), name="linkedin-post"),
    path(
        "linkedin/carousel/post/",
        LinkedInCarouselPostView.as_view(),
        name="linkedin-carousel-post",
    ),
    path(
        "linkedin/media/upload/",
        LinkedInMediaUploadView.as_view(),
        name="linkedin-media-upload",
    ),
    path(
        "linkedin/video/status/<str:asset_urn>/",
        LinkedInVideoStatusView.as_view(),
        name="linkedin-video-status",
    ),
    path(
        "linkedin/document/status/<str:document_urn>/",
        LinkedInDocumentStatusView.as_view(),
        name="linkedin-document-status",
    ),
    # LinkedIn Analytics
    path(
        "linkedin/analytics/",
        LinkedInAnalyticsView.as_view(),
        name="linkedin-analytics",
    ),
    path(
        "linkedin/analytics/<path:post_urn>/",
        LinkedInAnalyticsView.as_view(),
        name="linkedin-analytics-post",
    ),
    # LinkedIn Delete Post
    path(
        "linkedin/post/<path:post_urn>/",
        LinkedInDeletePostView.as_view(),
        name="linkedin-delete-post",
    ),
    # LinkedIn Webhooks
    path(
        "linkedin/webhook/",
        LinkedInWebhookView.as_view(),
        name="linkedin-webhook",
    ),
    path(
        "linkedin/webhooks/events/",
        LinkedInWebhookEventsView.as_view(),
        name="linkedin-webhook-events",
    ),  # Twitter/X OAuth
    path("twitter/connect/", TwitterConnectView.as_view(), name="twitter-connect"),
    path("twitter/callback/", TwitterCallbackView.as_view(), name="twitter-callback"),
    path(
        "twitter/disconnect/",
        TwitterDisconnectView.as_view(),
        name="twitter-disconnect",
    ),
    path(
        "twitter/test-connect/",
        TwitterTestConnectView.as_view(),
        name="twitter-test-connect",
    ),
    path("twitter/post/", TwitterPostView.as_view(), name="twitter-post"),
    path(
        "twitter/carousel/post/",
        TwitterCarouselPostView.as_view(),
        name="twitter-carousel-post",
    ),
    path(
        "twitter/validate/",
        TwitterValidateTweetView.as_view(),
        name="twitter-validate",
    ),
    path(
        "twitter/media/upload/",
        TwitterMediaUploadView.as_view(),
        name="twitter-media-upload",
    ),
    path(
        "twitter/media/status/<str:media_id>/",
        TwitterMediaStatusView.as_view(),
        name="twitter-media-status",
    ),
    path(
        "twitter/tweet/<str:tweet_id>/",
        TwitterDeleteTweetView.as_view(),
        name="twitter-delete-tweet",
    ),
    # Twitter Analytics
    path(
        "twitter/analytics/",
        TwitterAnalyticsView.as_view(),
        name="twitter-analytics",
    ),
    path(
        "twitter/analytics/<str:tweet_id>/",
        TwitterAnalyticsView.as_view(),
        name="twitter-analytics-tweet",
    ),
    # Twitter Webhooks
    path(
        "twitter/webhook/",
        TwitterWebhookView.as_view(),
        name="twitter-webhook",
    ),
    path(
        "twitter/webhooks/events/",
        TwitterWebhookEventsView.as_view(),
        name="twitter-webhook-events",
    ),
    # Facebook OAuth
    path("facebook/connect/", FacebookConnectView.as_view(), name="facebook-connect"),
    path(
        "facebook/callback/", FacebookCallbackView.as_view(), name="facebook-callback"
    ),
    path(
        "facebook/disconnect/",
        FacebookDisconnectView.as_view(),
        name="facebook-disconnect",
    ),
    path(
        "facebook/test-connect/",
        FacebookTestConnectView.as_view(),
        name="facebook-test-connect",
    ),
    # Facebook Pages
    path("facebook/pages/", FacebookPagesView.as_view(), name="facebook-pages"),
    path(
        "facebook/pages/select/",
        FacebookSelectPageView.as_view(),
        name="facebook-select-page",
    ),
    # Facebook Posting
    path("facebook/post/", FacebookPostView.as_view(), name="facebook-post"),
    path(
        "facebook/media/upload/",
        FacebookMediaUploadView.as_view(),
        name="facebook-media-upload",
    ),
    # Facebook Resumable Upload (for large videos > 1GB)
    path(
        "facebook/upload/resumable/",
        FacebookResumableUploadView.as_view(),
        name="facebook-resumable-upload",
    ),
    path(
        "facebook/upload/resumable/<str:action>/",
        FacebookResumableUploadView.as_view(),
        name="facebook-resumable-upload-action",
    ),
    path(
        "facebook/post/<str:post_id>/",
        FacebookDeletePostView.as_view(),
        name="facebook-delete-post",
    ),
    # Facebook Analytics
    path(
        "facebook/analytics/",
        FacebookAnalyticsView.as_view(),
        name="facebook-analytics",
    ),
    path(
        "facebook/analytics/<str:post_id>/",
        FacebookAnalyticsView.as_view(),
        name="facebook-analytics-post",
    ),
    # Facebook Link Preview
    path(
        "facebook/link-preview/",
        FacebookLinkPreviewView.as_view(),
        name="facebook-link-preview",
    ),
    # Facebook Carousel Posts
    path(
        "facebook/carousel/post/",
        FacebookCarouselPostView.as_view(),
        name="facebook-carousel-post",
    ),
    path(
        "facebook/carousel/upload/",
        FacebookCarouselUploadView.as_view(),
        name="facebook-carousel-upload",
    ),
    # Facebook Stories
    path(
        "facebook/stories/",
        FacebookStoryView.as_view(),
        name="facebook-stories",
    ),
    path(
        "facebook/stories/<str:story_id>/",
        FacebookStoryDeleteView.as_view(),
        name="facebook-story-delete",
    ),
    # Facebook Webhooks
    path(
        "facebook/webhook/",
        FacebookWebhookView.as_view(),
        name="facebook-webhook",
    ),
    path(
        "facebook/webhooks/events/",
        FacebookWebhookEventsView.as_view(),
        name="facebook-webhook-events",
    ),
    path(
        "facebook/webhooks/subscribe/",
        FacebookWebhookSubscribeView.as_view(),
        name="facebook-webhook-subscribe",
    ),
    # Instagram OAuth
    path(
        "instagram/connect/",
        InstagramConnectView.as_view(),
        name="instagram-connect",
    ),
    path(
        "instagram/callback/",
        InstagramCallbackView.as_view(),
        name="instagram-callback",
    ),
    path(
        "instagram/disconnect/",
        InstagramDisconnectView.as_view(),
        name="instagram-disconnect",
    ),
    path(
        "instagram/test-connect/",
        InstagramTestConnectView.as_view(),
        name="instagram-test-connect",
    ),
    # Instagram Accounts
    path(
        "instagram/accounts/",
        InstagramAccountsView.as_view(),
        name="instagram-accounts",
    ),
    path(
        "instagram/accounts/select/",
        InstagramSelectAccountView.as_view(),
        name="instagram-select-account",
    ),
    # Instagram Posting
    path(
        "instagram/post/",
        InstagramPostView.as_view(),
        name="instagram-post",
    ),
    path(
        "instagram/carousel/post/",
        InstagramCarouselPostView.as_view(),
        name="instagram-carousel-post",
    ),
    # Instagram Stories
    path(
        "instagram/stories/",
        InstagramStoryView.as_view(),
        name="instagram-stories",
    ),
    # Instagram Media (Posts)
    path(
        "instagram/media/",
        InstagramMediaView.as_view(),
        name="instagram-media",
    ),
    # Instagram Analytics
    path(
        "instagram/analytics/",
        InstagramAnalyticsView.as_view(),
        name="instagram-analytics",
    ),
    path(
        "instagram/analytics/<str:media_id>/",
        InstagramAnalyticsView.as_view(),
        name="instagram-analytics-media",
    ),
    # Instagram Comments
    path(
        "instagram/media/<str:media_id>/comments/",
        InstagramCommentsView.as_view(),
        name="instagram-comments",
    ),
    # Instagram Webhooks
    path(
        "instagram/webhook/",
        InstagramWebhookView.as_view(),
        name="instagram-webhook",
    ),
    path(
        "instagram/webhooks/events/",
        InstagramWebhookEventsView.as_view(),
        name="instagram-webhook-events",
    ),
    # Router URLs
    path("", include(router.urls)),
]
