"""
FastAPI entry point for the LangGraph AG-UI agent.

Exposes the agent via the AG-UI protocol at POST /copilotkit
so the NestJS CopilotRuntime (LangGraphHttpAgent) can route messages to it.

Agent name 'syllabus_agent' must match:
  - backend copilot.controller.ts  → agents: { syllabus_agent: ... }
  - frontend layout.tsx            → <CopilotKit agent='syllabus_agent'>

Run with:
    uvicorn agent.main:app --host 0.0.0.0 --port 8000
"""
import os
import sys
import types

os.environ.setdefault("UVICORN_HOST", "0.0.0.0")
if "PORT" in os.environ:
    os.environ["UVICORN_PORT"] = os.environ["PORT"]

for _m in [k for k in list(sys.modules) if "opentelemetry" in k]:
    del sys.modules[_m]

for _name, _attrs in [
    ("opentelemetry", {}),
    ("opentelemetry.context", {
        "attach": lambda t: None,
        "detach": lambda t: None,
        "get_current": lambda: {},
    }),
    ("opentelemetry.sdk", {}),
    ("opentelemetry.sdk.trace", {
        "TracerProvider": type("TracerProvider", (), {}),
    }),
]:
    _m = types.ModuleType(_name)
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
    sys.modules[_name] = _m

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ag_ui_langgraph.endpoint import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from .graph import graph

app = FastAPI(
    title="Master PFE — Syllabus AI Agent",
    description="AG-UI agent powered by LangGraph + NVIDIA NIM",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = LangGraphAGUIAgent(
    name="syllabus_agent",
    description="Course syllabus builder powered by NVIDIA NIM. Creates structured syllabi with chapters and rich BlockNote lesson content.",
    graph=graph,
    # Belt-and-suspenders: also set recursion_limit here in case the library
    # merges this config into the graph run config.
    config={"recursion_limit": 150},
)

add_langgraph_fastapi_endpoint(app, agent, "/copilotkit")

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
        host=os.getenv("UVICORN_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
