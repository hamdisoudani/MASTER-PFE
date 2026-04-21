"""Graph visualization sidecar.

A standalone FastAPI service that imports the compiled LangGraph graphs
from ./agent and exposes them as PNG / Mermaid / JSON. Runs as its own
Railway service (or `docker compose` service) — completely independent
of the main `langgraph dev` server so a breakage in one does not affect
the other.

Routes:
    GET  /                      JSON index of available graphs
    GET  /healthz               liveness probe (no graph imports)
    GET  /graphs                JSON index (alias of /)
    GET  /graphs/{name}.png     PNG (mermaid.ink, then pygraphviz fallback)
    GET  /graphs/{name}.mmd     raw mermaid source
    GET  /graphs/{name}.json    node/edge JSON (graph.to_json())

Graphs are imported lazily so an import failure in one graph does NOT
take down the whole sidecar. Rendered PNGs are cached in-process for
`CACHE_TTL_SECONDS` (default 300).
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("graph-viz")

_HERE = Path(__file__).resolve().parent
_AGENT_DIR = Path(os.getenv("AGENT_SRC", _HERE.parent / "agent")).resolve()
if str(_AGENT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR.parent))
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

logger.info("graph-viz boot: AGENT_SRC=%s sys.path[0:3]=%s", _AGENT_DIR, sys.path[:3])

GRAPHS: dict[str, str] = {
    "syllabus_agent": "agent.graph:graph",
    "syllabus_agent_deep": "agent.deep_graph:graph",
}

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))
_cache: dict[str, tuple[float, bytes | str]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value):
    _cache[key] = (time.time(), value)


def _import_graph(spec: str):
    mod_path, _, attr = spec.partition(":")
    import importlib

    mod = importlib.import_module(mod_path)
    return getattr(mod, attr)


def _load(name: str):
    spec = GRAPHS.get(name)
    if spec is None:
        return None
    return _import_graph(spec)


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


def _render_json(compiled) -> dict[str, Any] | None:
    try:
        g = compiled.get_graph()
    except Exception as exc:
        logger.exception("get_graph() failed: %s", exc)
        return None
    for fn_name in ("to_json", "to_dict"):
        fn = getattr(g, fn_name, None)
        if fn is None:
            continue
        try:
            out = fn()
            if isinstance(out, dict):
                return out
        except Exception as exc:
            logger.warning("%s failed: %s", fn_name, exc)
    try:
        nodes = [getattr(n, "id", str(n)) for n in getattr(g, "nodes", [])]
        edges = [
            {"source": getattr(e, "source", None), "target": getattr(e, "target", None)}
            for e in getattr(g, "edges", [])
        ]
        return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        logger.exception("manual graph json failed: %s", exc)
        return None


app = FastAPI(
    title="MASTER-PFE Graph Visualization Sidecar",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "graphs": list(GRAPHS.keys()), "agent_src": str(_AGENT_DIR)}


@app.get("/")
@app.get("/graphs")
async def index():
    return {
        "graphs": [
            {
                "name": name,
                "png": f"/graphs/{name}.png",
                "mermaid": f"/graphs/{name}.mmd",
                "json": f"/graphs/{name}.json",
            }
            for name in GRAPHS
        ]
    }


def _load_or_404(name: str):
    if name not in GRAPHS:
        raise HTTPException(status_code=404, detail={"error": f"unknown graph {name!r}", "available": list(GRAPHS.keys())})
    try:
        return _load(name)
    except Exception as exc:
        logger.exception("import failed for %s", name)
        raise HTTPException(status_code=500, detail={"error": f"import failed: {exc.__class__.__name__}: {exc}"})


@app.get("/graphs/{name}.png")
async def graph_png(name: str):
    cached = _cache_get(f"png:{name}")
    if isinstance(cached, bytes):
        return Response(cached, media_type="image/png")
    compiled = _load_or_404(name)
    png = _render_png(compiled)
    if png is None:
        mmd = _render_mermaid(compiled) or ""
        return PlainTextResponse(
            "PNG rendering unavailable (mermaid.ink unreachable and pygraphviz missing). "
            "Mermaid source below.\n\n" + mmd,
            status_code=503,
        )
    _cache_put(f"png:{name}", png)
    return Response(png, media_type="image/png")


@app.get("/graphs/{name}.mmd")
async def graph_mmd(name: str):
    cached = _cache_get(f"mmd:{name}")
    if isinstance(cached, str):
        return PlainTextResponse(cached, media_type="text/plain")
    compiled = _load_or_404(name)
    mmd = _render_mermaid(compiled)
    if mmd is None:
        raise HTTPException(status_code=500, detail={"error": "mermaid rendering failed"})
    _cache_put(f"mmd:{name}", mmd)
    return PlainTextResponse(mmd, media_type="text/plain")


@app.get("/graphs/{name}.json")
async def graph_json(name: str):
    compiled = _load_or_404(name)
    data = _render_json(compiled)
    if data is None:
        raise HTTPException(status_code=500, detail={"error": "json rendering failed"})
    return JSONResponse(data)


logger.info("graph-viz ready: %s", list(GRAPHS.keys()))
