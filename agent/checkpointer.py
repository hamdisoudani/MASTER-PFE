"""Optional durable checkpointer wiring.

When running under LangGraph Platform (`langgraph dev`, LangGraph Cloud,
Railway with the langgraph-cli), the platform injects its own checkpointer
and you MUST NOT pass one at graph compile time. For self-hosted / test
runs set `AGENT_PG_CHECKPOINTER=1` (and DATABASE_URL) to attach
PostgresSaver explicitly.

Use:
    from agent.checkpointer import get_checkpointer
    cp = get_checkpointer()   # None when not enabled
    graph = builder.compile(checkpointer=cp) if cp else builder.compile()
"""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_checkpointer():  # type: ignore[no-untyped-def]
    if os.getenv("AGENT_PG_CHECKPOINTER", "").lower() not in ("1", "true", "yes"):
        return None
    url = os.getenv("DATABASE_URL", "")
    if not url:
        logger.warning("AGENT_PG_CHECKPOINTER=1 but DATABASE_URL is unset; skipping.")
        return None
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("langgraph-checkpoint-postgres unavailable (%s); skipping.", exc)
        return None
    try:
        saver = PostgresSaver.from_conn_string(url)  # type: ignore[attr-defined]
        try:
            saver.setup()
        except Exception:
            pass
        logger.info("PostgresSaver checkpointer attached.")
        return saver
    except Exception as exc:  # noqa: BLE001
        logger.warning("PostgresSaver init failed (%s); running without durable state.", exc)
        return None
