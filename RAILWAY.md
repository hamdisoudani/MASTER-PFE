# Railway Deployment Guide

## Architecture

Deploy **3 Railway services** from this monorepo — each maps to one subdirectory:

| Service | Root Directory | Auto-detected |
|---------|---------------|---------------|
| **Agent** (Python FastAPI) | `agent/` | Python via `nixpacks.toml` |
| **Backend** (NestJS) | `backend/` | Node.js via `railway.toml` |
| **Frontend** (Next.js) | `frontend/` | Node.js via `railway.toml` |

---

## Step-by-Step Setup

### 1. Create Railway Project
[railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → `hamdisoudani/MASTER-PFE`

---

### 2. Agent Service (deploy first)
- **Add Service** → GitHub → same repo → **Root Directory** = `agent`
- Railway builds with `nixpacks.toml` (Python 3.12, pip install)
- **Environment Variables:**
  ```
  LLM_BASE_URL   = https://integrate.api.nvidia.com/v1
  LLM_API_KEY    = nvapi-your-key-here
  LLM_MODEL      = mistralai/mistral-small-4-119b-2603
  ```
- After deploy, copy the **Public URL** (e.g. `https://agent-xxx.railway.app`)

---

### 3. Backend Service
- **Add Service** → GitHub → same repo → **Root Directory** = `backend`
- **Environment Variables:**
  ```
  AGENT_URL      = https://agent-xxx.railway.app/copilotkit
  CORS_ORIGINS   = *
  ```
- After deploy, copy the **Public URL** (e.g. `https://backend-xxx.railway.app`)

---

### 4. Frontend Service
- **Add Service** → GitHub → same repo → **Root Directory** = `frontend`
- **Environment Variables:**
  ```
  NEXT_PUBLIC_RUNTIME_URL = https://backend-xxx.railway.app/copilotkit
  ```
- After deploy → open the frontend URL to see the chat UI

---

## Zero-config Railway features used
- Each `railway.toml` defines `buildCommand` + `startCommand`
- `$PORT` is injected automatically by Railway
- `output: standalone` in `next.config.js` = minimal Docker image for Next.js
- `healthcheckPath` ensures Railway waits for service readiness before routing traffic

---

## Local Development
```bash
# Agent
cd agent && pip install -r requirements.txt
cp .env.example .env   # fill in LLM_API_KEY
uvicorn agent.main:app --port 8000

# Backend (new terminal)
cd backend && npm install
AGENT_URL=http://localhost:8000/copilotkit npm start

# Frontend (new terminal)
cd frontend && npm install
NEXT_PUBLIC_RUNTIME_URL=http://localhost:3001/copilotkit npm run dev
```

Or all at once:
```bash
docker compose up --build
```
