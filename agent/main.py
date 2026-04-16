"""
FastAPI entry-point for the LangGraph syllabus agent.

Key design decisions
---------------------
1.  Postgres checkpoint (Supabase) - state is persisted server-side so that
    subsequent messages in the same thread are resumed from the checkpoint
    rather than re-parsing the full conversation history.  This also fixes
    the ag_ui JSONDecodeError that fires when tool-call arguments come back
    as an empty string on the second turn.

2.  Safe json.loads patch - belts-and-suspenders guard for the ag_ui library
    bug where tc.function.arguments can be '' (empty string) and the
    library does json.loads(...) without guarding against that.
"""

import json as _json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from copilotkit import CopilotKitRemoteEndpoint
from copilotkit.langgraph_agui_agent import LangGraphAGUIAgent

from agent.checkpointer import get_checkpointer, close_checkpointer
from agent.graph import build_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Monkey-patch: fix ag_ui bug where empty tool-call arguments crash json.loads
# ag_ui_langgraph/utils.py does:
#   json.loads(tc.function.arguments) if ... and tc.function.arguments else {}
# The guard is `if tc.function.arguments` which is False for None/empty string
# but True for a whitespace-only string like " ".  We patch json.loads so that
# any all-whitespace / empty input returns {} instead of raising JSONDecodeError.
_original_json_loads = _json.loads


def _safe_json_loads(s, *args, **kwargs):
    if isinstance(s, str) and not s.strip():
        return {}
    if isinstance(s, (bytes, bytearray)) and not s.strip():
        return {}
    return _original_json_loads(s, *args, **kwargs)


_json.loads = _safe_json_loads


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start-up: init DB pool + compile graph.  Shut-down: close pool."""
    checkpointer = await get_checkpointer()
    graph = build_graph(checkpointer)

    sdk = CopilotKitRemoteEndpoint(
        agents=[
            LangGraphAGUIAgent(
                name="syllabus_agent",
                description=(
                    "AI agent that builds detailed, research-backed course "
                    "syllabi using web search and scraping tools."
                ),
                graph=graph,
                config={"recursion_limit": 150},
            )
        ]
    )
    app.state.sdk = sdk
    logger.info("Agent ready.")
    yield
    await close_checkpointer()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/copilotkit")
async def copilotkit_endpoint(request: Request):
    return await app.state.sdk.handle_request(request)
