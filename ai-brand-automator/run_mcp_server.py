#!/usr/bin/env python
"""
Standalone runner script for the Automation MCP Server.

This script can be used to run the MCP server independently of the Django
REST API. It supports both stdio and SSE transports.

Usage:
    # Run with stdio transport (for MCP clients like Claude Desktop)
    python run_mcp_server.py

    # Run with SSE transport (for web clients)
    python run_mcp_server.py --transport sse --port 8080

    # Run with debug logging
    python run_mcp_server.py --debug
"""

import argparse
import asyncio
import logging
import os
import sys

# Add the project root to the path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    parser = argparse.ArgumentParser(
        description="Run the Automation MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with stdio (default, for Claude Desktop)
    python run_mcp_server.py

    # Run with SSE transport for web clients
    python run_mcp_server.py --transport sse --port 8080

    # Run with debug logging
    python run_mcp_server.py --debug
        """,
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport type (default: stdio)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)",
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="Host for SSE transport (default: localhost)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    # Setup Django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

    import django

    django.setup()

    logger.info(f"Starting Automation MCP Server with {args.transport} transport")

    if args.transport == "stdio":
        from automation.mcp_server import run_mcp_server

        asyncio.run(run_mcp_server())

    elif args.transport == "sse":
        from automation.mcp_server import create_mcp_server
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route
        import uvicorn

        server = create_mcp_server()
        sse = SseServerTransport("/messages")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        async def handle_messages(request):
            await sse.handle_post_message(request.scope, request.receive, request._send)

        app = Starlette(
            debug=args.debug,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Route("/messages", endpoint=handle_messages, methods=["POST"]),
            ],
        )

        logger.info(f"SSE server listening on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
