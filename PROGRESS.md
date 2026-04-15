# PROGRESS.md — Master PFE

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Browser (Next.js 14)                          │
│  CopilotKit v1.55  ·  CopilotSidebar  ·  useCoAgent                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ POST /api/copilotkit (rewrite)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│          NestJS Backend  (port 3001)                                  │
│  CopilotKit Runtime v2  ·  createCopilotExpressHandler               │
│  REST API  /api/chats  ·  TypeORM + SQLite                           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ AG-UI protocol  HTTP → port 8000
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│          Python Agent  (FastAPI, port 8000)                           │
│  CopilotKit SDK  ·  LangGraphAGUIAgent  ·  LangGraph state machine   │
│  Custom LLM via .env  (openai | anthropic | google | custom)         │
└─────────────────────────────────────────────────────────────────────┘
```

## Services

| Service   | Port | Tech                              |
|-----------|------|-----------------------------------|
| Frontend  | 3000 | Next.js 14 + CopilotKit v1.55     |
| Backend   | 3001 | NestJS 10 + CopilotKit Runtime v2 |
| Agent     | 8000 | FastAPI + LangGraph + CopilotKit  |

## Key CopilotKit Choices

### Frontend
- `CopilotKit` provider from `@copilotkit/react-core` with `runtimeUrl="/api/copilotkit"`
- `CopilotSidebar` from `@copilotkit/react-ui` (pre-built UI)
- `useCoAgent<T>` — read/write typed LangGraph agent state
- `useCoAgentStateRender<T>` — generative UI on agent state changes
- `useCopilotAction` — expose frontend tools the agent can call

### Backend (NestJS)
- `CopilotRuntime` + `HttpAgent` from `@copilotkit/runtime/v2`
- `createCopilotExpressHandler` from `@copilotkit/runtime/v2/express`
- Mounted via `CopilotController` inside NestJS on `/copilotkit/**`

### Python Agent
- `CopilotKitRemoteEndpoint` + `LangGraphAGUIAgent` from `copilotkit` SDK
- `add_fastapi_endpoint(app, sdk, "/copilotkit")` — registers AG-UI routes
- `CopilotKitState` as graph state; `copilotkit_customize_config` for streaming
- Custom LLM factory reads `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`

## Getting Started

```bash
# 1. Agent
cd agent && cp .env.example .env && pip install -r requirements.txt
uvicorn agent.main:app --reload --port 8000

# 2. Backend
cd backend && cp .env.example .env && npm install && npm run start:dev

# 3. Frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Open http://localhost:3000

## Progress Log
| Date       | Milestone                                                   |
|------------|-------------------------------------------------------------|
| 2025-04-15 | Initial scaffold                                            |
| 2025-04-15 | Full rewrite: CopilotKit v2, LangGraph Python agent sidecar |
| 2025-04-15 | No `any` types; strict TypeScript; custom LLM env vars      |
| 2025-04-15 | useCoAgent + useCoAgentStateRender + useCopilotAction        |
| 2025-04-15 | PlanView generative UI; Docker Compose for all 3 services   |
