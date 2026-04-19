# Railway Deployment Guide

Three services from this monorepo. Each uses its own Dockerfile — Railway's "Root Directory" selects which one.

| Service  | Root Directory | Dockerfile         | Internal port |
|----------|---------------:|--------------------|--------------:|
| Agent    | `agent`        | `agent/Dockerfile`    | `$PORT` (default `2024`) |
| Backend  | `backend`      | `backend/Dockerfile`  | `$PORT` (default `3001`) |
| Frontend | `frontend`     | `frontend/Dockerfile` | `$PORT` (default `3000`) |

Railway injects `$PORT` at runtime and the Dockerfiles honour it; all three bind `0.0.0.0`.

---

## 1. Create Railway project
[railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → `hamdisoudani/MASTER-PFE`.

Add **three services** from the same repo (see table below).

---

## 2. Agent (deploy first)

- **Root Directory**: `agent`
- Railway auto-picks `agent/railway.toml` → Dockerfile build.
- **Environment variables:**
  ```
  LLM_BASE_URL = https://integrate.api.nvidia.com/v1
  LLM_API_KEY  = nvapi-...
  LLM_MODEL    = mistralai/mistral-small-4-119b-2603
  ```
- Health check: `/ok` (LangGraph dev server).
- Expose public networking → note the URL (e.g. `https://agent-xxx.up.railway.app`).

---

## 3. Backend

- **Root Directory**: `backend`
- **Environment variables:**
  ```
  CORS_ORIGINS   = https://<frontend-domain>
  LANGGRAPH_URL  = https://<agent-domain>
  ```
- Health check: `/health`.
- Note the URL.

---

## 4. Frontend

- **Root Directory**: `frontend`
- **Build-time variables** (must be set in Railway → _Variables_ → _Build_, because they are baked into the static bundle):
  ```
  NEXT_PUBLIC_LANGGRAPH_URL = https://<agent-domain>
  NEXT_PUBLIC_API_BASE_URL  = https://<backend-domain>
  NEXT_PUBLIC_ASSISTANT_ID  = syllabus_agent
  NEXT_PUBLIC_PUSHER_KEY    = <optional>
  NEXT_PUBLIC_PUSHER_CLUSTER= <optional, e.g. eu>
  ```
- Expose public networking.

---

## Key Dockerfile details

### `agent/Dockerfile`
- `python:3.11-slim` + `pip install -r requirements.txt` (includes `langgraph-cli[inmem]`).
- Copies repo into `/app/agent/` and `langgraph.json` to `/app/`.
- `CMD` runs `langgraph dev --host 0.0.0.0 --port $PORT --no-browser --allow-blocking`.
- Exposes `/ok`, `/info`, `/threads`, `/runs`, `/assistants` (standard LangGraph API surface).

### `backend/Dockerfile`
- Two-stage (`builder` + `runner`), `node:20-alpine`.
- Installs dev deps for `nest build`, then reinstalls with `--omit=dev` in runner.
- Binds `0.0.0.0:$PORT`, defaults to `3001`.

### `frontend/Dockerfile`
- Three-stage: `deps` → `builder` → `runner`.
- Accepts `NEXT_PUBLIC_*` build args so `next build` inlines them.
- Uses `output: "standalone"` from `next.config.js`; runner only ships `.next/standalone` + `.next/static` + `public/`.
- Runs as non-root `nextjs` user.

---

## Local dev
```bash
docker compose up --build
# agent   → http://localhost:2024  (health: /ok)
# backend → http://localhost:3001  (health: /health)
# front   → http://localhost:3000
```

Or run each service natively — see `README.md`.
