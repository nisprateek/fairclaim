"""Shared MCP connection for agents that need the CRA KB toolset."""

import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Resolve the src-layout root so `-m fairclaim.backend.mcp_server.server`
# works from an installed package or local checkout.
SRC_DIR = Path(__file__).resolve().parents[2]

# One shared stateless stdio toolset for all sequential specialist agents.
CRA_TOOLSET = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "fairclaim.backend.mcp_server.server"],
            cwd=str(SRC_DIR),
        ),
        timeout=10.0,
    ),
)
