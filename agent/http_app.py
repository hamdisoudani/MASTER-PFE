"""Custom HTTP routes mounted onto the LangGraph API server.

Registered via langgraph.json:

    "http": { "app": "./agent/http_app.py:app" }

Routes (all served at the deployment root, e.g. https://<svc>.railway.app):

    GET /graphs                     JSON index
    GET /graphs/{name}.png          PNG render (mermaid.ink fallback pygraphviz)
    GET /graphs/{name}.mmd          raw mermaid source
    GET /graphs/healthz             liveness probe

Graphs are imported lazily inside each handler so an import/compile failure
in one graph does not prevent the routes from registering at startup
(which is what caused the previous 404s on Railway).
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, Response

logger = logging.getLogger(__name__)

app = FastAPI(title="MASTER-PFE custom routes")

GRAPH_NAMES = ("syllabus_agent", "syllabus_agent_deep")


def _load_graph(name: str):
    if name == "syllabus_agent":
        from agent.graph import graph
        return graph
    if name == "syllabus_agent_deep":
        from agent.deep_graph import graph
        return graph
    return None


def _render_png(compiled) -> bytes | None:
    try:
        g = compiled.get_graph()
    except Exception as exc:
        logger.exception("get_graph() failed: %s", exc)
        return None
    for fn_name in ("draw_mermaid_png", "draw_png"):
        fn: Callable | None = getattr(g, fn_name, None)
        if fn is None:
            continue
        try:
            data = fn()
            if data:
                return data
        except Exception as exc:
            logger.warning("%s failed: %s", fn_name, exc)
    return None


def _render_mermaid(compiled) -> str | None:
    try:
        return compiled.get_graph().draw_mermaid()
    except Exception as exc:
        logger.exception("draw_mermaid() failed: %s", exc)
        return None


@app.get("/graphs/healthz")
async def healthz():
    return {"ok": True, "graphs": list(GRAPH_NAMES)}


@app.get("/graphs")
async def list_graphs():
    return {
        "graphs": [
            {
                "name": name,
                "png": f"/graphs/{name}.png",
                "mermaid": f"/graphs/{name}.mmd",
            }
            for name in GRAPH_NAMES
        ]
    }


@app.get("/graphs/{name}.png")
async def graph_png(name: str):
    try:
        compiled = _load_graph(name)
    except Exception as exc:
        logger.exception("failed to import graph %s: %s", name, exc)
        return JSONResponse(
            {"error": f"import failed for {name!r}: {exc.__class__.__name__}: {exc}"},
            status_code=500,
        )
    if compiled is None:
        return JSONResponse(
            {"error": f"unknown graph {name!r}", "available": list(GRAPH_NAMES)},
            status_code=404,
        )
    png = _render_png(compiled)
    if png is None:
        mmd = _render_mermaid(compiled) or ""
        return PlainTextResponse(
            "PNG rendering unavailable (mermaid.ink unreachable and pygraphviz missing). "
            "Mermaid source below.\n\n" + mmd,
            status_code=503,
        )
    return Response(png, media_type="image/png")


@app.get("/graphs/{name}.mmd")
async def graph_mmd(name: str):
    try:
        compiled = _load_graph(name)
    except Exception as exc:
        logger.exception("failed to import graph %s: %s", name, exc)
        return JSONResponse(
            {"error": f"import failed for {name!r}: {exc.__class__.__name__}: {exc}"},
            status_code=500,
        )
    if compiled is None:
        return JSONResponse(
            {"error": f"unknown graph {name!r}", "available": list(GRAPH_NAMES)},
            status_code=404,
        )
    mmd = _render_mermaid(compiled)
    if mmd is None:
        return JSONResponse({"error": "mermaid rendering failed"}, status_code=500)
    return PlainTextResponse(mmd, media_type="text/plain")
