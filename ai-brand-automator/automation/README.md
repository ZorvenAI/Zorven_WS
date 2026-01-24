# Automation Microservice

> **Version**: 2.0.0  
> **Status**: ✅ Production Ready  
> **Tests**: 149 passing  
> **Last Updated**: January 23, 2026

The automation microservice handles all social media integrations, content scheduling, Google Business Profile management, and provides an MCP server for AI agent integration.

## Features

### Social Media Platforms (All Complete ✅)

| Platform | OAuth | Posting | Scheduling | Media | Analytics | Webhooks |
|----------|-------|---------|------------|-------|-----------|----------|
| LinkedIn | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Twitter/X | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Facebook | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Instagram | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Google Business Profile | ✅ | ✅ | ✅ | ✅ | ✅ | - |

### Core Capabilities

- **OAuth Integration** - Secure token management with encryption
- **Content Calendar** - Schedule posts across all platforms
- **Media Uploads** - Images, videos, documents with platform-specific handling
- **Background Tasks** - Celery-based automatic publishing (every 60 seconds)
- **MCP Server** - 23 tools for AI agent integration
- **Analytics** - Engagement metrics and insights

## Architecture

```
automation/
├── __init__.py
├── admin.py              # Django admin configuration
├── apps.py               # App configuration
├── constants.py          # Platform constants and limits
├── encryption.py         # Token encryption utilities
├── models.py             # Database models
├── serializers.py        # DRF serializers
├── services.py           # Platform API services
├── publish_helpers.py    # Publishing utilities
├── tasks.py              # Celery tasks
├── views.py              # API views (5700+ lines)
├── urls.py               # URL routing
├── mcp_server.py         # MCP Server with 23 tools
├── docs/                 # Platform integration documentation
│   ├── LINKEDIN_INTEGRATION_REPORT.md
│   ├── TWITTER_INTEGRATION_REPORT.md
│   ├── FACEBOOK_INTEGRATION_REPORT.md
│   ├── INSTAGRAM_INTEGRATION_REPORT.md
│   └── GOOGLE_BUSINESS_PROFILE_IMPLEMENTATION_PLAN.md
├── tests/                # Test suite (149 tests)
│   ├── test_models.py         # 51 unit tests
│   ├── test_properties.py     # 18 property-based tests
│   ├── test_integration.py    # 26 integration tests
│   ├── test_services.py       # 36 service tests
│   └── test_gbp.py            # 77 GBP tests
└── management/           # Django management commands
```

## Models

### SocialProfile
Stores connected social media accounts with encrypted tokens.

```python
class SocialProfile(models.Model):
    company = ForeignKey(Company)
    platform = CharField(choices=PLATFORM_CHOICES)  # linkedin, twitter, facebook, instagram, gbp
    platform_user_id = CharField()
    access_token_encrypted = TextField()
    refresh_token_encrypted = TextField(null=True)
    token_expires_at = DateTimeField(null=True)
    profile_name = CharField()
    profile_url = URLField(null=True)
    is_active = BooleanField(default=True)
```

### ContentCalendar
Manages scheduled and published content.

```python
class ContentCalendar(models.Model):
    company = ForeignKey(Company)
    profile = ForeignKey(SocialProfile)
    content = TextField()
    scheduled_time = DateTimeField()
    status = CharField(choices=STATUS_CHOICES)  # draft, scheduled, published, failed, cancelled
    platform_post_id = CharField(null=True)
    published_at = DateTimeField(null=True)
    error_message = TextField(null=True)
```

### GBPListing
Google Business Profile listing management.

```python
class GBPListing(models.Model):
    company = ForeignKey(Company)
    profile = ForeignKey(SocialProfile)
    location_id = CharField()
    business_name = CharField()
    address = TextField()
    phone_number = CharField(null=True)
    website = URLField(null=True)
    categories = JSONField(default=list)
    is_verified = BooleanField(default=False)
```

### GBPPost, GBPReview, GBPInsight
Additional GBP-related models for posts, reviews, and analytics.

## API Endpoints

### Social Profiles
```
GET  /api/v1/automation/social-profiles/         # List connected profiles
GET  /api/v1/automation/social-profiles/status/  # Platform connection status
```

### LinkedIn
```
GET  /api/v1/automation/linkedin/connect/        # Initiate OAuth
GET  /api/v1/automation/linkedin/callback/       # OAuth callback
POST /api/v1/automation/linkedin/disconnect/     # Disconnect
POST /api/v1/automation/linkedin/post/           # Post immediately
POST /api/v1/automation/linkedin/media/upload/   # Upload media
GET  /api/v1/automation/linkedin/analytics/      # Get analytics
POST /api/v1/automation/linkedin/webhook/        # Webhook handler
```

### Twitter/X
```
GET  /api/v1/automation/twitter/connect/         # Initiate OAuth (PKCE)
GET  /api/v1/automation/twitter/callback/        # OAuth callback
POST /api/v1/automation/twitter/disconnect/      # Disconnect
POST /api/v1/automation/twitter/post/            # Post immediately
POST /api/v1/automation/twitter/thread/          # Post thread
POST /api/v1/automation/twitter/media/upload/    # Upload media
GET  /api/v1/automation/twitter/analytics/       # Get analytics
```

### Facebook
```
GET  /api/v1/automation/facebook/connect/        # Initiate OAuth
GET  /api/v1/automation/facebook/callback/       # OAuth callback
POST /api/v1/automation/facebook/disconnect/     # Disconnect
POST /api/v1/automation/facebook/post/           # Post to page
POST /api/v1/automation/facebook/story/          # Post story
POST /api/v1/automation/facebook/carousel/       # Post carousel
POST /api/v1/automation/facebook/video/upload/   # Resumable video upload
GET  /api/v1/automation/facebook/analytics/      # Get analytics
POST /api/v1/automation/facebook/webhook/        # Webhook handler
```

### Instagram
```
GET  /api/v1/automation/instagram/connect/       # Initiate OAuth
GET  /api/v1/automation/instagram/callback/      # OAuth callback
POST /api/v1/automation/instagram/disconnect/    # Disconnect
POST /api/v1/automation/instagram/post/          # Post media
POST /api/v1/automation/instagram/story/         # Post story
POST /api/v1/automation/instagram/reel/          # Post reel
POST /api/v1/automation/instagram/carousel/      # Post carousel
GET  /api/v1/automation/instagram/analytics/     # Get analytics
POST /api/v1/automation/instagram/webhook/       # Webhook handler
```

### Google Business Profile
```
GET    /api/v1/automation/gbp/listings/              # List GBP listings
POST   /api/v1/automation/gbp/listings/              # Create listing
GET    /api/v1/automation/gbp/listings/{id}/         # Get listing details
PUT    /api/v1/automation/gbp/listings/{id}/         # Update listing
DELETE /api/v1/automation/gbp/listings/{id}/         # Delete listing
POST   /api/v1/automation/gbp/listings/{id}/posts/   # Create post
GET    /api/v1/automation/gbp/listings/{id}/posts/   # List posts
GET    /api/v1/automation/gbp/listings/{id}/reviews/ # Get reviews
POST   /api/v1/automation/gbp/reviews/{id}/reply/    # Reply to review
GET    /api/v1/automation/gbp/listings/{id}/insights/# Get insights
```

### Content Calendar
```
GET  /api/v1/automation/content-calendar/            # List scheduled posts
POST /api/v1/automation/content-calendar/            # Create scheduled post
PUT  /api/v1/automation/content-calendar/{id}/       # Edit scheduled post
GET  /api/v1/automation/content-calendar/upcoming/   # Get upcoming posts
POST /api/v1/automation/content-calendar/{id}/publish/ # Publish now
POST /api/v1/automation/content-calendar/{id}/cancel/  # Cancel scheduled
```

## MCP Server

The MCP (Model Context Protocol) server enables AI agents like Claude or GPT to interact with the automation service.

### Starting the Server

```bash
# Stdio transport (for Claude Desktop, VS Code)
python run_mcp_server.py --transport stdio

# SSE transport (for web clients)
python run_mcp_server.py --transport sse --host 0.0.0.0 --port 8001
```

### Available Tools (23 Total)

#### Social Profile Tools
| Tool | Description |
|------|-------------|
| `list_social_profiles` | List all connected social accounts |
| `get_social_profile_status` | Check connection status |
| `disconnect_social_profile` | Remove social connection |
| `get_platform_oauth_url` | Get OAuth connect URL |

#### Content Scheduling Tools
| Tool | Description |
|------|-------------|
| `list_scheduled_content` | Get scheduled posts |
| `create_scheduled_content` | Schedule new post |
| `update_scheduled_content` | Modify scheduled post |
| `cancel_scheduled_content` | Cancel scheduled post |
| `publish_content_now` | Publish immediately |

#### Direct Posting Tools
| Tool | Description |
|------|-------------|
| `post_to_linkedin` | Direct LinkedIn post |
| `post_to_twitter` | Direct Twitter post |
| `post_to_facebook` | Direct Facebook post |
| `post_to_instagram` | Direct Instagram post |

#### Google Business Profile Tools
| Tool | Description |
|------|-------------|
| `create_gbp_listing` | Create GBP listing |
| `update_gbp_listing` | Update GBP listing |
| `get_gbp_listing` | Get listing details |
| `delete_gbp_listing` | Delete GBP listing |
| `list_gbp_listings` | List all GBP listings |
| `create_gbp_post` | Create GBP post |
| `list_gbp_posts` | List GBP posts |
| `get_gbp_reviews` | Get GBP reviews |
| `reply_to_gbp_review` | Reply to review |
| `get_gbp_insights` | Get GBP analytics |

#### Automation Tools
| Tool | Description |
|------|-------------|
| `list_automation_tasks` | Get automation jobs |

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "automation": {
      "command": "python",
      "args": ["run_mcp_server.py"],
      "cwd": "/path/to/ai-brand-automator",
      "env": {
        "DJANGO_SETTINGS_MODULE": "brand_automator.settings"
      }
    }
  }
}
```

## Celery Tasks

### Background Publishing

The `publish_scheduled_posts` task runs every 60 seconds to publish due content:

```python
@shared_task
def publish_scheduled_posts():
    """Publish all scheduled posts that are due."""
    now = timezone.now()
    due_posts = ContentCalendar.objects.filter(
        status='scheduled',
        scheduled_time__lte=now
    )
    for post in due_posts:
        publish_single_post.delay(post.id)

@shared_task
def publish_single_post(post_id):
    """Publish a single scheduled post."""
    post = ContentCalendar.objects.get(id=post_id)
    # Platform-specific publishing logic
```

### Starting Celery

```bash
# Terminal 1 - Start Redis
brew services start redis  # macOS

# Terminal 2 - Celery Worker
cd ai-brand-automator
source ../.venv/bin/activate
celery -A brand_automator worker -l info

# Terminal 3 - Celery Beat
cd ai-brand-automator
source ../.venv/bin/activate
celery -A brand_automator beat -l info
```

## Media Specifications

| Platform | Image | Video | Document |
|----------|-------|-------|----------|
| LinkedIn | 8MB (JPEG, PNG, GIF) | 500MB (MP4) | 100MB (PDF, DOC, PPT) |
| Twitter/X | 5MB (JPEG, PNG, GIF) | 512MB (MP4) | N/A |
| Facebook | 4MB (JPEG, PNG) | 4GB (MP4) | N/A |
| Instagram | 8MB (JPEG, PNG) | 100MB (MP4) | N/A |
| GBP | 5MB (JPEG, PNG) | N/A | N/A |

## Environment Variables

```bash
# LinkedIn
LINKEDIN_CLIENT_ID=your-client-id
LINKEDIN_CLIENT_SECRET=your-client-secret
LINKEDIN_REDIRECT_URI=http://localhost:8000/api/v1/automation/linkedin/callback/

# Twitter/X
TWITTER_CLIENT_ID=your-client-id
TWITTER_CLIENT_SECRET=your-client-secret

# Facebook
FACEBOOK_APP_ID=your-app-id
FACEBOOK_APP_SECRET=your-app-secret

# Instagram
INSTAGRAM_CLIENT_ID=your-client-id
INSTAGRAM_CLIENT_SECRET=your-client-secret

# Google Business Profile
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Token Encryption
ENCRYPTION_KEY=your-fernet-key
```

## Testing

```bash
# Run all automation tests
pytest automation/tests/ -v

# Run specific test files
pytest automation/tests/test_models.py -v       # 51 unit tests
pytest automation/tests/test_properties.py -v   # 18 property-based tests
pytest automation/tests/test_integration.py -v  # 26 integration tests
pytest automation/tests/test_services.py -v     # 36 service tests
pytest automation/tests/test_gbp.py -v          # 77 GBP tests

# Run with coverage
pytest automation/tests/ --cov=automation --cov-report=html
```

## Documentation

- [LinkedIn Integration](docs/LINKEDIN_INTEGRATION_REPORT.md) - OAuth, posting, media, analytics
- [Twitter Integration](docs/TWITTER_INTEGRATION_REPORT.md) - OAuth PKCE, threads, analytics
- [Facebook Integration](docs/FACEBOOK_INTEGRATION_REPORT.md) - Pages, stories, carousels
- [Instagram Integration](docs/INSTAGRAM_INTEGRATION_REPORT.md) - Posts, stories, reels
- [GBP Implementation](docs/GOOGLE_BUSINESS_PROFILE_IMPLEMENTATION_PLAN.md) - Listings, posts, reviews

## Security

- **Token Encryption**: All OAuth tokens encrypted at rest using Fernet
- **Secure Storage**: Tokens stored in encrypted fields, never in plain text
- **Token Refresh**: Automatic refresh before expiration
- **Scope Management**: Minimal permissions requested per platform

## Troubleshooting

### OAuth Fails
- Check client ID/secret in `.env`
- Verify redirect URI matches registered app
- Check platform developer console for errors

### Posts Not Publishing
- Verify Celery worker is running
- Check Redis connection
- Look at Celery logs for errors
- Verify token hasn't expired

### Media Upload Fails
- Check file size against platform limits
- Verify file format is supported
- Check platform-specific requirements (aspect ratios, etc.)

### MCP Server Issues
- Ensure Django settings module is set
- Check database connection
- Verify transport (stdio vs SSE) matches client

## Changelog

### 2.0.0 (January 23, 2026)
- ✅ Google Business Profile integration (10 MCP tools)
- ✅ Instagram OAuth and posting
- ✅ 77 GBP tests added
- ✅ Total 149 tests passing

### 1.5.0
- ✅ Twitter/X integration with PKCE
- ✅ Facebook integration with resumable uploads

### 1.0.0
- ✅ LinkedIn integration
- ✅ Content Calendar
- ✅ MCP Server with 13 tools
- ✅ Celery background publishing
