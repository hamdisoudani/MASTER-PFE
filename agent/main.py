"""
FastAPI entry point for the LangGraph AG-UI agent.

Exposes the agent via the AG-UI protocol at POST /copilotkit
so the NestJS CopilotRuntime (HttpAgent) can route messages to it.

Run with:
    uvicorn agent.main:app --host 0.0.0.0 --port 8000
"""
import os
import json as _json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ag_ui_langgraph.endpoint import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent

from agent.checkpointer import get_checkpointer, close_checkpointer
from agent.graph import build_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety patch for ag_ui_langgraph bug:
# utils.py does json.loads(tc.function.arguments) guarded only by truthiness,
# but a whitespace-only string passes the guard and then raises JSONDecodeError.
# ---------------------------------------------------------------------------
_orig_json_loads = _json.loads

def _safe_json_loads(s, *args, **kwargs):
    if isinstance(s, (str, bytes, bytearray)) and not (s.strip() if isinstance(s, str) else s.strip()):
        return {}
    return _orig_json_loads(s, *args, **kwargs)

_json.loads = _safe_json_loads
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    checkpointer = await get_checkpointer()
    graph = build_graph(checkpointer)

    agent = LangGraphAGUIAgent(
        name="default",
        description="A general-purpose AI assistant powered by NVIDIA NIM.",
        graph=graph,
    )

    # Register the AG-UI endpoint — same pattern as the original working code
    add_langgraph_fastapi_endpoint(app, agent, "/copilotkit")
    logger.info("Agent ready.")

    yield

    # --- shutdown ---
    await close_checkpointer()


app = FastAPI(
    title="Master PFE — LangGraph Agent",
    description="AG-UI agent powered by LangGraph + NVIDIA NIM",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "agent": "default",
        "llm": os.getenv("LLM_MODEL", "unknown"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "agent.main:app",
        host=os.getenv("AGENT_HOST", "0.0.0.0"),
        port=int(os.getenv("AGENT_PORT", "8000")),
        reload=False,
    )
