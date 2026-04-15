# Master PFE

AI assistant platform built with:
- **Next.js 14** + CopilotKit v1.55 (frontend)
- **NestJS 10** + CopilotKit Runtime v2 (backend)
- **Python FastAPI** + LangGraph + CopilotKit SDK (AI agent)

## Quick Start

See [PROGRESS.md](./PROGRESS.md) for full documentation, architecture diagram, and setup guide.

```bash
# 1. Start the Python agent
cd agent && cp .env.example .env
# Edit .env: set LLM_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn agent.main:app --reload --port 8000

# 2. Start the NestJS backend  
cd backend && cp .env.example .env && npm install && npm run start:dev

# 3. Start the Next.js frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Open http://localhost:3000
