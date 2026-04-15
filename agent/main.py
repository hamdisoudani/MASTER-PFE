"""
FastAPI entry point for the LangGraph CopilotKit agent.

The agent exposes the AG-UI protocol via CopilotKit's Python SDK so that
the NestJS CopilotRuntime (or any AG-UI-compatible runtime) can route
messages to it.

Run with:
    uvicorn agent.main:app --reload --port 8000
"""
import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from copilotkit import CopilotKitRemoteEndpoint
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from .graph import graph

app = FastAPI(
    title="Master PFE — LangGraph Agent",
    description="CopilotKit-compatible AG-UI agent powered by LangGraph",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sdk = CopilotKitRemoteEndpoint(
    agents=[
        LangGraphAGUIAgent(
            name="default",
            description=(
                "A general-purpose AI assistant that can chat, plan, "
                "and use frontend tools."
            ),
            graph=graph,
        )
    ]
)

add_fastapi_endpoint(app, sdk, "/copilotkit")


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent.main:app",
        host=os.getenv("AGENT_HOST", "0.0.0.0"),
        port=int(os.getenv("AGENT_PORT", "8000")),
        reload=True,
    )
