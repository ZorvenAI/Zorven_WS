"""
Model Context Protocol (MCP) Server for the Automation Service.

This module provides an MCP server that exposes the automation service
capabilities (social media management, content scheduling, publishing)
as MCP tools that can be used by AI models (Claude, GPT, etc.).

Server Information:
    - Name: automation-mcp-server
    - Version: 1.0.0
    - Protocol: Model Context Protocol (MCP) v1.0
    - Transports: stdio (Claude Desktop), SSE (web clients)

Capabilities:
    - Social Profile Management: Connect, list, and manage OAuth-linked social accounts
    - Content Calendar: Create, schedule, update, and cancel posts
    - Direct Publishing: Post immediately to LinkedIn, Twitter/X, Facebook
    - Automation Tasks: Track background job status and history

Supported Platforms:
    - LinkedIn (Company Pages API)
    - Twitter/X (OAuth 2.0, API v2)
    - Facebook (Graph API, Pages)
    - Instagram (Graph API via Facebook Business)

Authentication:
    Users are identified by email address. Social platform connections
    use OAuth 2.0 with tokens stored in SocialProfile models.

The server can run:
    1. Standalone as an MCP server (stdio or SSE transport)
    2. Alongside the Django REST API microservice (dual-mode)

Usage:
    # Run as standalone MCP server (stdio for Claude Desktop)
    python -m automation.mcp_server

    # Run with SSE transport for web clients
    python run_mcp_server.py --transport sse --port 8001

    # Or import and run programmatically
    from automation.mcp_server import create_mcp_server
    server = create_mcp_server()
    server.run()

Example Tool Invocations:
    # List social profiles for a user
    {"tool": "list_social_profiles", "arguments": {"user_email": "user@example.com"}}

    # Schedule a LinkedIn post
    {"tool": "create_scheduled_content", "arguments": {
        "user_email": "user@example.com",
        "title": "Product Launch",
        "content": "Excited to announce our new feature!",
        "platforms": ["linkedin", "twitter"],
        "scheduled_date": "2024-01-15T10:00:00Z"
    }}

    # Post immediately to Twitter
    {"tool": "post_to_twitter", "arguments": {
        "user_email": "user@example.com",
        "text": "Hello from the AI Brand Automator! 🚀"
    }}
"""

import os
import sys
import json
import logging
from typing import Any
from datetime import datetime, timedelta

# Add the project root to path for Django imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Setup Django before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

import django  # noqa: E402

django.setup()

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import (  # noqa: E402
    Tool,
    TextContent,
    Resource,
    Prompt,
    PromptMessage,
    PromptArgument,
    GetPromptResult,
)

# Server metadata for agent discovery
SERVER_NAME = "automation-mcp-server"
SERVER_VERSION = "1.0.0"
SERVER_DESCRIPTION = """AI Brand Automator - Social Media Automation MCP Server.

This server enables AI agents to manage social media accounts, schedule content,
and publish posts across LinkedIn, Twitter/X, Facebook, and Instagram.

Key Capabilities:
• Manage OAuth-connected social media profiles
• Create and schedule content calendar posts
• Publish content immediately or on schedule
• Track automation task status and history
• Generate OAuth URLs for new platform connections
• Manage Google Business Profile listings and locations

Authentication: Users are identified by email. Call tools with 'user_email' parameter.
Platforms: linkedin, twitter, instagram, facebook
Google Business: Profile connection, account selection, location CRUD

Common Workflows:
1. Check connected accounts: list_social_profiles → get_social_profile_status
2. Schedule a post: create_scheduled_content → (optional) update_scheduled_content
3. Post immediately: post_to_linkedin / post_to_twitter / post_to_facebook
4. Connect new platform: get_platform_oauth_url → redirect user → callback
5. Google Business: gbp_get_status → gbp_connect → gbp_select_account → gbp_list_locations
"""

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

from .models import SocialProfile, ContentCalendar, AutomationTask  # noqa: E402
from .models import GoogleBusinessProfile, GoogleBusinessLocation  # noqa: E402
from .services import (  # noqa: E402
    linkedin_service,
    twitter_service,
    facebook_service,
    instagram_service,
    google_business_service,
)
from .publish_helpers import publish_content, update_content_status  # noqa: E402

logger = logging.getLogger(__name__)

User = get_user_model()


def create_mcp_server() -> Server:
    """
    Create and configure the MCP server with automation tools.

    This function creates an MCP server instance configured with:
    - 13 tools for social media automation
    - Resources for accessing user data and platform status
    - Prompts for common workflow patterns

    Returns:
        Configured MCP Server instance with full automation capabilities

    Example:
        >>> server = create_mcp_server()
        >>> # Run with stdio transport (for Claude Desktop)
        >>> async with stdio_server() as (read, write):
        ...     await server.run(read, write, server.create_initialization_options())
    """
    server = Server(
        SERVER_NAME,
        version=SERVER_VERSION,
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available automation tools."""
        return [
            # Social Profile Tools
            Tool(
                name="list_social_profiles",
                description="""List all connected social media profiles for a user.

Returns an array of profile objects with connection details. Use this to check
which platforms a user has connected before attempting to post.

Returns:
    {
        "profiles": [
            {
                "id": 123,
                "platform": "linkedin",
                "platform_display": "LinkedIn",
                "status": "connected" | "disconnected" | "expired",
                "profile_name": "John Doe",
                "profile_url": "https://linkedin.com/in/johndoe",
                "is_token_valid": true,
                "is_token_expiring_soon": false,
                "token_expires_at": "2024-06-15T10:00:00Z"
            }
        ],
        "count": 1
    }

Example: List all LinkedIn profiles
    {"user_email": "user@example.com", "platform": "linkedin"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user (must exist in the system)",
                        },
                        "platform": {
                            "type": "string",
                            "description": "Optional: filter results to a specific platform",
                            "enum": ["linkedin", "twitter", "instagram", "facebook"],
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="get_social_profile_status",
                description="""Get the connection status of ALL social media platforms for a user.

Returns a status object for each platform (linkedin, twitter, instagram, facebook),
showing whether each is connected and valid. This is a quick way to see the full
platform connection overview.

Returns:
    {
        "linkedin": {"connected": true, "profile_name": "John", "status": "connected", "is_token_valid": true},
        "twitter": {"connected": false, "status": "not_connected"},
        "instagram": {"connected": false, "status": "not_connected"},
        "facebook": {"connected": true, "profile_name": "John's Page", "status": "connected", "is_token_valid": true}
    }

Use Case: Check which platforms are ready for posting before scheduling content.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="disconnect_social_profile",
                description="""Disconnect a social media profile for a user.

Revokes OAuth access and marks the profile as disconnected. The user will
need to go through OAuth flow again to reconnect.

Note: This does NOT delete posts already published via this connection.

Returns:
    {
        "success": true,
        "message": "LinkedIn disconnected successfully"
    }

Errors:
- "No {platform} profile found" - User doesn't have this platform connected

Example:
    {"user_email": "user@example.com", "platform": "twitter"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user",
                        },
                        "platform": {
                            "type": "string",
                            "description": "Platform to disconnect",
                            "enum": ["linkedin", "twitter", "instagram", "facebook"],
                        },
                    },
                    "required": ["user_email", "platform"],
                    "additionalProperties": False,
                },
            ),
            # Content Calendar Tools
            Tool(
                name="list_scheduled_content",
                description="""List scheduled content posts for a user's content calendar.

Returns upcoming and past scheduled posts. Use this to see what's in the queue
or to find content IDs for updating/cancelling posts.

Returns:
    {
        "content": [
            {
                "id": 456,
                "title": "Product Launch",
                "content": "Excited to announce..." (truncated to 200 chars),
                "platforms": ["linkedin", "twitter"],
                "scheduled_date": "2024-01-15T10:00:00Z",
                "status": "scheduled",
                "published_at": null
            }
        ],
        "count": 1
    }

Status Values:
- draft: Created but not scheduled
- scheduled: Waiting for scheduled time
- published: Successfully posted
- failed: Publishing failed
- cancelled: User cancelled

Example: Get all scheduled posts for next 7 days
    {"user_email": "user@example.com", "status": "scheduled", "days_ahead": 7}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user",
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (optional)",
                            "enum": [
                                "draft",
                                "scheduled",
                                "published",
                                "failed",
                                "cancelled",
                            ],
                        },
                        "days_ahead": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 365,
                            "default": 30,
                            "description": "Number of days ahead to look (default: 30, max: 365)",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="create_scheduled_content",
                description="""Create a new scheduled content post for future publishing.

Creates a content calendar entry that will be automatically published at the
scheduled time. The user must have connected profiles for the specified platforms.

Platform Considerations:
- twitter: Max 280 characters for text
- linkedin: Supports longer form content, images, and articles
- facebook: Requires page access (not personal profiles)
- instagram: Requires media (image/video) for most post types

Returns:
    {
        "success": true,
        "content_id": 456,
        "title": "Product Launch",
        "scheduled_date": "2024-01-15T10:00:00Z",
        "platforms": ["linkedin", "twitter"]
    }

Errors:
- "User not found" - Invalid user_email
- "Invalid platform" - Platform not in allowed list

Example: Schedule a multi-platform post
    {
        "user_email": "user@example.com",
        "title": "Weekly Update",
        "content": "Check out our latest features! 🚀",
        "platforms": ["linkedin", "twitter"],
        "scheduled_date": "2024-01-20T14:00:00Z"
    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user creating the post",
                        },
                        "title": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                            "description": "Internal title for the post (not published, for organization)",
                        },
                        "content": {
                            "type": "string",
                            "minLength": 1,
                            "description": "The text content to post. Note: Twitter has 280 char limit.",
                        },
                        "platforms": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "linkedin",
                                    "twitter",
                                    "instagram",
                                    "facebook",
                                ],
                            },
                            "minItems": 1,
                            "description": "List of platforms to post to (user must have connected profiles)",
                        },
                        "scheduled_date": {
                            "type": "string",
                            "format": "date-time",
                            "description": "ISO 8601 datetime for publishing (e.g., 2024-01-15T10:00:00Z). Must be in the future.",
                        },
                        "media_urls": {
                            "type": "array",
                            "items": {"type": "string", "format": "uri"},
                            "description": "Optional: URLs of images/videos to attach. Required for Instagram.",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Optional tenant ID for multi-tenant context (set by pipeline agents).",
                        },
                    },
                    "required": [
                        "user_email",
                        "title",
                        "content",
                        "platforms",
                        "scheduled_date",
                    ],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="update_scheduled_content",
                description="""Update an existing scheduled content post.

Modify the title, content, scheduled time, or platforms of an existing post.
Can ONLY update content in 'draft' or 'scheduled' status.

Constraints:
- Cannot update already published content
- Cannot update cancelled or failed content
- At least one field (title, content, scheduled_date, or platforms) should be provided

Returns:
    {
        "success": true,
        "content_id": 456,
        "title": "Updated Title",
        "status": "scheduled"
    }

Errors:
- "Content with id X not found" - Invalid content_id
- "Cannot update content with status 'published'" - Already published

Example: Update the scheduled time
    {"content_id": 456, "scheduled_date": "2024-01-20T15:00:00Z"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content_id": {
                            "type": "integer",
                            "description": "ID of the content to update (from create_scheduled_content or list_scheduled_content)",
                        },
                        "title": {
                            "type": "string",
                            "maxLength": 200,
                            "description": "New title (optional)",
                        },
                        "content": {
                            "type": "string",
                            "description": "New content text (optional). Remember Twitter 280 char limit.",
                        },
                        "scheduled_date": {
                            "type": "string",
                            "format": "date-time",
                            "description": "New scheduled date in ISO 8601 format (optional)",
                        },
                        "platforms": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "linkedin",
                                    "twitter",
                                    "instagram",
                                    "facebook",
                                ],
                            },
                            "description": "New list of platforms (optional)",
                        },
                    },
                    "required": ["content_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="cancel_scheduled_content",
                description="""Cancel a scheduled content post.

Marks the content as cancelled so it will NOT be published at the scheduled time.
This is a soft delete - the content record remains for history.

Constraints:
- Cannot cancel already published content
- Cancelled content cannot be un-cancelled (create a new post instead)

Returns:
    {
        "success": true,
        "content_id": 456,
        "message": "Content 'Weekly Update' cancelled"
    }

Errors:
- "Content with id X not found" - Invalid content_id
- "Cannot cancel already published content" - Already published

Example:
    {"content_id": 456}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content_id": {
                            "type": "integer",
                            "description": "ID of the content to cancel (from list_scheduled_content)",
                        },
                    },
                    "required": ["content_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="publish_content_now",
                description="""Immediately publish a scheduled or draft content post.

Publishes the content to ALL configured platforms right now, regardless of
the originally scheduled time. Good for urgent posts or testing.

Constraints:
- Can only publish 'draft' or 'scheduled' status content
- Cannot re-publish already published content
- Requires connected profiles for all specified platforms

Returns:
    {
        "success": true,
        "content_id": 456,
        "status": "published" | "partial" | "failed",
        "results": {"linkedin": {"post_id": "..."}, "twitter": {"tweet_id": "..."}},
        "errors": {}  // Platform-specific errors if any
    }

Status Values:
- "published": All platforms succeeded
- "partial": Some platforms succeeded, some failed (check errors)
- "failed": All platforms failed

Example:
    {"content_id": 456}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content_id": {
                            "type": "integer",
                            "description": "ID of the content to publish immediately",
                        },
                    },
                    "required": ["content_id"],
                    "additionalProperties": False,
                },
            ),
            # Direct Posting Tools
            Tool(
                name="post_to_linkedin",
                description="""Post content IMMEDIATELY to LinkedIn.

Publishes a post to the user's LinkedIn profile or company page right now.
Requires the user to have a connected and valid LinkedIn profile.

Prerequisites:
- User must have connected LinkedIn via OAuth (check with get_social_profile_status)
- OAuth token must be valid (not expired)

Returns:
    {
        "success": true,
        "platform": "linkedin",
        "post_id": "urn:li:share:123456789",
        "result": {...}  // Full LinkedIn API response
    }

Errors:
- "LinkedIn profile not connected" - No OAuth connection
- "LinkedIn token is expired" - Need to reconnect

Example:
    {"user_email": "user@example.com", "text": "Excited to share our Q4 results! 📈"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user with connected LinkedIn",
                        },
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 3000,
                            "description": "Post text content (max 3000 characters for LinkedIn)",
                        },
                        "media_urls": {
                            "type": "array",
                            "items": {"type": "string", "format": "uri"},
                            "description": "Optional: Image or video URLs to attach",
                        },
                    },
                    "required": ["user_email", "text"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="post_to_twitter",
                description="""Post a tweet IMMEDIATELY to Twitter/X.

Publishes a tweet to the user's connected Twitter account right now.
STRICT 280 character limit enforced - will error if exceeded.

Prerequisites:
- User must have connected Twitter via OAuth (check with get_social_profile_status)
- OAuth token must be valid

Character Limit: 280 characters maximum (enforced)

Returns:
    {
        "success": true,
        "platform": "twitter",
        "tweet_id": "1234567890123456789",
        "result": {"data": {"id": "1234567890123456789", "text": "..."}}
    }

Errors:
- "Tweet exceeds 280 character limit" - Text too long
- "Twitter profile not connected" - No OAuth connection
- "Twitter token is expired" - Need to reconnect

Example:
    {"user_email": "user@example.com", "text": "Just launched our new feature! 🚀 #ProductLaunch"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user with connected Twitter",
                        },
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 280,
                            "description": "Tweet text (STRICTLY max 280 characters)",
                        },
                        "media_urls": {
                            "type": "array",
                            "items": {"type": "string", "format": "uri"},
                            "maxItems": 4,
                            "description": "Optional: Up to 4 image URLs to attach",
                        },
                    },
                    "required": ["user_email", "text"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="post_to_facebook",
                description="""Post content IMMEDIATELY to a Facebook Page.

Publishes a post to the user's connected Facebook Page (not personal profile).
Requires the user to have connected Facebook and selected a Page to manage.

Prerequisites:
- User must have connected Facebook via OAuth
- User must have selected a Facebook Page to post to
- OAuth token and page access token must be valid

Note: This posts to PAGES only, not personal profiles (Facebook API limitation).

Returns:
    {
        "success": true,
        "platform": "facebook",
        "post_id": "123456789_987654321",
        "result": {"id": "123456789_987654321"}
    }

Errors:
- "Facebook profile not connected" - No OAuth connection
- "Facebook page not configured" - Need to select a Page

Example:
    {"user_email": "user@example.com", "text": "Check out our latest blog post! 📝"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user with connected Facebook Page",
                        },
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Post text content",
                        },
                        "media_urls": {
                            "type": "array",
                            "items": {"type": "string", "format": "uri"},
                            "description": "Optional: Image or video URLs to attach",
                        },
                    },
                    "required": ["user_email", "text"],
                },
            ),
            # Automation Task Tools
            Tool(
                name="list_automation_tasks",
                description="""List automation tasks for a user's account.

Shows background task history including scheduled publishing jobs, OAuth refreshes,
and other automated operations. Useful for debugging and monitoring.

Returns:
    {
        "tasks": [
            {
                "id": 789,
                "task_type": "publish_content",
                "status": "completed",
                "created_at": "2024-01-14T09:00:00Z",
                "completed_at": "2024-01-14T09:00:05Z",
                "error_message": null,
                "result": {"post_ids": {...}}
            }
        ],
        "count": 1
    }

Task Types:
- publish_content: Scheduled post publishing
- refresh_token: OAuth token refresh
- sync_profile: Profile data sync from platform

Status Values:
- pending: Queued, waiting to run
- running: Currently executing
- completed: Finished successfully
- failed: Error occurred (see error_message)
- cancelled: Manually cancelled

Example: Get failed tasks for debugging
    {"user_email": "user@example.com", "status": "failed", "limit": 10}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user",
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by task status (optional)",
                            "enum": [
                                "pending",
                                "in_progress",
                                "completed",
                                "failed",
                                "cancelled",
                            ],
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 20,
                            "description": "Maximum number of tasks to return (default: 20, max: 100)",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="get_platform_oauth_url",
                description="""Get the OAuth authorization URL for connecting a new social platform.

Generates a unique authorization URL that the user should visit to grant
access to their social media account. After authorization, the platform
will redirect back with an auth code to complete the connection.

Workflow:
1. Call this tool to get authorization_url
2. Redirect user to authorization_url in their browser
3. User approves access on the platform
4. Platform redirects to callback URL with auth code
5. Backend exchanges code for access token automatically

Returns:
    {
        "platform": "linkedin",
        "authorization_url": "https://www.linkedin.com/oauth/v2/authorization?...",
        "state": "abc123-state-token",
        "instructions": "Redirect the user to the authorization URL..."
    }

Errors:
- "Unsupported platform" - Platform not in allowed list
- "{Platform} OAuth is not configured" - Missing API credentials in environment

Example:
    {"platform": "linkedin", "user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "platform": {
                            "type": "string",
                            "description": "Social platform to connect",
                            "enum": ["linkedin", "twitter", "facebook", "instagram"],
                        },
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email of the user initiating the OAuth flow",
                        },
                    },
                    "required": ["platform", "user_email"],
                    "additionalProperties": False,
                },
            ),
            # Google Business Profile Tools
            Tool(
                name="gbp_get_status",
                description="""Get Google Business Profile connection status for a user.

Returns the current GBP connection status including account details,
connection state, and whether the profile is in mock mode (for testing).

Returns:
    {
        "connected": true,
        "profile": {
            "id": 123,
            "google_email": "user@gmail.com",
            "gbp_account_id": "accounts/123456",
            "gbp_account_name": "My Business",
            "status": "connected",
            "is_mock": false,
            "is_token_valid": true,
            "location_count": 3
        }
    }

If not connected:
    {"connected": false, "profile": null}

Example:
    {"user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_connect",
                description="""Initiate Google Business Profile OAuth connection.

Generates an authorization URL for the user to connect their Google account.
Supports both real OAuth (when credentials configured) and mock mode (for testing).

Returns:
    {
        "authorization_url": "https://accounts.google.com/o/oauth2/...",
        "is_mock_mode": false,
        "instructions": "Redirect user to authorization URL..."
    }

In mock mode, use gbp_test_connect instead for instant connection.

Example:
    {"user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_test_connect",
                description="""Create a test/mock Google Business Profile connection.

Creates a simulated GBP connection for testing without real Google OAuth.
Useful for development, demos, and testing the GBP workflow.

Returns:
    {
        "success": true,
        "message": "Test connection created",
        "profile": {
            "id": 123,
            "status": "connected",
            "is_mock": true,
            "google_email": "test@example.com"
        }
    }

Example:
    {"user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_disconnect",
                description="""Disconnect Google Business Profile for a user.

Revokes the GBP connection and clears stored tokens. The user will need
to re-authenticate to use GBP features again.

Returns:
    {
        "success": true,
        "message": "Google Business Profile disconnected"
    }

Errors:
- "No Google Business Profile found" - User doesn't have GBP connected

Example:
    {"user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_list_accounts",
                description="""List available Google Business Profile accounts.

Returns GBP accounts the user has access to. The user must select one
account to manage locations under.

Returns:
    {
        "accounts": [
            {
                "name": "accounts/123456789",
                "accountName": "My Business Account",
                "type": "PERSONAL",
                "role": "PRIMARY_OWNER",
                "state": {"status": "VERIFIED"}
            }
        ],
        "count": 1
    }

Errors:
- "No Google Business Profile found" - User doesn't have GBP connected
- "GBP connection not active" - Token expired or revoked

Example:
    {"user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_select_account",
                description="""Select a Google Business Profile account to use.

Sets the active GBP account for managing business locations.
The account_id should be from the gbp_list_accounts response.

Returns:
    {
        "success": true,
        "message": "Account selected",
        "account_id": "accounts/123456789",
        "account_name": "My Business Account"
    }

Example:
    {"user_email": "user@example.com", "account_id": "accounts/123456789"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                        "account_id": {
                            "type": "string",
                            "description": "GBP account ID (e.g., 'accounts/123456789')",
                        },
                    },
                    "required": ["user_email", "account_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_list_locations",
                description="""List business locations for the user's GBP account.

Returns all business locations associated with the selected GBP account.

Returns:
    {
        "locations": [
            {
                "id": 1,
                "location_id": "locations/abc123",
                "business_name": "Downtown Coffee Shop",
                "primary_category": "Coffee shop",
                "full_address": "123 Main St, San Francisco, CA 94102",
                "phone_number": "+1-415-555-0100",
                "website_url": "https://example.com",
                "verification_status": "verified",
                "is_synced": true
            }
        ],
        "count": 1
    }

Errors:
- "No Google Business Profile found" - User doesn't have GBP connected
- "No GBP account selected" - User needs to select an account first

Example:
    {"user_email": "user@example.com"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                    },
                    "required": ["user_email"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_create_location",
                description="""Create a new business location in Google Business Profile.

Creates a new business listing. Required fields: business_name, address_line1, city.

Returns:
    {
        "success": true,
        "location": {
            "id": 2,
            "location_id": "locations/new123",
            "business_name": "My New Shop",
            "full_address": "456 Oak Ave, San Francisco, CA 94108",
            "verification_status": "unverified"
        }
    }

Note: New locations typically require verification through Google.

Example:
    {
        "user_email": "user@example.com",
        "business_name": "My Coffee Shop",
        "primary_category": "Coffee shop",
        "address_line1": "123 Main Street",
        "city": "San Francisco",
        "state": "CA",
        "postal_code": "94102",
        "country": "US",
        "phone_number": "+1-415-555-0100"
    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                        "business_name": {
                            "type": "string",
                            "description": "Name of the business",
                        },
                        "primary_category": {
                            "type": "string",
                            "description": "Primary business category (e.g., 'Coffee shop')",
                        },
                        "address_line1": {
                            "type": "string",
                            "description": "Street address line 1",
                        },
                        "address_line2": {
                            "type": "string",
                            "description": "Street address line 2 (optional)",
                        },
                        "city": {
                            "type": "string",
                            "description": "City name",
                        },
                        "state": {
                            "type": "string",
                            "description": "State/province code (e.g., 'CA')",
                        },
                        "postal_code": {
                            "type": "string",
                            "description": "Postal/ZIP code",
                        },
                        "country": {
                            "type": "string",
                            "description": "Country code (e.g., 'US')",
                            "default": "US",
                        },
                        "phone_number": {
                            "type": "string",
                            "description": "Business phone number",
                        },
                        "website_url": {
                            "type": "string",
                            "format": "uri",
                            "description": "Business website URL",
                        },
                    },
                    "required": [
                        "user_email",
                        "business_name",
                        "address_line1",
                        "city",
                    ],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_delete_location",
                description="""Delete a business location from Google Business Profile.

Removes a location from the user's GBP account. This action cannot be undone.

Returns:
    {
        "success": true,
        "message": "Location 'My Coffee Shop' deleted"
    }

Errors:
- "Location not found" - The specified location doesn't exist
- "Cannot delete verified location" - Some restrictions may apply

Example:
    {"user_email": "user@example.com", "location_id": "locations/abc123"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email address of the user",
                        },
                        "location_id": {
                            "type": "string",
                            "description": "Location ID to delete (e.g., 'locations/abc123')",
                        },
                    },
                    "required": ["user_email", "location_id"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="gbp_search_categories",
                description="""Search for Google Business Profile categories.

Searches available business categories for creating or updating locations.
Returns matching categories with their display names.

Returns:
    {
        "categories": [
            {"name": "categories/gcid:coffee_shop", "displayName": "Coffee shop"},
            {"name": "categories/gcid:cafe", "displayName": "Cafe"}
        ],
        "count": 2
    }

Example:
    {"query": "coffee"}""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for categories (optional, returns all if empty)",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            result = await _execute_tool(name, arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]
        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": str(e), "tool": name}),
                )
            ]

    # =========================================================================
    # RESOURCES - Data endpoints for agents to discover and access
    # =========================================================================
    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available data resources.

        Resources provide read-only access to data that agents might need.
        These complement the tools by providing discovery mechanisms.
        """
        return [
            Resource(
                uri="automation://platforms",
                name="Supported Platforms",
                description="List of supported social media platforms with their capabilities and limitations",
                mimeType="application/json",
            ),
            Resource(
                uri="automation://status-values",
                name="Status Values",
                description="Valid status values for content and profiles (for filtering)",
                mimeType="application/json",
            ),
            Resource(
                uri="automation://character-limits",
                name="Character Limits",
                description="Character limits for each social platform",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read a resource by URI."""
        if uri == "automation://platforms":
            return json.dumps(
                {
                    "platforms": [
                        {
                            "id": "linkedin",
                            "name": "LinkedIn",
                            "description": "Professional networking - company pages and personal profiles",
                            "character_limit": 3000,
                            "supports_media": True,
                            "media_types": ["image", "video", "document"],
                            "requires_page": False,
                            "oauth_scopes": ["w_member_social", "r_liteprofile"],
                        },
                        {
                            "id": "twitter",
                            "name": "Twitter/X",
                            "description": "Microblogging - tweets with strict character limit",
                            "character_limit": 280,
                            "supports_media": True,
                            "media_types": ["image", "video", "gif"],
                            "max_media": 4,
                            "requires_page": False,
                            "oauth_scopes": ["tweet.read", "tweet.write", "users.read"],
                        },
                        {
                            "id": "facebook",
                            "name": "Facebook",
                            "description": "Social network - posts to Facebook Pages only (not personal)",
                            "character_limit": 63206,
                            "supports_media": True,
                            "media_types": ["image", "video"],
                            "requires_page": True,
                            "oauth_scopes": [
                                "pages_manage_posts",
                                "pages_read_engagement",
                            ],
                        },
                        {
                            "id": "instagram",
                            "name": "Instagram",
                            "description": "Visual social network - requires media for most posts",
                            "character_limit": 2200,
                            "supports_media": True,
                            "media_types": ["image", "video", "carousel"],
                            "requires_media": True,
                            "requires_page": True,
                            "note": "Connected via Facebook Business",
                        },
                    ]
                },
                indent=2,
            )

        elif uri == "automation://status-values":
            return json.dumps(
                {
                    "content_status": {
                        "draft": "Content created but not scheduled",
                        "scheduled": "Content scheduled for future publishing",
                        "published": "Content successfully published",
                        "failed": "Publishing failed (check error message)",
                        "cancelled": "Content cancelled by user",
                        "partial": "Published to some platforms, failed on others",
                    },
                    "profile_status": {
                        "connected": "OAuth connection active and valid",
                        "disconnected": "User disconnected the profile",
                        "expired": "OAuth token expired, needs reconnection",
                        "error": "Connection error, needs troubleshooting",
                    },
                    "task_status": {
                        "pending": "Task queued but not started",
                        "running": "Task currently executing",
                        "completed": "Task finished successfully",
                        "failed": "Task failed (check error message)",
                        "cancelled": "Task cancelled",
                    },
                },
                indent=2,
            )

        elif uri == "automation://character-limits":
            return json.dumps(
                {
                    "limits": {
                        "twitter": {"text": 280, "alt_text": 1000},
                        "linkedin": {"text": 3000, "article": 125000},
                        "facebook": {"text": 63206, "comment": 8000},
                        "instagram": {"caption": 2200, "bio": 150, "hashtags": 30},
                    },
                    "recommendations": {
                        "twitter": "Keep tweets concise. Use threads for longer content.",
                        "linkedin": "First 150 chars are most visible. Use formatting for readability.",
                        "facebook": "First 400 chars show before 'See more'. Use engaging hooks.",
                        "instagram": "First line is most important. Use line breaks for readability.",
                    },
                },
                indent=2,
            )

        raise ValueError(f"Unknown resource URI: {uri}")

    # =========================================================================
    # PROMPTS - Pre-built workflow templates for common tasks
    # =========================================================================
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """List available prompts for common workflows.

        Prompts help agents understand how to accomplish common tasks
        by providing structured templates with required arguments.
        """
        return [
            Prompt(
                name="schedule_multi_platform_post",
                description="Schedule a post to multiple social media platforms at once. "
                "Guides you through checking connections and creating the scheduled content.",
                arguments=[
                    PromptArgument(
                        name="user_email",
                        description="Email of the user",
                        required=True,
                    ),
                    PromptArgument(
                        name="content",
                        description="The text content to post",
                        required=True,
                    ),
                    PromptArgument(
                        name="platforms",
                        description="Comma-separated platforms (linkedin,twitter,facebook)",
                        required=True,
                    ),
                ],
            ),
            Prompt(
                name="check_and_post_now",
                description="Check if platforms are connected and post immediately. "
                "Validates connections before attempting to post.",
                arguments=[
                    PromptArgument(
                        name="user_email",
                        description="Email of the user",
                        required=True,
                    ),
                    PromptArgument(
                        name="platform",
                        description="Platform to post to (linkedin, twitter, or facebook)",
                        required=True,
                    ),
                    PromptArgument(
                        name="content",
                        description="The text content to post",
                        required=True,
                    ),
                ],
            ),
            Prompt(
                name="connect_new_platform",
                description="Generate OAuth URL and instructions for connecting a new social platform.",
                arguments=[
                    PromptArgument(
                        name="user_email",
                        description="Email of the user",
                        required=True,
                    ),
                    PromptArgument(
                        name="platform",
                        description="Platform to connect (linkedin, twitter, facebook, instagram)",
                        required=True,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict) -> GetPromptResult:
        """Get a prompt template with filled arguments."""
        if name == "schedule_multi_platform_post":
            user_email = arguments.get("user_email", "")
            content = arguments.get("content", "")
            platforms = arguments.get("platforms", "").split(",")

            return GetPromptResult(
                description="Schedule a multi-platform post",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""I want to schedule a post across multiple platforms.

User: {user_email}
Platforms: {', '.join(platforms)}
Content: {content}

Please:
1. First, call get_social_profile_status to check which platforms are connected
2. For any platform not connected, use get_platform_oauth_url to generate connection URLs
3. For connected platforms, call create_scheduled_content with the content
4. Report which platforms were scheduled and which need connection""",
                        ),
                    ),
                ],
            )

        elif name == "check_and_post_now":
            user_email = arguments.get("user_email", "")
            platform = arguments.get("platform", "")
            content = arguments.get("content", "")

            tool_name = (
                f"post_to_{platform}"
                if platform in ["linkedin", "twitter", "facebook"]
                else None
            )

            return GetPromptResult(
                description=f"Post immediately to {platform}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""I want to post to {platform} right now.

User: {user_email}
Platform: {platform}
Content: {content}

Please:
1. Call get_social_profile_status to verify {platform} is connected
2. If connected and token is valid, call {tool_name or f'post_to_{platform}'} with the content
3. If not connected, use get_platform_oauth_url to provide connection instructions
4. Report the result (post ID if successful, or connection instructions if needed)""",
                        ),
                    ),
                ],
            )

        elif name == "connect_new_platform":
            user_email = arguments.get("user_email", "")
            platform = arguments.get("platform", "")

            return GetPromptResult(
                description=f"Connect {platform} account",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""I want to connect my {platform} account.

User: {user_email}
Platform: {platform}

Please:
1. First check current status with get_social_profile_status
2. If already connected, inform the user and ask if they want to reconnect
3. If not connected, call get_platform_oauth_url to generate the authorization URL
4. Provide clear instructions for the user to complete the OAuth flow""",
                        ),
                    ),
                ],
            )

        raise ValueError(f"Unknown prompt: {name}")

    return server


def _execute_tool_sync(name: str, arguments: dict) -> dict[str, Any]:
    """
    Execute a tool synchronously and return the result.

    This is the sync implementation that performs Django ORM operations.
    It is wrapped by _execute_tool with sync_to_async for async contexts.
    """

    # Helper to get user by email
    def get_user(email: str):
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            raise ValueError(f"User with email {email} not found")

    # Social Profile Tools
    if name == "list_social_profiles":
        user = get_user(arguments["user_email"])
        queryset = SocialProfile.objects.filter(user=user)

        if "platform" in arguments:
            queryset = queryset.filter(platform=arguments["platform"])

        profiles = []
        for profile in queryset:
            profiles.append(
                {
                    "id": profile.id,
                    "platform": profile.platform,
                    "platform_display": profile.get_platform_display(),
                    "status": profile.status,
                    "profile_name": profile.profile_name,
                    "profile_url": profile.profile_url,
                    "is_token_valid": profile.is_token_valid,
                    "is_token_expiring_soon": profile.is_token_expiring_soon,
                    "token_expires_at": profile.token_expires_at,
                }
            )

        return {"profiles": profiles, "count": len(profiles)}

    elif name == "get_social_profile_status":
        user = get_user(arguments["user_email"])
        profiles = SocialProfile.objects.filter(user=user)

        status_dict = {}
        for platform in ["linkedin", "twitter", "instagram", "facebook"]:
            profile = profiles.filter(platform=platform).first()
            if profile:
                status_dict[platform] = {
                    "connected": profile.status == "connected",
                    "profile_name": profile.profile_name,
                    "status": profile.status,
                    "is_token_valid": profile.is_token_valid,
                }
            else:
                status_dict[platform] = {"connected": False, "status": "not_connected"}

        return status_dict

    elif name == "disconnect_social_profile":
        user = get_user(arguments["user_email"])
        platform = arguments["platform"]

        try:
            profile = SocialProfile.objects.get(user=user, platform=platform)
            profile.disconnect()
            return {
                "success": True,
                "message": (
                    f"{profile.get_platform_display()} disconnected from this app "
                    "and local tokens cleared. If needed, also revoke access in "
                    f"your {profile.get_platform_display()} account settings."
                ),
            }
        except SocialProfile.DoesNotExist:
            return {"success": False, "error": f"No {platform} profile found"}

    # Content Calendar Tools
    elif name == "list_scheduled_content":
        user = get_user(arguments["user_email"])
        days_ahead = arguments.get("days_ahead", 30)

        queryset = ContentCalendar.objects.filter(user=user)

        if "status" in arguments:
            queryset = queryset.filter(status=arguments["status"])
        else:
            # Default: show future scheduled content (from now to days_ahead)
            now = timezone.now()
            queryset = queryset.filter(
                scheduled_date__gte=now,
                scheduled_date__lte=now + timedelta(days=days_ahead),
                status="scheduled",
            )

        content_list = []
        for content in queryset.order_by("scheduled_date")[:50]:
            content_list.append(
                {
                    "id": content.id,
                    "title": content.title,
                    "content": (
                        content.content[:200] + "..."
                        if len(content.content) > 200
                        else content.content
                    ),
                    "platforms": content.platforms,
                    "scheduled_date": content.scheduled_date,
                    "status": content.status,
                    "published_at": content.published_at,
                }
            )

        return {"content": content_list, "count": len(content_list)}

    elif name == "create_scheduled_content":
        user = get_user(arguments["user_email"])

        # Parse scheduled date
        scheduled_date = datetime.fromisoformat(
            arguments["scheduled_date"].replace("Z", "+00:00")
        )

        # Validate platforms
        platforms = arguments["platforms"]
        valid_platforms = ["linkedin", "twitter", "instagram", "facebook"]
        for p in platforms:
            if p not in valid_platforms:
                raise ValueError(f"Invalid platform: {p}")

        # Optional tenant context for multi-tenant pipeline usage
        tenant_id = arguments.get("tenant_id")

        # Strip markdown from content — social platforms render plain text
        from automation.utils import strip_markdown

        # Create content
        create_kwargs = {
            "user": user,
            "title": strip_markdown(arguments["title"]),
            "content": strip_markdown(arguments["content"]),
            "platforms": platforms,
            "scheduled_date": scheduled_date,
            "media_urls": arguments.get("media_urls", []),
            "status": "scheduled",
        }
        if tenant_id:
            create_kwargs["tenant_id"] = tenant_id
        content = ContentCalendar.objects.create(**create_kwargs)

        # Associate with social profiles — prefer user's own, fall back to tenant members
        if tenant_id:
            from django.db.models import Q
            from tenants.models import Membership

            member_user_ids = list(
                Membership.objects.filter(
                    tenant_id=tenant_id,
                    is_active=True,
                ).values_list("user_id", flat=True)
            )
            for platform in platforms:
                profile = SocialProfile.objects.filter(
                    Q(user=user, platform=platform, status="connected")
                    | Q(
                        tenant__isnull=True,
                        user_id__in=member_user_ids,
                        platform=platform,
                        status="connected",
                    )
                ).first()
                if profile:
                    content.social_profiles.add(profile)
        else:
            for platform in platforms:
                try:
                    profile = SocialProfile.objects.get(
                        user=user, platform=platform, status="connected"
                    )
                    content.social_profiles.add(profile)
                except SocialProfile.DoesNotExist:
                    pass  # Profile not connected, skip

        return {
            "success": True,
            "content_id": content.id,
            "title": content.title,
            "scheduled_date": content.scheduled_date,
            "platforms": content.platforms,
        }

    elif name == "update_scheduled_content":
        content_id = arguments["content_id"]

        try:
            content = ContentCalendar.objects.get(id=content_id)
        except ContentCalendar.DoesNotExist:
            raise ValueError(f"Content with id {content_id} not found")

        if content.status not in ["draft", "scheduled"]:
            raise ValueError(
                f"Cannot update content with status '{content.status}'. "
                "Only draft or scheduled content can be updated."
            )

        # Update fields if provided
        if "title" in arguments:
            content.title = arguments["title"]
        if "content" in arguments:
            content.content = arguments["content"]
        if "scheduled_date" in arguments:
            content.scheduled_date = datetime.fromisoformat(
                arguments["scheduled_date"].replace("Z", "+00:00")
            )
        if "platforms" in arguments:
            platforms = arguments["platforms"]
            if not isinstance(platforms, list):
                raise ValueError("platforms must be provided as a list")

            # Update platforms and keep social_profiles M2M in sync
            connected_profiles = SocialProfile.objects.filter(
                user=content.user, platform__in=platforms, status="connected"
            )
            connected_platforms = set(
                connected_profiles.values_list("platform", flat=True)
            )

            missing_platforms = set(platforms) - connected_platforms
            if missing_platforms:
                missing_str = ", ".join(sorted(str(p) for p in missing_platforms))
                raise ValueError(
                    f"No connected social profiles found for: {missing_str}"
                )

            content.platforms = platforms
            content.social_profiles.set(connected_profiles)

        content.save()

        return {
            "success": True,
            "content_id": content.id,
            "title": content.title,
            "status": content.status,
        }

    elif name == "cancel_scheduled_content":
        content_id = arguments["content_id"]

        try:
            content = ContentCalendar.objects.get(id=content_id)
        except ContentCalendar.DoesNotExist:
            raise ValueError(f"Content with id {content_id} not found")

        if content.status == "published":
            raise ValueError("Cannot cancel already published content")

        content.status = "cancelled"
        content.save()

        return {
            "success": True,
            "content_id": content.id,
            "message": f"Content '{content.title}' cancelled",
        }

    elif name == "publish_content_now":
        content_id = arguments["content_id"]

        try:
            content = ContentCalendar.objects.get(id=content_id)
        except ContentCalendar.DoesNotExist:
            raise ValueError(f"Content with id {content_id} not found")

        if content.status not in ["draft", "scheduled"]:
            raise ValueError(
                f"Cannot publish content with status '{content.status}'. "
                "Only draft or scheduled content can be published."
            )

        results, errors = publish_content(content, log_prefix="MCP: ")
        final_status = update_content_status(content, results, errors)

        return {
            "success": final_status in ["published", "partial"],
            "content_id": content.id,
            "status": final_status,
            "results": results,
            "errors": errors,
        }

    # Direct Posting Tools
    elif name == "post_to_linkedin":
        from .constants import TEST_ACCESS_TOKEN

        user = get_user(arguments["user_email"])

        try:
            profile = SocialProfile.objects.get(
                user=user, platform="linkedin", status="connected"
            )
        except SocialProfile.DoesNotExist:
            raise ValueError("LinkedIn profile not connected")

        # Check for test mode
        if profile.access_token == TEST_ACCESS_TOKEN:
            return {
                "success": True,
                "platform": "linkedin",
                "post_id": "test_post_id_12345",
                "test_mode": True,
                "message": "Post simulated in test mode (no real LinkedIn API call)",
                "result": {"id": "test_post_id_12345", "test_mode": True},
            }

        # Get valid access token (refreshes if needed)
        try:
            access_token = profile.get_valid_access_token()
        except ValueError as e:
            raise ValueError(f"LinkedIn token error: {str(e)}. Please reconnect.")

        if not access_token:
            raise ValueError("LinkedIn token is missing. Please reconnect.")

        text = arguments["text"]
        media_urls = arguments.get("media_urls", [])

        # Get the user's LinkedIn URN (profile_id stores the LinkedIn user ID)
        user_urn = profile.profile_id
        if not user_urn:
            raise ValueError("LinkedIn profile ID not found. Please reconnect.")

        # Create the post using correct parameter names
        result = linkedin_service.create_share(
            access_token=access_token,
            user_urn=user_urn,
            text=text,
            image_urns=media_urls if media_urls else None,
        )

        return {
            "success": True,
            "platform": "linkedin",
            "post_id": result.get("id"),
            "result": result,
        }

    elif name == "post_to_twitter":
        from .constants import TWITTER_TEST_ACCESS_TOKEN

        user = get_user(arguments["user_email"])

        try:
            profile = SocialProfile.objects.get(
                user=user, platform="twitter", status="connected"
            )
        except SocialProfile.DoesNotExist:
            raise ValueError("Twitter profile not connected")

        # Check for test mode
        if profile.access_token == TWITTER_TEST_ACCESS_TOKEN:
            return {
                "success": True,
                "platform": "twitter",
                "tweet_id": "test_tweet_id_12345",
                "test_mode": True,
                "message": "Tweet simulated in test mode (no real Twitter API call)",
                "result": {"id": "test_tweet_id_12345", "test_mode": True},
            }

        if not profile.is_token_valid:
            raise ValueError("Twitter token is expired. Please reconnect.")

        text = arguments["text"]
        if len(text) > 280:
            raise ValueError("Tweet exceeds 280 character limit")

        media_urls = arguments.get("media_urls", [])

        # Create the tweet
        result = twitter_service.create_tweet(
            access_token=profile.access_token,
            text=text,
            media_ids=media_urls,
        )

        return {
            "success": True,
            "platform": "twitter",
            "tweet_id": result.get("id"),
            "result": result,
        }

    elif name == "post_to_facebook":
        from .constants import FACEBOOK_TEST_ACCESS_TOKEN, FACEBOOK_TEST_PAGE_TOKEN

        user = get_user(arguments["user_email"])

        try:
            profile = SocialProfile.objects.get(
                user=user, platform="facebook", status="connected"
            )
        except SocialProfile.DoesNotExist:
            raise ValueError("Facebook profile not connected")

        # Check for test mode
        if (
            profile.access_token == FACEBOOK_TEST_ACCESS_TOKEN
            or profile.page_access_token == FACEBOOK_TEST_PAGE_TOKEN
        ):
            return {
                "success": True,
                "platform": "facebook",
                "post_id": "test_fb_post_id_12345",
                "test_mode": True,
                "message": "Facebook post simulated in test mode (no real Facebook API call)",
                "result": {"id": "test_fb_post_id_12345", "test_mode": True},
            }

        if not profile.page_id or not profile.page_access_token:
            raise ValueError(
                "Facebook page not configured. Please select a page to post to."
            )

        text = arguments["text"]
        media_urls = arguments.get("media_urls", [])

        # Create the post
        result = facebook_service.create_page_post(
            page_id=profile.page_id,
            page_access_token=profile.page_access_token,
            message=text,
            media_urls=media_urls,
        )

        return {
            "success": True,
            "platform": "facebook",
            "post_id": result.get("id"),
            "result": result,
        }

    # Automation Task Tools
    elif name == "list_automation_tasks":
        user = get_user(arguments["user_email"])
        limit = arguments.get("limit", 20)

        queryset = AutomationTask.objects.filter(user=user)

        if "status" in arguments:
            queryset = queryset.filter(status=arguments["status"])

        tasks = []
        for task in queryset.order_by("-created_at")[:limit]:
            tasks.append(
                {
                    "id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "created_at": task.created_at,
                    "completed_at": task.completed_at,
                    "error_message": task.error_message,
                    "result": task.result,
                }
            )

        return {"tasks": tasks, "count": len(tasks)}

    elif name == "get_platform_oauth_url":
        platform = arguments["platform"]
        user = get_user(arguments["user_email"])

        # Generate state token
        import uuid
        from .models import OAuthState

        state_token = str(uuid.uuid4())

        # Get authorization URL based on platform
        service_map = {
            "linkedin": linkedin_service,
            "twitter": twitter_service,
            "facebook": facebook_service,
            "instagram": instagram_service,
        }

        service = service_map.get(platform)
        if not service:
            raise ValueError(f"Unsupported platform: {platform}")

        if not service.is_configured:
            raise ValueError(
                f"{platform.title()} OAuth is not configured. "
                "Please set the required environment variables."
            )

        # Handle PKCE for Twitter OAuth 2.0
        code_verifier = None
        if platform == "twitter":
            code_verifier, code_challenge = twitter_service.generate_pkce_pair()
            auth_url = service.get_authorization_url(state_token, code_challenge)
        else:
            auth_url = service.get_authorization_url(state_token)

        # Store OAuth state (with code_verifier for Twitter PKCE)
        OAuthState.objects.create(
            user=user,
            state=state_token,
            platform=platform,
            code_verifier=code_verifier,
        )

        return {
            "platform": platform,
            "authorization_url": auth_url,
            "state": state_token,
            "instructions": f"Redirect the user to the authorization URL to connect their {platform.title()} account.",
        }

    # Google Business Profile Tools
    elif name == "gbp_get_status":
        user = get_user(arguments["user_email"])

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
            location_count = GoogleBusinessLocation.objects.filter(
                profile=profile
            ).count()
            return {
                "connected": profile.status == "connected",
                "profile": {
                    "id": profile.id,
                    "google_email": profile.google_email,
                    "gbp_account_id": profile.gbp_account_id,
                    "gbp_account_name": profile.gbp_account_name,
                    "status": profile.status,
                    "is_mock": profile.is_mock,
                    "is_token_valid": profile.is_token_valid,
                    "location_count": location_count,
                },
            }
        except GoogleBusinessProfile.DoesNotExist:
            return {"connected": False, "profile": None}

    elif name == "gbp_connect":
        import uuid

        state = str(uuid.uuid4())
        auth_url = google_business_service.get_authorization_url(state)

        return {
            "authorization_url": auth_url,
            "is_mock_mode": google_business_service.is_mock_mode,
            "state": state,
            "instructions": (
                "Redirect the user to the authorization URL to connect their Google account. "
                "In mock mode, use gbp_test_connect for instant testing."
            ),
        }

    elif name == "gbp_test_connect":
        user = get_user(arguments["user_email"])

        # Create or update mock profile
        profile, created = GoogleBusinessProfile.objects.update_or_create(
            user=user,
            defaults={
                "google_account_id": "mock_google_account_123",
                "google_account_name": "Test Account",
                "google_email": f"test_{user.email}",
                "status": "connected",
                "is_mock": True,
            },
        )

        # Set mock tokens using property setters
        profile.access_token = google_business_service.MOCK_ACCESS_TOKEN
        profile.refresh_token = google_business_service.MOCK_REFRESH_TOKEN
        profile.save()

        return {
            "success": True,
            "message": "Test connection created (mock mode)",
            "profile": {
                "id": profile.id,
                "status": profile.status,
                "is_mock": profile.is_mock,
                "google_email": profile.google_email,
            },
        }

    elif name == "gbp_disconnect":
        user = get_user(arguments["user_email"])

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
            profile.disconnect()
            return {
                "success": True,
                "message": "Google Business Profile disconnected",
            }
        except GoogleBusinessProfile.DoesNotExist:
            return {"success": False, "error": "No Google Business Profile found"}

    elif name == "gbp_list_accounts":
        user = get_user(arguments["user_email"])

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
        except GoogleBusinessProfile.DoesNotExist:
            raise ValueError("No Google Business Profile found. Connect GBP first.")

        if profile.status != "connected":
            raise ValueError("GBP connection not active. Please reconnect.")

        access_token = profile.access_token
        accounts = google_business_service.list_accounts(access_token)

        return {"accounts": accounts, "count": len(accounts)}

    elif name == "gbp_select_account":
        user = get_user(arguments["user_email"])
        account_id = arguments["account_id"]

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
        except GoogleBusinessProfile.DoesNotExist:
            raise ValueError("No Google Business Profile found. Connect GBP first.")

        # Get account details from the account list
        access_token = profile.access_token
        accounts = google_business_service.list_accounts(access_token)

        selected_account = None
        for account in accounts:
            if account.get("name") == account_id:
                selected_account = account
                break

        if not selected_account:
            raise ValueError(f"Account {account_id} not found")

        # Update profile with selected account
        profile.gbp_account_id = account_id
        profile.gbp_account_name = selected_account.get("accountName", "")
        profile.save()

        return {
            "success": True,
            "message": "Account selected",
            "account_id": account_id,
            "account_name": profile.gbp_account_name,
        }

    elif name == "gbp_list_locations":
        user = get_user(arguments["user_email"])

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
        except GoogleBusinessProfile.DoesNotExist:
            raise ValueError("No Google Business Profile found. Connect GBP first.")

        if not profile.gbp_account_id:
            raise ValueError("No GBP account selected. Use gbp_select_account first.")

        locations = GoogleBusinessLocation.objects.filter(profile=profile)
        location_list = []

        for loc in locations:
            location_list.append(
                {
                    "id": loc.id,
                    "location_id": loc.location_id,
                    "business_name": loc.business_name,
                    "primary_category": loc.primary_category,
                    "full_address": loc.full_address,
                    "phone_number": loc.phone_number,
                    "website_url": loc.website_url,
                    "verification_status": loc.verification_status,
                    "is_synced": loc.is_synced,
                }
            )

        return {"locations": location_list, "count": len(location_list)}

    elif name == "gbp_create_location":
        user = get_user(arguments["user_email"])

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
        except GoogleBusinessProfile.DoesNotExist:
            raise ValueError("No Google Business Profile found. Connect GBP first.")

        if not profile.gbp_account_id:
            raise ValueError("No GBP account selected. Use gbp_select_account first.")

        # Prepare location data
        location_data = {
            "business_name": arguments["business_name"],
            "primary_category": arguments.get("primary_category", ""),
            "address_line1": arguments["address_line1"],
            "address_line2": arguments.get("address_line2", ""),
            "city": arguments["city"],
            "state": arguments.get("state", ""),
            "postal_code": arguments.get("postal_code", ""),
            "country": arguments.get("country", "US"),
            "phone_number": arguments.get("phone_number", ""),
            "website_url": arguments.get("website_url", ""),
        }

        # Create via service (handles mock/real mode)
        access_token = profile.access_token
        api_result = google_business_service.create_location(
            access_token, profile.gbp_account_id, location_data
        )

        # Save to database
        location = GoogleBusinessLocation.objects.create(
            profile=profile,
            location_id=api_result.get(
                "name", f"locations/mock_{timezone.now().timestamp()}"
            ),
            business_name=location_data["business_name"],
            primary_category=location_data["primary_category"],
            address_line1=location_data["address_line1"],
            address_line2=location_data["address_line2"],
            city=location_data["city"],
            state=location_data["state"],
            postal_code=location_data["postal_code"],
            country=location_data["country"],
            phone_number=location_data["phone_number"],
            website_url=location_data["website_url"],
            verification_status="unverified",
            is_synced=not profile.is_mock,
        )

        return {
            "success": True,
            "location": {
                "id": location.id,
                "location_id": location.location_id,
                "business_name": location.business_name,
                "full_address": location.full_address,
                "verification_status": location.verification_status,
            },
        }

    elif name == "gbp_delete_location":
        user = get_user(arguments["user_email"])
        location_id = arguments["location_id"]

        try:
            profile = GoogleBusinessProfile.objects.get(user=user)
        except GoogleBusinessProfile.DoesNotExist:
            raise ValueError("No Google Business Profile found")

        try:
            location = GoogleBusinessLocation.objects.get(
                profile=profile, location_id=location_id
            )
            business_name = location.business_name

            # Delete via service if not mock
            if not profile.is_mock:
                access_token = profile.access_token
                google_business_service.delete_location(access_token, location_id)

            location.delete()

            return {
                "success": True,
                "message": f"Location '{business_name}' deleted",
            }
        except GoogleBusinessLocation.DoesNotExist:
            raise ValueError(f"Location {location_id} not found")

    elif name == "gbp_search_categories":
        query = arguments.get("query", "")
        categories = google_business_service.list_categories(query=query)

        return {"categories": categories, "count": len(categories)}

    else:
        raise ValueError(f"Unknown tool: {name}")


async def _execute_tool(name: str, arguments: dict) -> dict[str, Any]:
    """
    Execute a tool asynchronously.

    Wraps the synchronous _execute_tool_sync with sync_to_async to properly
    handle Django ORM operations in async contexts without raising
    SynchronousOnlyOperation errors.
    """
    from asgiref.sync import sync_to_async

    return await sync_to_async(_execute_tool_sync, thread_sensitive=True)(
        name, arguments
    )


async def run_mcp_server():
    """Run the MCP server using stdio transport."""
    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main():
    """Entry point for running the MCP server."""
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
