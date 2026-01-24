#!/bin/bash
set -e
echo "=== Starting MCP Server ==="
echo "Transport: ${MCP_TRANSPORT}"
echo "Host: ${MCP_HOST}"
echo "Port: ${MCP_PORT}"

# Run MCP server with configured transport
exec python run_mcp_server.py \
    --transport "${MCP_TRANSPORT}" \
    --host "${MCP_HOST}" \
    --port "${MCP_PORT}"
