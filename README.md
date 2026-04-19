# MASTER-PFE

Syllabus agent: **LangGraph (Python)** + **Next.js frontend** using `@langchain/langgraph-sdk/react` `useStream`, with a **Pusher** realtime bridge (pako-gzip payloads) that lets the backend agent dispatch tool calls to the browser and resume via the LangGraph state API.

## Layout
- `agent/` — pure LangGraph graph `syllabus_agent` (no CopilotKit). Run locally with `langgraph dev`.
- `frontend/` — Next.js 15 / React 19 UI; `lib/useSyllabusAgent.ts` wraps `useStream`, `lib/pusherClient.ts` subscribes to `agent-{threadId}` channels and posts tool results back.
- `backend/` — Minimal NestJS health/chat gateway (CopilotKit + ag-ui/langgraph removed; LangGraph traffic goes direct to the agent).

## Local dev
```bash
# agent
cd agent && python3.11 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt "langgraph-cli[inmem]"
langgraph dev --host 127.0.0.1 --port 2024

# frontend
cd frontend && pnpm install && pnpm dev
```
