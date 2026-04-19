"""Tool bridge — publishes compressed tool-call notifications to Pusher.

Format on the wire (channel `thread-<thread_id>`, event `tool-call`):
    {"z": "<base64 gzipped JSON>"}
Decoded payload:
    {"thread_id": "...", "tool_call_id": "...", "name": "...", "args": {...}}

The Python code compresses with zlib; the browser decompresses with `pako.inflate`.
Best-effort: failures are logged and swallowed so they never break the graph.
"""
from __future__ import annotations
import base64
import json
import logging
import os
import zlib
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PUSHER_APP_ID = os.getenv("PUSHER_APP_ID", "")
_PUSHER_KEY = os.getenv("PUSHER_KEY", "")
_PUSHER_SECRET = os.getenv("PUSHER_SECRET", "")
_PUSHER_CLUSTER = os.getenv("PUSHER_CLUSTER", "eu")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not (_PUSHER_APP_ID and _PUSHER_KEY and _PUSHER_SECRET):
        logger.info("Pusher env not set — tool bridge disabled (dev mode).")
        return None
    try:
        import pusher  # type: ignore
    except ImportError:
        logger.warning("pusher package not installed — tool bridge disabled.")
        return None
    _client = pusher.Pusher(
        app_id=_PUSHER_APP_ID,
        key=_PUSHER_KEY,
        secret=_PUSHER_SECRET,
        cluster=_PUSHER_CLUSTER,
        ssl=True,
    )
    return _client


def _compress(payload: dict[str, Any]) -> dict[str, str]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    z = zlib.compress(raw, level=6)
    return {"z": base64.b64encode(z).decode("ascii")}


def publish_tool_call(thread_id: Optional[str], tool_call_id: str, name: str, args: dict) -> None:
    if not thread_id:
        return
    client = _get_client()
    if client is None:
        return
    try:
        body = _compress({
            "thread_id": thread_id,
            "tool_call_id": tool_call_id,
            "name": name,
            "args": args,
        })
        client.trigger(f"thread-{thread_id}", "tool-call", body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pusher publish failed: %s", exc)


def publish_activity(thread_id: Optional[str], activity: str) -> None:
    if not thread_id:
        return
    client = _get_client()
    if client is None:
        return
    try:
        body = _compress({"thread_id": thread_id, "activity": activity})
        client.trigger(f"thread-{thread_id}", "activity", body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pusher publish failed: %s", exc)
