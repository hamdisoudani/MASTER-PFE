"""FastMCP server entrypoint."""
from __future__ import annotations
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from .tools import register

load_dotenv()

mcp = FastMCP("curriculum-mcp")
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
