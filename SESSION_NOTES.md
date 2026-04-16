# SESSION NOTES — Read This First on Every New Session

> ⚠️ **STRICT** — These rules were learned from real bugs. Violating them breaks the app silently.

---

## 🔴 RULE 1 — Agent name must be identical in all 3 places

The `agent` name is a string key that must match **exactly** (case-sensitive) across the entire stack.
If any one of the three is different, CopilotKit silently fails to find the agent and the sidebar never responds.

| Layer | File | Current value |
|-------|------|---------------|
| **Frontend** | `frontend/app/layout.tsx` | `agent="syllabus_agent"` |
| **Backend** | `backend/src/copilot/copilot.controller.ts` | `agents: { syllabus_agent: <HttpAgent> }` |
| **Agent** | `agent/main.py` | `LangGraphAGUIAgent(name="syllabus_agent")` |

**When you rename the agent** → update all 3 files in the same commit.

---

## 🔴 RULE 2 — Only ONE `<CopilotKit>` provider in the tree

`<CopilotKit>` must appear **only in `layout.tsx`**. Never add a second `<CopilotKit>` wrapper inside `page.tsx` or any child component. A double-wrap causes context conflicts and breaks all hooks.

---

## 🔴 RULE 3 — Backend URL is hardcoded in layout.tsx (no proxy)

The working setup uses a direct hardcoded URL in `layout.tsx`:

```tsx
<CopilotKit
  runtimeUrl="https://backend-production-47f8.up.railway.app/copilotkit"
  agent="syllabus_agent"
>
```

Do **not** replace this with a `/api/copilotkit` Next.js proxy route — that was tried and broke communication.
If the backend URL changes on Railway, update this one line only.

---

## Architecture snapshot (as of last working session)

```
Browser
  └─▶ layout.tsx  <CopilotKit runtimeUrl="https://backend-production-47f8.up.railway.app/copilotkit" agent="syllabus_agent">
         │
         ▼
      NestJS /copilotkit
        agents: { syllabus_agent: HttpAgent → AGENT_URL }
         │
         ▼
      FastAPI LangGraphAGUIAgent(name="syllabus_agent")
         │
         ▼
      NVIDIA NIM (LLM)
```

---

## Syllabus Builder — CopilotKit tools registered

| Tool | Description |
|------|-------------|
| `create_syllabus` | Creates a new syllabus with title + description |
| `add_chapter` | Adds a chapter to the active syllabus |
| `add_lesson` | Adds a lesson under a chapter |
| `update_lesson_content` | Updates BlockNote content of a lesson |
| `remove_chapter` | Removes a chapter and all its lessons |
| `remove_lesson` | Removes a single lesson |
| `report_render_error` | Reports a rendering error back to the AI |

---

## Key packages (frontend)

| Package | Version | Note |
|---------|---------|------|
| `@blocknote/react` | `^0.48` | Uses `.bn-root` for theme vars (breaking change from older) |
| `@copilotkit/react-core` | latest | Must NOT be double-wrapped |
| `zustand` | `^4.5.2` | Persist store for syllabus state |
| `@mantine/core` | `^7.15` | Required peer dep for BlockNote |

---

*Last updated: session where double-CopilotKit-wrapper and agent name mismatch bugs were fixed.*
