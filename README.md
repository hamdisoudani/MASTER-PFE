# Master PFE — CopilotKit v2 + LangGraph + NestJS + Next.js

> **Full-stack AI copilot** powered by LangGraph (Python), NestJS (gateway), Next.js (UI), and NVIDIA NIM as the LLM provider.

---

## ⚠️ Read SESSION_NOTES.md First

Before making any changes, read **[SESSION_NOTES.md](./SESSION_NOTES.md)**.
It contains strict rules (agent name sync, single CopilotKit provider, hardcoded backend URL) that were learned from real bugs. Skipping it will reproduce the same broken states.

---

## Architecture

```
Browser
  │ HTTP :3000
  ▼
Next.js (CopilotKit React hooks)
  │ POST /copilotkit :3001
  ▼
NestJS — CopilotRuntime + HttpAgent
  │ POST /copilotkit :8000 (AG-UI SSE)
  ▼
FastAPI — LangGraphAGUIAgent
  │ invoke LangGraph
  ▼
NVIDIA NIM (mistralai/mistral-small-4-119b-2603)
  │ token stream
  ▼
AG-UI SSE → NestJS → Next.js (real-time rendering)
```

## Quick Start

```bash
# 1. Configure env files
cp agent/.env.example     agent/.env      # fill LLM_API_KEY
cp backend/.env.example   backend/.env
cp frontend/.env.example  frontend/.env.local

# 2. Start all services
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend  | http://localhost:3001 |
| Agent    | http://localhost:8000 |
| Health   | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |

## Local Dev (without Docker)

```bash
# Agent
cd agent && pip install -r requirements.txt
uvicorn agent.main:app --reload --port 8000

# Backend
cd backend && npm install && npm run start:dev

# Frontend
cd frontend && npm install && npm run dev
```

## Cloudflare Tunnel (public HTTPS)

```bash
bash cloudflare-tunnel.sh
# Prints three trycloudflare.com URLs
```

## Environment Variables

### agent/.env
| Variable | Default |
|----------|---------|
| `LLM_API_KEY` | — |
| `LLM_MODEL` | `mistralai/mistral-small-4-119b-2603` |
| `LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `AGENT_PORT` | `8000` |

### backend/.env
| Variable | Default |
|----------|---------|
| `AGENT_URL` | `http://localhost:8000/copilotkit` |
| `PORT` | `3001` |
| `CORS_ORIGINS` | `http://localhost:3000` |

### frontend/.env.local
| Variable | Default |
|----------|---------|
| `NEXT_PUBLIC_RUNTIME_URL` | `http://localhost:3001/copilotkit` |

## Key Technical Decisions

**Why `add_langgraph_fastapi_endpoint` instead of `CopilotKitRemoteEndpoint`?**

CopilotKit v2 uses the AG-UI protocol. `LangGraphAGUIAgent` (from the copilotkit Python SDK) extends `ag_ui_langgraph.LangGraphAgent` and must be mounted via `add_langgraph_fastapi_endpoint`. The old `CopilotKitRemoteEndpoint` path calls `.execute()` which is not implemented on `LangGraphAGUIAgent`.

**NVIDIA NIM as LLM**

Uses `langchain_openai.ChatOpenAI` with `base_url=https://integrate.api.nvidia.com/v1` — swap any NVIDIA-hosted model by changing `LLM_MODEL` in `agent/.env`.

## Project Structure

```
.
├── agent/              # Python FastAPI + LangGraph (port 8000)
├── backend/            # NestJS CopilotKit Runtime (port 3001)
├── frontend/           # Next.js UI (port 3000)
├── docker-compose.yml
├── cloudflare-tunnel.sh
├── SESSION_NOTES.md    # ← READ THIS FIRST before any session
└── README.md
```

## License

MIT
