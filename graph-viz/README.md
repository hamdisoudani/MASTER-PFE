# graph-viz — LangGraph Visualization Sidecar

A tiny FastAPI service that imports the compiled graphs from `../agent`
and serves them as PNG / Mermaid / JSON. Runs as a **separate** process
from the main `langgraph dev` server so a crash or import issue in the
sidecar never affects the live agent, and vice versa.

## Why a sidecar?

We originally mounted custom `/graphs/*` routes inside the agent service
via `langgraph.json`'s `http.app` hook. That integration proved
unreliable across `langgraph-cli` versions, so we moved the visualization
surface into its own service — independent lifecycle, independent
deploy, independent logs.

## Endpoints

| Route                         | Purpose                                  |
|-------------------------------|------------------------------------------|
| `GET /healthz`                | Liveness probe (no graph imports)        |
| `GET /` or `/graphs`          | JSON index of available graphs           |
| `GET /graphs/{name}.png`      | PNG render (mermaid.ink, then pygraphviz)|
| `GET /graphs/{name}.mmd`      | Raw Mermaid source                       |
| `GET /graphs/{name}.json`     | Node/edge JSON (`graph.to_json()`)       |
| `GET /docs`                   | OpenAPI / Swagger UI                     |

Graphs exposed today: `syllabus_agent`, `syllabus_agent_deep`.

## Local run

```bash
# from repo root
docker build -f graph-viz/Dockerfile -t master-pfe-graph-viz .
docker run --rm -p 8088:8088 --env-file agent/.env master-pfe-graph-viz

# or without docker, from repo root:
pip install -r graph-viz/requirements.txt
PYTHONPATH="$PWD" uvicorn app:app --app-dir graph-viz --port 8088
```

Smoke test:

```bash
curl -s http://localhost:8088/healthz
curl -s http://localhost:8088/graphs | jq
curl -s http://localhost:8088/graphs/syllabus_agent.mmd
curl -so /tmp/g.png http://localhost:8088/graphs/syllabus_agent.png
```

## Railway deploy

Add a **fourth service** to the existing Railway project:

| Field              | Value                                  |
|--------------------|----------------------------------------|
| Root Directory     | `/` *(repo root — NOT `graph-viz`)*    |
| Dockerfile Path    | `graph-viz/Dockerfile`                 |
| Health Check Path  | `/healthz`                             |
| Env vars           | whatever `./agent` needs at import time (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, Supabase keys, etc.) |

Railway injects `$PORT`; the Dockerfile already honors it.

Expose public networking and note the URL — the frontend can then embed
the PNG via `<img src="https://graph-viz-xxx.up.railway.app/graphs/syllabus_agent_deep.png">`.

## docker-compose

Already wired under `graph-viz` in `docker-compose.yml`. `docker compose
up graph-viz` brings it up on `localhost:8088`.

## Caching

Rendered PNGs and Mermaid sources are cached in-process for
`CACHE_TTL_SECONDS` (default 300). Restart the service to bust the cache
after a graph topology change.

## Env vars

| Var                  | Default                       | Notes                               |
|----------------------|-------------------------------|-------------------------------------|
| `PORT`               | `8088`                        | bind port                           |
| `AGENT_SRC`          | `/app/agent` (in container)   | directory of the `agent` package    |
| `CORS_ORIGINS`       | `*`                           | comma-separated origins             |
| `CACHE_TTL_SECONDS`  | `300`                         | PNG/Mermaid cache TTL               |
| `LOG_LEVEL`          | `INFO`                        | standard Python logging level       |

Plus every env var the `agent` package needs at import time (LLM keys,
Supabase keys, MCP endpoints).
