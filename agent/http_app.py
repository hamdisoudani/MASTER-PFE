"""Custom HTTP routes mounted onto the LangGraph API server.

Exposes PNG renderings of the two compiled graphs so you can eyeball the
topology from a browser:

    GET /graphs/syllabus_agent.png
    GET /graphs/syllabus_agent_deep.png
    GET /graphs/{name}.mmd          # raw mermaid source (no graphviz needed)
    GET /graphs                     # JSON index

Wired via langgraph.json:
    "http": { "app": "./agent/http_app.py:app" }

Rendering order for PNG:
  1. graph.get_graph().draw_mermaid_png()         (uses mermaid.ink, no deps)
  2. graph.get_graph().draw_png()                 (needs pygraphviz)
  3. fallback -> 503 with mermaid source in body
"""
from __future__ import annotations

import logging
from typing import Callable

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from agent.graph import graph as syllabus_graph
from agent.deep_graph import graph as syllabus_deep_graph

logger = logging.getLogger(__name__)

GRAPHS: dict[str, object] = {
    "syllabus_agent": syllabus_graph,
    "syllabus_agent_deep": syllabus_deep_graph,
}


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


async def list_graphs(request):
    return JSONResponse(
        {
            "graphs": [
                {
                    "name": name,
                    "png": f"/graphs/{name}.png",
                    "mermaid": f"/graphs/{name}.mmd",
                }
                for name in GRAPHS
            ]
        }
    )


async def graph_png(request):
    name = request.path_params["name"]
    compiled = GRAPHS.get(name)
    if compiled is None:
        return JSONResponse({"error": f"unknown graph {name!r}", "available": list(GRAPHS)}, status_code=404)
    png = _render_png(compiled)
    if png is None:
        mmd = _render_mermaid(compiled) or ""
        return PlainTextResponse(
            "PNG rendering unavailable (mermaid.ink unreachable and pygraphviz missing). "
            "Mermaid source below.\n\n" + mmd,
            status_code=503,
            media_type="text/plain",
        )
    return Response(png, media_type="image/png")


async def graph_mmd(request):
    name = request.path_params["name"]
    compiled = GRAPHS.get(name)
    if compiled is None:
        return JSONResponse({"error": f"unknown graph {name!r}", "available": list(GRAPHS)}, status_code=404)
    mmd = _render_mermaid(compiled)
    if mmd is None:
        return JSONResponse({"error": "mermaid rendering failed"}, status_code=500)
    return PlainTextResponse(mmd, media_type="text/plain")


app = Starlette(
    debug=False,
    routes=[
        Route("/graphs", list_graphs, methods=["GET"]),
        Route("/graphs/{name}.png", graph_png, methods=["GET"]),
        Route("/graphs/{name}.mmd", graph_mmd, methods=["GET"]),
    ],
)
