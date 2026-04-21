"""FastMCP server entrypoint.

Deployed to Railway as `mcp-curriculum` (streamable-http on :8080, path /mcp).

Production notes
----------------
1. **DNS rebinding protection** — FastMCP enables
   `TransportSecuritySettings.enable_dns_rebinding_protection=True` with an
   empty `allowed_hosts` list by default. The MCP SDK's `_validate_host`
   only supports exact matches and `:port` wildcards — NOT a bare "*" — so
   any Host header from Railway (e.g. `mcp-curriculum.up.railway.app`) is
   rejected with HTTP 421 "Invalid Host header" before the session manager
   runs. We disable the check by default (the server is still protected
   by the optional `CURRICULUM_MCP_TOKEN` bearer and Supabase RLS). If you
   want to re-enable it, set `MCP_ALLOWED_HOSTS` to a comma-separated list
   of exact hostnames, and optionally `MCP_ALLOWED_ORIGINS`.

2. **Stateless streamable-http** — `langchain-mcp-adapters` opens a fresh
   transport per tool call and does not pin `mcp-session-id`. Running in
   `stateless_http=True` + `json_response=True` makes every POST
   self-contained.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from .tools import register
from .tools_activities import register_activities

load_dotenv()


def _transport_security() -> TransportSecuritySettings:
    raw_hosts = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    raw_origins = os.environ.get("MCP_ALLOWED_ORIGINS", "").strip()
    allowed_hosts = [h.strip() for h in raw_hosts.split(",") if h.strip()]
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    enable = bool(allowed_hosts)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=enable,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


mcp = FastMCP(
    "curriculum-mcp",
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security(),
)
register(mcp)
register_activities(mcp)


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
