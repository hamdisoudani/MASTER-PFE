# SESSION NOTES — Master PFE

> **Last updated**: 2026-04-15  
> **Purpose**: Document everything done so far and what remains for the next coding session.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Tech Stack & Versions](#tech-stack--versions)
4. [What We've Done](#what-weve-done)
5. [Current File Structure](#current-file-structure)
6. [Environment Variables](#environment-variables)
7. [How to Run (Daytona VM)](#how-to-run-daytona-vm)
8. [Known Issues & Fixes Applied](#known-issues--fixes-applied)
9. [Screenshots](#screenshots)
10. [What's Left To Do](#whats-left-to-do)

---

## Project Overview

A **3-service AI Copilot application** that uses:
- A **Next.js frontend** with CopilotKit UI components for the chat interface
- A **NestJS backend** that proxies CopilotKit runtime requests to the agent
- A **Python (LangGraph) agent** that handles AI reasoning via NVIDIA NIM (Mistral model)

The user interacts with the chat UI → frontend sends requests to backend `/copilotkit` → backend forwards to the Python agent → agent calls NVIDIA NIM LLM → response streams back.

---

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Next.js Frontend  │────▶│   NestJS Backend     │────▶│  Python Agent       │
│   (Port 3000)       │     │   (Port 3001)        │     │  (Port 8000)        │
│                     │     │                      │     │                     │
│ • CopilotKit React  │     │ • /copilotkit proxy  │     │ • LangGraph graph   │
│ • CopilotChat UI    │     │ • CORS enabled       │     │ • CopilotKit SDK    │
│ • Tailwind CSS      │     │ • Chat persistence   │     │ • NVIDIA NIM LLM    │
│ • Next.js 15.3      │     │ • NestJS 11          │     │ • Uvicorn server    │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         ▲                                                        │
         │                                                        ▼
         │                                              ┌─────────────────────┐
         └──────────────────────────────────────────────│  NVIDIA NIM API     │
                        (streamed responses)             │  (Mistral model)    │
                                                        └─────────────────────┘
```

---

## Tech Stack & Versions

| Component      | Technology               | Version    |
|----------------|--------------------------|------------|
| Frontend       | Next.js                  | 15.3.9     |
| Frontend       | React                    | 19.x       |
| Frontend       | CopilotKit React Core    | 1.56.0     |
| Frontend       | CopilotKit React UI      | 1.56.0     |
| Frontend       | Tailwind CSS             | 3.x        |
| Frontend       | TypeScript               | 5.x        |
| Backend        | NestJS                   | 11.x       |
| Backend        | Node.js                  | 20.x (via nvm) |
| Backend        | TypeScript               | 5.x        |
| Agent          | Python                   | 3.x        |
| Agent          | LangGraph                | latest     |
| Agent          | CopilotKit Python SDK    | latest     |
| Agent          | Uvicorn                  | latest     |
| Infrastructure | Daytona SDK (sandboxes)  | latest     |
| LLM Provider   | NVIDIA NIM               | Mistral    |

---

## What We've Done

### ✅ Completed

1. **Repository setup** — Cloned and organized the monorepo with `frontend/`, `backend/`, `agent/` directories
2. **Dependency installation** — All three services have their deps installed:
   - Agent: `pip install` in `/root/MASTER-PFE/agent`
   - Backend: `npm install --legacy-peer-deps` (needed for peer dep conflicts)
   - Frontend: `npm install --legacy-peer-deps` + added `tailwindcss@3 autoprefixer postcss`
3. **ESLint 9 migration** — Backend moved from `.eslintrc.json` to `eslint.config.mjs` (flat config)
4. **TypeScript config fixes** — Backend `tsconfig.json` updated: `moduleResolution: "node16"`, `module: "node16"` (required for `@copilotkit/runtime/langgraph` subpath exports)
5. **Agent checkpointer fix** — Patched `agent/agent/graph.py` to use `MemorySaver` checkpointer (was missing, causing runtime errors)
6. **Agent zombie process fix** — Used `sandbox.process.create_session()` + `execute_session_command()` instead of `exec()` to avoid zombie processes on Daytona
7. **Backend ESM fix** — Added `npm i p-retry@5` to fix ESM module resolution error
8. **All 3 services verified running**:
   - Agent health endpoint: `GET /health` → `{"status":"ok"}` on port 8000
   - Backend: listening on port 3001, `/copilotkit/*` route mapped
   - Frontend: Next.js serving on port 3000, returns 200
9. **CopilotKit CSS fix** — Added proper Tailwind directives to `globals.css`, added `@copilotkit/react-ui/styles.css` import in both `layout.tsx` and `page.tsx`, added CSS custom properties for dark theme, added height constraints for CopilotChat container
10. **Daytona sandbox management** — Created sandbox with `public=True`, managed sessions for all services, cleaned up old sandboxes

### ⚠️ Partially Done

- **Public URL access**: URLs are generated by Daytona but show a "Preview Warning" consent page on first visit. After accepting (POST to `/accept-daytona-preview-warning`), it works via cookie. For programmatic access, use signed preview URLs or the `x-daytona-preview-token` header.

### ❌ Not Done Yet

- **NVIDIA API Key**: `LLM_API_KEY` in `agent/.env` is set to `PLACEHOLDER` — need a real NVIDIA NIM API key for the agent to make LLM calls
- **End-to-end chat test**: Cannot fully test until the API key is configured
- **Chat persistence**: Backend has chat API endpoints (`/api/chats`) but no database is connected (TypeORM/SQLite/Postgres setup needed)
- **Production deployment**: Docker compose exists but hasn't been tested for production

---

## Current File Structure

```
MASTER-PFE/
├── agent/
│   ├── agent/
│   │   ├── __init__.py
│   │   └── graph.py          # LangGraph graph with MemorySaver checkpointer
│   ├── .env                   # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, PORT=8000
│   ├── requirements.txt
│   └── pyproject.toml
├── backend/
│   ├── src/
│   │   └── ...                # NestJS modules, controllers, services
│   ├── .env                   # PORT=3001, AGENT_URL, CORS_ORIGINS=*
│   ├── eslint.config.mjs      # ESLint 9 flat config
│   ├── tsconfig.json           # moduleResolution: node16
│   └── package.json
├── frontend/
│   ├── app/
│   │   ├── globals.css         # Tailwind directives + CopilotKit dark theme overrides
│   │   ├── layout.tsx          # Root layout with CopilotKit provider + CSS import
│   │   ├── page.tsx            # Main page with CopilotChat component
│   │   └── page.module.css
│   ├── components/
│   │   ├── Chat.tsx            # Custom chat component (alternative to CopilotChat)
│   │   ├── PlanAccordion.tsx   # Execution plan accordion UI
│   │   └── chat/
│   │       ├── PlanView.tsx
│   │       └── PlanView.module.css
│   ├── lib/
│   │   ├── api.ts              # Chat persistence API client
│   │   └── copilot.ts          # CopilotKit URL config
│   ├── types/
│   │   └── index.ts            # TypeScript interfaces
│   ├── .env.local              # NEXT_PUBLIC_COPILOT_URL
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── next.config.js          # standalone output
│   └── package.json
├── docs/
│   └── screenshots/            # Testing screenshots
├── docker-compose.yml
├── cloudflare-tunnel.sh
├── PROGRESS.md
├── RAILWAY.md
├── SESSION_NOTES.md            # ← This file
└── README.md
```

---

## Environment Variables

### Agent (`agent/.env`)
```env
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=PLACEHOLDER          # ⚠️ REPLACE with real NVIDIA NIM API key
LLM_MODEL=mistralai/mistral-7b-instruct-v0.3
PORT=8000
```

### Backend (`backend/.env`)
```env
PORT=3001
AGENT_URL=http://localhost:8000/copilotkit
CORS_ORIGINS=*
```

### Frontend (`frontend/.env.local`)
```env
NEXT_PUBLIC_COPILOT_URL=http://localhost:3001/copilotkit
```

> **Note**: When deploying on Daytona or any remote VM, replace `localhost` URLs with the actual service URLs or keep them as `localhost` if all services run on the same machine.

---

## How to Run (Daytona VM)

### Prerequisites
- Daytona SDK API key
- Node.js 20+ (use `nvm use 20`)
- Python 3.10+
- A valid NVIDIA NIM API key

### 1. Create Daytona Sandbox
```python
from daytona_sdk import Daytona, DaytonaConfig, CreateSandboxFromImageParams, Resources

daytona = Daytona(DaytonaConfig(api_key="YOUR_DAYTONA_API_KEY"))
sandbox = daytona.create(CreateSandboxFromImageParams(
    image="ubuntu:22.04",
    public=True,
    resources=Resources(cpu=4, memory=4, disk=10),
))
```

### 2. Clone & Install
```bash
git clone https://github.com/hamdisoudani/MASTER-PFE.git /root/MASTER-PFE
cd /root/MASTER-PFE

# Agent
cd agent && pip install -r requirements.txt && cd ..

# Backend (Node 20 required)
nvm install 20 && nvm use 20
cd backend && npm install --legacy-peer-deps && npm i p-retry@5 && cd ..

# Frontend
cd frontend && npm install --legacy-peer-deps && cd ..
```

### 3. Start Services
```bash
# Terminal 1 — Agent
cd /root/MASTER-PFE/agent
python3 -m uvicorn agent.graph:app --host 0.0.0.0 --port 8000

# Terminal 2 — Backend
cd /root/MASTER-PFE/backend
nvm use 20 && npm run start:dev

# Terminal 3 — Frontend
cd /root/MASTER-PFE/frontend
npm run dev
```

### 4. Access URLs
Via Daytona preview URLs:
- Frontend: `https://3000-<sandbox-id>.daytonaproxy01.net`
- Backend: `https://3001-<sandbox-id>.daytonaproxy01.net`
- Agent: `https://8000-<sandbox-id>.daytonaproxy01.net`

> First visit shows a "Preview Warning" page — click "I Understand, Continue" to proceed.  
> For programmatic access, use `sandbox.create_signed_preview_url(port)` or pass the `x-daytona-preview-token` header.

---

## Known Issues & Fixes Applied

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Backend can't resolve `@copilotkit/runtime/langgraph` | `moduleResolution: "node"` doesn't support subpath exports | Changed to `"node16"` in tsconfig.json |
| Backend ESM error with `p-retry` | Default version uses ESM, NestJS expects CJS | `npm i p-retry@5` (last CJS version) |
| Agent zombie processes on Daytona | `sandbox.exec()` creates orphan processes | Use `sandbox.process.create_session()` + `execute_session_command()` |
| Agent missing checkpointer | `graph.py` had no checkpointer configured | Added `MemorySaver` from `langgraph.checkpoint.memory` |
| CopilotKit chat has no styling | Missing CSS import + no Tailwind directives + no container height | Added `@copilotkit/react-ui/styles.css` import, Tailwind directives in globals.css, explicit height on chat container |
| Daytona preview warning on public URLs | Default Daytona behavior even with `public=True` | Accept the warning (sets cookie) or use signed URLs / token header |
| Frontend peer dep conflicts | React 19 + CopilotKit 1.56 version mismatches | `npm install --legacy-peer-deps` |
| Missing Tailwind in frontend | `tailwindcss`, `autoprefixer`, `postcss` not in deps | `npm i tailwindcss@3 autoprefixer postcss` |

---

## Screenshots

### GitHub Repository Overview
![GitHub Repo](docs/screenshots/github-repo-overview.png)

### Daytona Preview Warning Page
![Preview Warning](docs/screenshots/frontend-preview-warning.png)

> **Note**: The VM was deleted after testing. Screenshots show the state at time of testing. The frontend renders the CopilotChat component with dark theme styling when the services are running.

---

## What's Left To Do

### 🔴 Critical (Must Do Next Session)

1. **Get NVIDIA NIM API Key** — Replace `PLACEHOLDER` in `agent/.env` with a real key. Without this, the agent can't call the LLM and chat won't work end-to-end.

2. **End-to-End Test** — Once the API key is set:
   - Send a message in the chat UI
   - Verify it reaches the backend → agent → NVIDIA NIM → response streams back
   - Check for any runtime errors in each service's logs

3. **CopilotKit CSS Verification** — The CSS imports are now in place. On next deploy, verify:
   - The CopilotChat component renders with proper styling (input box, message bubbles, scrollable area)
   - Dark theme overrides in `globals.css` apply correctly
   - If styles still don't show, check browser DevTools for 404 on the CSS file

### 🟡 Important (Should Do)

4. **Database Setup for Chat Persistence** — Backend has chat API routes but no database:
   - Install TypeORM + SQLite (or Postgres): `npm i @nestjs/typeorm typeorm sqlite3`
   - Create Chat and Message entities
   - Wire up the TypeORM module in `app.module.ts`

5. **Custom Chat Component Decision** — There are TWO chat implementations:
   - `page.tsx` uses `<CopilotChat>` (CopilotKit's built-in component)
   - `components/Chat.tsx` is a custom chat UI using `useCopilotChat()` hook
   - **Decide which to use** and remove the other to avoid confusion
   - The custom `Chat.tsx` gives more control over styling but needs more maintenance

6. **Environment Variable Management** — Consider using a `.env.example` file to document required variables without exposing secrets

### 🟢 Nice To Have

7. **Docker Compose Testing** — `docker-compose.yml` exists but hasn't been validated. Test it for local development and production deployment.

8. **Cloudflare Tunnel** — `cloudflare-tunnel.sh` exists for exposing services. Could be an alternative to Daytona preview URLs.

9. **Error Handling & Loading States** — Improve the frontend to show better error messages when:
   - Backend is unreachable
   - Agent fails to respond
   - LLM API key is invalid

10. **Agent Capabilities** — Expand the LangGraph agent with:
    - More tools (web search, code execution, file operations)
    - Better plan generation and execution tracking
    - Memory/context persistence across conversations

---

## Quick Reference Commands

```bash
# Check if services are running
curl http://localhost:8000/health          # Agent
curl http://localhost:3001/copilotkit      # Backend
curl http://localhost:3000                  # Frontend

# Kill a service by port
fuser -k 8000/tcp   # Agent
fuser -k 3001/tcp   # Backend
fuser -k 3000/tcp   # Frontend

# View logs (when running in Daytona sessions)
# Sessions: agent-svc, backend-svc, frontend-svc
```

---

*This file is meant to be the single source of truth for the project's current state. Update it at the end of each coding session.*
