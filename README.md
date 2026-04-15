# MASTER-PFE — AI Planning Assistant

A full-stack AI chat application with **NestJS** backend and **Next.js** frontend,
powered by **CopilotKit** and **LangGraph**.

---

## Architecture

```
┌─────────────────────────┐        ┌──────────────────────────┐
│   Next.js Frontend      │◄──────►│   NestJS Backend          │
│   (port 3000)           │  HTTP  │   (port 4000)             │
│                         │        │                           │
│  CopilotKit React UI    │        │  CopilotRuntime           │
│  Chat sidebar           │        │  LangGraph Agent          │
│  Plan Accordion         │        │  Chats REST API           │
│  Multi-chat sessions    │        │  MemorySaver checkpointer │
└─────────────────────────┘        └──────────────────────────┘
```

## Features

- 🤖 **LangGraph agent** with planner → responder pipeline
- 📋 **Step-by-step plan accordion** — agent produces a plan before answering
- 💬 **Multi-chat sessions** — sidebar with create/delete chat
- 🌊 **Streaming responses** via CopilotKit runtime
- 🗄️ **In-memory checkpointer** (swap for PostgreSQL in production)

---

## Quick Start

### Prerequisites
- Node.js ≥ 20
- OpenAI API key

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
npm install
npm run build
npm start
# → http://localhost:4000
```

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
# Edit .env.local if backend is not on localhost:4000
npm install
npm run dev
# → http://localhost:3000
```

---

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/chats` | Create a new chat session |
| GET | `/chats?userId=` | List chats for a user |
| GET | `/chats/:id` | Get single chat |
| PATCH | `/chats/:id` | Rename a chat |
| DELETE | `/chats/:id` | Delete a chat |
| POST | `/copilot` | CopilotKit runtime endpoint |

---

## Project Structure

```
├── backend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── app.module.ts
│   │   ├── agent/
│   │   │   ├── agent.module.ts
│   │   │   └── agent.service.ts      ← LangGraph planner+responder
│   │   ├── checkpointer/
│   │   │   ├── checkpointer.module.ts
│   │   │   └── checkpointer.service.ts
│   │   ├── copilot/
│   │   │   ├── copilot.module.ts
│   │   │   └── copilot.controller.ts ← CopilotKit runtime handler
│   │   └── chats/
│   │       ├── chat.entity.ts
│   │       ├── chats.service.ts
│   │       ├── chats.controller.ts
│   │       └── chats.module.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── nest-cli.json
│
└── frontend/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                  ← Sidebar + chat routing
    │   └── globals.css
    ├── components/
    │   ├── Chat.tsx                  ← CopilotKit chat with streaming
    │   └── PlanAccordion.tsx         ← Step accordion UI
    ├── lib/
    │   └── copilot.ts
    ├── package.json
    └── tsconfig.json
```

---

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|--------|
| `@copilotkit/runtime` | 1.50.1 | Backend AI runtime |
| `@copilotkit/react-core` | 1.50.1 | Frontend hooks |
| `@copilotkit/react-ui` | 1.50.1 | Frontend UI components |
| `@langchain/langgraph` | ^0.2.0 | Agent graph execution |
| `@langchain/openai` | ^0.3.0 | OpenAI LLM adapter |
| `@nestjs/common` | ^10.0.0 | Backend framework |
| `next` | 14.2.5 | Frontend framework |
