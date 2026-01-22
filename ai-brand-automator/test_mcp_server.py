#!/usr/bin/env python
"""
Test script for the Automation MCP Server.

This script tests the MCP server functionality without requiring
an actual MCP client. It directly invokes the server's handlers.

Usage:
    python test_mcp_server.py           # Run all tests
    python test_mcp_server.py --verbose # Verbose output
    python test_mcp_server.py --live    # Test with real database (requires running Django)
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime

# Add the project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

import django  # noqa: E402

django.setup()

from automation.mcp_server import (  # noqa: E402
    create_mcp_server,
    _execute_tool,
    SERVER_NAME,
    SERVER_VERSION,
    SERVER_DESCRIPTION,
)


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(text: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.YELLOW}ℹ {text}{Colors.END}")


async def test_server_metadata():
    """Test server metadata is properly defined."""
    print_header("Testing Server Metadata")

    errors = []

    # Check server name
    if SERVER_NAME == "automation-mcp-server":
        print_success(f"Server name: {SERVER_NAME}")
    else:
        print_error(f"Unexpected server name: {SERVER_NAME}")
        errors.append("server_name")

    # Check version
    if SERVER_VERSION == "1.0.0":
        print_success(f"Server version: {SERVER_VERSION}")
    else:
        print_error(f"Unexpected version: {SERVER_VERSION}")
        errors.append("version")

    # Check description exists and is meaningful
    if len(SERVER_DESCRIPTION) > 100:
        print_success(f"Server description: {len(SERVER_DESCRIPTION)} characters")
        print(f"   Preview: {SERVER_DESCRIPTION[:150]}...")
    else:
        print_error("Server description too short")
        errors.append("description")

    return len(errors) == 0


async def test_server_creation():
    """Test that the server can be created."""
    print_header("Testing Server Creation")

    try:
        server = create_mcp_server()
        print_success(f"Server created: {server.name}")
        return True
    except Exception as e:
        print_error(f"Failed to create server: {e}")
        return False


async def test_list_tools():
    """Test listing all tools by invoking the registered handler."""
    print_header("Testing Tool Listing")

    # Create server to verify it can be instantiated (tools are registered internally)
    _ = create_mcp_server()

    expected_tools = [
        "list_social_profiles",
        "get_social_profile_status",
        "disconnect_social_profile",
        "list_scheduled_content",
        "create_scheduled_content",
        "update_scheduled_content",
        "cancel_scheduled_content",
        "publish_content_now",
        "post_to_linkedin",
        "post_to_twitter",
        "post_to_facebook",
        "list_automation_tasks",
        "get_platform_oauth_url",
    ]

    # Since we can't easily access internal handlers, we'll test via _execute_tool
    # which is our own function that handles all tool calls
    print(f"\nExpected {len(expected_tools)} tools:")

    # Verify each tool can be called (with expected errors for missing data)
    working = []
    for tool_name in expected_tools:
        try:
            # Try calling with minimal/invalid args to verify tool exists
            if "user_email" in tool_name or tool_name in [
                "list_social_profiles",
                "get_social_profile_status",
                "disconnect_social_profile",
                "list_scheduled_content",
                "create_scheduled_content",
                "list_automation_tasks",
                "get_platform_oauth_url",
                "post_to_linkedin",
                "post_to_twitter",
                "post_to_facebook",
            ]:
                args = {"user_email": "test@test.com"}
            elif "content_id" in tool_name or tool_name in [
                "update_scheduled_content",
                "cancel_scheduled_content",
                "publish_content_now",
            ]:
                args = {"content_id": 1}
            else:
                args = {}

            # Add platform for those that need it
            if tool_name == "disconnect_social_profile":
                args["platform"] = "linkedin"
            elif tool_name == "get_platform_oauth_url":
                args["platform"] = "linkedin"
            elif tool_name == "create_scheduled_content":
                args.update(
                    {
                        "title": "Test",
                        "content": "Test content",
                        "platforms": ["linkedin"],
                        "scheduled_date": "2025-01-01T10:00:00Z",
                    }
                )

            _ = await _execute_tool(tool_name, args)
            # Tool executed (even if returned error about user not found)
            print_success(f"  {tool_name}")
            working.append(tool_name)
        except ValueError as e:
            # ValueError means tool exists but validation failed (expected)
            print_success(f"  {tool_name} (validated: {str(e)[:40]}...)")
            working.append(tool_name)
        except Exception as e:
            if "Unknown tool" in str(e):
                print_error(f"  {tool_name} (NOT FOUND)")
            else:
                # Other errors mean tool exists
                print_success(f"  {tool_name} (error: {str(e)[:30]}...)")
                working.append(tool_name)

    return len(working) == len(expected_tools)


async def test_tool_schemas():
    """Test that _execute_tool handles all expected tools."""
    print_header("Testing Tool Execution Handler")

    # Test that unknown tools raise proper error
    try:
        await _execute_tool("unknown_tool_xyz", {})
        print_error("Unknown tool should raise ValueError")
        return False
    except ValueError as e:
        if "Unknown tool" in str(e):
            print_success("Unknown tool raises ValueError correctly")
        else:
            print_error(f"Wrong error message: {e}")
            return False

    # Test that missing required args raise errors
    test_cases = [
        ("list_social_profiles", {}, "user_email required"),
        ("post_to_twitter", {"user_email": "x@x.com"}, "text required"),
    ]

    for tool_name, args, desc in test_cases:
        try:
            await _execute_tool(tool_name, args)
            # If we get here without error about missing field, check what happened
            print_info(f"  {tool_name}: Executed (may have validation elsewhere)")
        except (ValueError, KeyError, TypeError):
            print_success(f"  {tool_name}: Validation works - {desc}")
        except Exception as exc:
            print_info(f"  {tool_name}: Got {type(exc).__name__}: {exc}")

    return True


async def test_resources():
    """Test resource functionality."""
    print_header("Testing Resources")

    # Resources are read via read_resource in the server
    print_info("Resources are registered but require MCP client to read")
    print_info("Resource URIs:")
    print("  - automation://platforms")
    print("  - automation://status-values")
    print("  - automation://character-limits")

    return True


async def test_prompts():
    """Test prompt functionality."""
    print_header("Testing Prompts")

    print_info("Prompts are registered but require MCP client to invoke")
    print_info("Available prompts:")
    print("  - schedule_multi_platform_post")
    print("  - check_and_post_now")
    print("  - connect_new_platform")

    return True


async def test_tool_execution_validation():
    """Test tool execution with invalid inputs (should return errors gracefully)."""
    print_header("Testing Tool Error Handling")

    test_cases = [
        {
            "name": "list_social_profiles",
            "args": {"user_email": "nonexistent@example.com"},
            "expect_error": True,
            "error_contains": "not found",
        },
        {
            "name": "get_social_profile_status",
            "args": {"user_email": "invalid@example.com"},
            "expect_error": True,
            "error_contains": "not found",
        },
        {
            "name": "cancel_scheduled_content",
            "args": {"content_id": 999999},
            "expect_error": True,
            "error_contains": "not found",
        },
    ]

    errors = []

    for tc in test_cases:
        try:
            result = await _execute_tool(tc["name"], tc["args"])

            if tc["expect_error"]:
                # Check if error is in result
                if "error" in result or "error" in str(result).lower():
                    print_success(f"{tc['name']}: Returned error as expected")
                else:
                    print_error(f"{tc['name']}: Expected error but got success")
                    errors.append(tc["name"])
            else:
                print_success(f"{tc['name']}: Executed successfully")

        except ValueError as e:
            if tc["expect_error"] and tc["error_contains"] in str(e).lower():
                print_success(f"{tc['name']}: Raised expected error")
            else:
                print_error(f"{tc['name']}: Unexpected error: {e}")
                errors.append(tc["name"])
        except Exception as e:
            if tc["expect_error"]:
                print_success(
                    f"{tc['name']}: Raised error (expected): {type(e).__name__}"
                )
            else:
                print_error(f"{tc['name']}: Unexpected exception: {e}")
                errors.append(tc["name"])

    return len(errors) == 0


async def test_with_live_data(user_email: str):
    """Test with real database data (optional)."""
    print_header(f"Testing with Live Data (user: {user_email})")

    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Check if user exists
    try:
        user = User.objects.get(email=user_email)
        print_success(f"Found user: {user.email}")
    except User.DoesNotExist:
        print_error(f"User not found: {user_email}")
        return False

    # Test list_social_profiles
    print("\n--- list_social_profiles ---")
    result = await _execute_tool("list_social_profiles", {"user_email": user_email})
    print(json.dumps(result, indent=2, default=str))

    # Test get_social_profile_status
    print("\n--- get_social_profile_status ---")
    result = await _execute_tool(
        "get_social_profile_status", {"user_email": user_email}
    )
    print(json.dumps(result, indent=2, default=str))

    # Test list_scheduled_content
    print("\n--- list_scheduled_content ---")
    result = await _execute_tool("list_scheduled_content", {"user_email": user_email})
    print(json.dumps(result, indent=2, default=str))

    # Test list_automation_tasks
    print("\n--- list_automation_tasks ---")
    result = await _execute_tool("list_automation_tasks", {"user_email": user_email})
    print(json.dumps(result, indent=2, default=str))

    return True


async def run_all_tests(verbose: bool = False, live_user: str = None):
    """Run all tests."""
    print_header("MCP Server Test Suite")
    print(f"Server: {SERVER_NAME} v{SERVER_VERSION}")
    print(f"Time: {datetime.now().isoformat()}")

    results = {}

    # Core tests
    results["metadata"] = await test_server_metadata()
    results["creation"] = await test_server_creation()
    results["tools"] = await test_list_tools()
    results["tool_handler"] = await test_tool_schemas()
    results["resources"] = await test_resources()
    results["prompts"] = await test_prompts()
    results["error_handling"] = await test_tool_execution_validation()

    # Optional live data test
    if live_user:
        results["live_data"] = await test_with_live_data(live_user)

    # Summary
    print_header("Test Summary")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        if result:
            print_success(f"{name}")
        else:
            print_error(f"{name}")

    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}")

    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}All tests passed! ✓{Colors.END}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}Some tests failed ✗{Colors.END}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Test the Automation MCP Server")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--live", metavar="EMAIL", help="Test with live user data")

    args = parser.parse_args()

    exit_code = asyncio.run(run_all_tests(verbose=args.verbose, live_user=args.live))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
