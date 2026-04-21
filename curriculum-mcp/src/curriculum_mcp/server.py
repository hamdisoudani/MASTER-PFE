"""FastMCP server entrypoint.

Deployed to Railway as `mcp-curriculum` (streamable-http on :8080, path /mcp).

Two production-only concerns that bite FastMCP here:

1. **DNS rebinding protection (HTTP 421 "Invalid Host header")** — FastMCP
   enables `TransportSecuritySettings.enable_dns_rebinding_protection=True`
   with an empty `allowed_hosts` list by default, which only permits
   `127.0.0.1` / `localhost`. On Railway the Host header is
   `mcp-curriculum.up.railway.app` (or any custom domain), so every POST
   /mcp was being rejected with 421 *before* reaching the session
   manager. We relax the check to "any host/origin" for the streamable
   transport (the server is still protected by Supabase RLS + the optional
   CURRICULUM_MCP_TOKEN bearer).

2. **Short-lived clients (HTTP 421 "Session not found")** — `langchain-mcp-adapters`
   opens a fresh streamable-http transport per tool call and does not pin
   an `mcp-session-id`. Running FastMCP in `stateless_http=True` +
   `json_response=True` means each POST is self-contained.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from .tools import register

load_dotenv()


def _transport_security() -> TransportSecuritySettings:
    # Allow any Host/Origin by default; narrow via env if you want to pin
    # the Railway domain(s). Comma-separated.
    hosts = os.environ.get("MCP_ALLOWED_HOSTS", "*").split(",")
    origins = os.environ.get("MCP_ALLOWED_ORIGINS", "*").split(",")
    hosts = [h.strip() for h in hosts if h.strip()]
    origins = [o.strip() for o in origins if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts or ["*"],
        allowed_origins=origins or ["*"],
    )


mcp = FastMCP(
    "curriculum-mcp",
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security(),
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
