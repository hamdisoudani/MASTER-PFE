"""
FastAPI entry point for the LangGraph AG-UI agent.

Exposes the agent via the AG-UI protocol at POST /copilotkit
so the NestJS CopilotRuntime (LangGraphHttpAgent) can route messages to it.

Agent name 'syllabus_agent' must match:
  - backend copilot.controller.ts  -> agents: { syllabus_agent: ... }
  - frontend page.tsx              -> <CopilotKit agent='syllabus_agent'>

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
    checkpointer = await get_checkpointer()
    graph = build_graph(checkpointer)

    # Only set recursion_limit — AG-UI / CopilotKit handle tool dispatch
    # for both frontend and backend tools automatically.
    agui_config = {"recursion_limit": 150}

    agent = LangGraphAGUIAgent(
        name="syllabus_agent",
        description="Course syllabus builder powered by NVIDIA NIM. Creates structured syllabi with chapters and rich BlockNote lesson content.",
        graph=graph,
        config=agui_config,
    )

    add_langgraph_fastapi_endpoint(app, agent, "/copilotkit")
    logger.info("Agent ready.")

    yield

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
        "agent": "syllabus_agent",
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
