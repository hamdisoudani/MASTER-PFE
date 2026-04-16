# SESSION NOTES — Read This First on Every New Session

> ⚠️ **STRICT** — These rules were learned from real bugs. Violating them breaks the app silently.

---

## 🔔 RULE 1 — Agent name must be identical in all 3 places

The `agent` name is a string key that must match **exactly** (case-sensitive) across the entire stack.

| Layer | File | Current value |
|-------|------|---------------|
| **Frontend** | `frontend/app/layout.tsx` | `agent="syllabus_agent"` |
| **Backend** | `backend/src/copilot/copilot.controller.ts` | `agents: { syllabus_agent: <HttpAgent> }` |
| **Agent** | `agent/main.py` | `LangGraphAGUIAgent(name="syllabus_agent")` |

**When you rename the agent** → update all 3 files in the same commit.

---

## 🔔 RULE 2 — Only ONE `<CopilotKit>` provider in the tree

`<CopilotKit>` must appear **only in `layout.tsx`**. Never add a second one inside `page.tsx` or child components.

---

## 🔔 RULE 3 — Backend URL hardcoded in layout.tsx (no proxy)

```tsx
<CopilotKit
  runtimeUrl="https://backend-production-47f8.up.railway.app/copilotkit"
  agent="syllabus_agent"
>
```

Do **not** replace this with a `/api/copilotkit` proxy route — that was tried and broke things.

---

## Architecture

```
Browser
  └─⤶ layout.tsx <CopilotKit runtimeUrl="https://backend-production-47f8.up.railway.app/copilotkit" agent="syllabus_agent">
         │
         ⤶
      NestJS /copilotkit
        agents: { syllabus_agent: HttpAgent → AGENT_URL }
         │
         ⤶
      FastAPI LangGraphAGUIAgent(name="syllabus_agent")
         │
         ⤶
      LangGraph: chat_node ⇄ tools_node (plan_tasks / search_web / scrape_website)
         │
         ⤶
      NVIDIA NIM (LLM)
```

---

## Agent Tools

### Python-side tools (in `agent/tools.py`)

| Tool | Purpose | Key args |
|------|---------|---------|
| `plan_tasks(tasks)` | Break complex requests into steps | `tasks: list[str]` |
| `search_web(query, country, time_period, num_results)` | Serper search | country: 'us'/'fr'/..., time_period: ''/d/w/m/y |
| `scrape_website(url)` | Serper scrape → markdown | `url: str` |

### Frontend tools (in `frontend/components/CopilotTools.tsx`)

| Tool | Purpose |
|------|---------|
| `create_syllabus` | Create a new course |
| `add_chapter` | Add chapter to syllabus |
| `add_lesson` | Add lesson with BlockNote content |
| `update_lesson_content` | Fix/improve lesson content |
| `remove_chapter` / `remove_lesson` | Remove items |
| `report_render_error` | Report BlockNote render error |

### Env var to add on Railway (agent service)
```
SERPER_API_KEY=b4fd128a8b82c89a2c5c17773be56770c09a1193
```

---

## Agent Graph Flow

```
entry ⇒ chat_node
  ⇓ (if plan_tasks / search_web / scrape_website tool calls)
tools_node ⇒ chat_node (loop)
  ⇓ (no more python tool calls)
END
```

Frontend tool calls (create_syllabus etc.) are handled by CopilotKit runtime — they never reach the Python tools_node.

---

## Frontend Rendering

### `useCoAgentStateRender` (in `AgentActivityPanel.tsx`)
Renders inside the CopilotSidebar whenever the agent state updates:
- **Plan panel** — todo list with pending/done tasks
- **Search panel** — result cards with titles, URLs, snippets  
- **Scrape panel** — scraped page preview

### `useCopilotAction` render props (in `CopilotTools.tsx`)
Each tool has a `render` prop showing a Card during execution:
- Animated pulse dot while `status === "inProgress"` or `"executing"`
- Green ✓ when `status === "complete"`

---

## shadcn/ui Setup

Components are in `frontend/components/ui/`:
- `card.tsx`, `badge.tsx`, `button.tsx`, `progress.tsx`, `scroll-area.tsx`, `separator.tsx`
- Utility: `frontend/lib/utils.ts` (cn helper)
- Config: `frontend/components.json`
- To add more: `npx shadcn@latest add <component>` in `frontend/`

Key deps added to `package.json`:
```
class-variance-authority, clsx, tailwind-merge, lucide-react
@radix-ui/react-progress, @radix-ui/react-scroll-area,
@radix-ui/react-separator, @radix-ui/react-slot
```

---

## Key Packages

| Package | Version | Note |
|---------|---------|------|
| `@blocknote/react` | `^0.48` | Uses `.bn-root` for theme vars |
| `@copilotkit/react-core` | 1.56.0 | Must NOT be double-wrapped |
| `zustand` | `^4.5.2` | Persist store for syllabus state |
| `@mantine/core` | `^7.15` | Peer dep for BlockNote |

---

## Session — 2026-04-16 (bug-fix pass)

### Issues fixed this session

| # | Error | Root cause | Fix | File(s) |
|---|-------|------------|-----|---------|
| 1 | `SyntaxError` — files contained placeholder strings after commit | `execute_composio_tool` receives placeholder values instead of real content when large strings are passed inline in the JSON args | Switched to `composio_workbench` with content embedded as Python string literals | `agent/nodes.py`, `frontend/components/CopilotTools.tsx` |
| 2 | Frontend build: `PostCSSSyntaxError` on `@copilotkit/react-core/dist/v2/index.css` | `@copilotkit/react-core/v2` auto-imports a Tailwind v4 CSS file (~76 KB) that PostCSS in Next.js 15 cannot parse | Added webpack `IgnorePlugin` in `next.config.js` to suppress that specific CSS auto-import | `frontend/next.config.js` |
| 3 | `TypeError: get_llm() takes 0 positional arguments but 1 was given` | `nodes.py` calls `get_llm(config)` but `llm.py` defined `get_llm()` with no params | Added `config=None` optional parameter to `get_llm()` | `agent/llm.py` |
| 4 | `AttributeError: 'Context' object has no attribute 'get'` | CopilotKit stores context entries as Pydantic `Context` model instances, not plain dicts — code was calling `.get("description")` on them | Switched to attribute access: `entry.description` / `entry.value` with `hasattr` fallback | `agent/nodes.py` |

### Key learnings

- **`composio_workbench` is a separate sandbox** — it cannot read `/workspace/` files. Always embed file content directly as Python string literals in the workbench script.
- **`execute_composio_tool` args are a JSON string** — large file content passed inline gets truncated/replaced. Use `composio_workbench` + `run_composio_tool()` for real file content.
- **`@copilotkit/react-core/v2` CSS** — the `/v2` subpath ships a full Tailwind v4 stylesheet that Next.js PostCSS cannot handle. Suppress with `IgnorePlugin`; add CopilotKit styles manually if needed.
- **CopilotKit context entries are Pydantic objects** — always use `entry.description` / `entry.value`, not dict `.get()`.

*Last updated: 2026-04-16 — agent fully working end-to-end.*
