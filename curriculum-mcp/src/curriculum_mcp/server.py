"""FastMCP server entrypoint.

Deployed to Railway as `mcp-curriculum` (streamable-http on :8080, path /mcp).
The agent connects via `langchain-mcp-adapters` (MultiServerMCPClient) which
opens short-lived streamable-http transports per tool invocation. To keep that
working across independent requests without a sticky mcp-session-id handshake,
we run FastMCP in **stateless_http** mode — otherwise the server responds
`421 Misdirected Request` whenever a POST arrives without a live session
(which is what we were seeing in the Railway logs).
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from .tools import register

load_dotenv()

# stateless_http=True  -> no per-session state; every POST is self-contained
# json_response=True   -> respond with a single JSON body instead of SSE stream
#                        (simpler for clients that don't hold the stream open)
mcp = FastMCP(
    "curriculum-mcp",
    stateless_http=True,
    json_response=True,
)
register(mcp)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
