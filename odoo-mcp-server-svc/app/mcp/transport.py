"""MCP transport layer — Streamable HTTP and SSE handlers.

Provides HTTP endpoints for MCP protocol communication:
- POST /mcp — Streamable HTTP transport (JSON-RPC over HTTP)
- GET /mcp/sse — Server-Sent Events transport
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

mcp_router = APIRouter()

# Set by lifespan
mcp_server: Optional[Any] = None


@mcp_router.post("/mcp")
async def mcp_streamable_http(request: Request) -> Response:
    """Streamable HTTP transport for MCP protocol.

    Accepts JSON-RPC requests and returns JSON-RPC responses.
    """
    if mcp_server is None:
        return Response(
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": "MCP server not initialized",
                    },
                    "id": None,
                }
            ),
            media_type="application/json",
            status_code=503,
        )

    try:
        body = await request.json()
        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id")

        result = await _dispatch_mcp_method(method, params)

        return Response(
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": request_id,
                }
            ),
            media_type="application/json",
        )
    except Exception as exc:
        logger.error("MCP request failed: %s", exc)
        return Response(
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": str(exc),
                    },
                    "id": body.get("id") if "body" in dir() else None,
                }
            ),
            media_type="application/json",
            status_code=500,
        )


@mcp_router.get("/mcp/sse")
async def mcp_sse(request: Request) -> StreamingResponse:
    """Server-Sent Events transport for MCP protocol."""

    async def event_generator():
        """Generate SSE events."""
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connection', 'status': 'connected'})}\n\n"

        # Keep connection alive
        import asyncio

        try:
            while True:
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _dispatch_mcp_method(method: str, params: dict[str, Any]) -> Any:
    """Dispatch an MCP JSON-RPC method to the appropriate handler."""
    if method == "tools/list":
        tools = await mcp_server.list_tools()
        return {"tools": [t.model_dump() for t in tools]}
    elif method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await mcp_server.call_tool(name, arguments)
        return {"content": [c.model_dump() for c in result]}
    elif method == "resources/list":
        resources = await mcp_server.list_resources()
        return {"resources": [r.model_dump() for r in resources]}
    elif method == "resources/read":
        uri = params.get("uri", "")
        content = await mcp_server.read_resource(uri)
        return {"contents": [{"uri": uri, "text": content}]}
    elif method == "prompts/list":
        prompts = await mcp_server.list_prompts()
        return {"prompts": [p.model_dump() for p in prompts]}
    elif method == "prompts/get":
        name = params.get("name", "")
        arguments = params.get("arguments")
        result = await mcp_server.get_prompt(name, arguments)
        return result.model_dump()
    elif method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": "odoo-mcp-server",
                "version": "1.0.0",
            },
        }
    else:
        raise ValueError(f"Unknown MCP method: {method}")
