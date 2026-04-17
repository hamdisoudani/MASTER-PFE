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

## 🔔 RULE 4 — Always build-test BEFORE pushing to GitHub

**NEVER push code changes without running a successful build first.**

The local BU sandbox has ~1.6GB disk and cannot run `npm install` + `next build` for this project. Instead, use **E2B sandbox via Composio** for all heavy build/test operations.

### E2B Build-Test Workflow

1. **Create sandbox** — `E2B_POST_SANDBOXES` with template `desktop` (powerful sandbox with plenty of disk/RAM)
2. **Connect** — `E2B_CONNECT_SANDBOX` with the returned `sandbox_id`
3. **Clone & build** — run commands via `composio_workbench`:
   ```python
   run_composio_tool("E2B_POST_SANDBOXES", {"template": "desktop"})
   # connect, then use COMPOSIO_REMOTE_WORKBENCH to run:
   # git clone https://github.com/hamdisoudani/MASTER-PFE.git
   # cd MASTER-PFE/frontend && npm install && npm run build
   ```
4. **Only push if build succeeds** — if build fails, fix the code and re-test before pushing
5. **Tear down** — `E2B_DELETE_SANDBOXES` when done to avoid costs

### Composio E2B Tools Reference

| Tool | Purpose |
|------|---------|
| `E2B_POST_SANDBOXES` | Create sandbox (use `template: "desktop"`) |
| `E2B_CONNECT_SANDBOX` | Connect to sandbox by ID |
| `E2B_POST_SANDBOXES_TIMEOUT` | Extend sandbox TTL |
| `E2B_REFRESH_SANDBOX` | Keep sandbox alive |
| `E2B_GET_SANDBOXES_LOGS` | Debug build failures |
| `E2B_DELETE_SANDBOXES` | Clean up after done |
| `COMPOSIO_REMOTE_WORKBENCH` | Execute commands in connected sandbox |

### Why not build locally?
- BU sandbox has ~1.6GB disk — `node_modules` alone is ~350MB, build artifacts add more
- `next build` frequently times out or runs out of space
- E2B desktop template provides a full environment with ample resources

---

## 🔔 RULE 5 — Use E2B for any heavy operation

Not just builds — use E2B sandbox for:
- Running full test suites
- Installing large dependency trees
- Any operation that needs >1GB disk or significant RAM
- TypeScript compilation checks (`npx tsc --noEmit`)

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

---

## Session — 2026-04-17 (build fix)

### Issues fixed this session

| # | Error | Root cause | Fix | Commit |
|---|-------|------------|-----|--------|
| 1 | Frontend build: `AgentActivityPanel` missing required props | `CopilotTools.tsx` renders `<AgentActivityPanel />` with no props but all 4 props were required | Made all 4 props optional with defaults (`[]`, `0`, `"idle"`, `""`) | `785b8b9` |
| 2 | Agent: `openai.AuthenticationError` — missing authorization header | `nodes.py` used `NVIDIA_API_KEY` env var but Railway uses `LLM_API_KEY` per `.env.example` | Changed to `os.environ.get("LLM_API_KEY")`, also made `LLM_BASE_URL` and `LLM_MODEL` configurable | `b53cf3e` |

### Key learnings
- **Build-test before push** — the AgentActivityPanel fix was correct but wasn't build-tested locally due to disk constraints. Use E2B next time.
- **Env var naming consistency** — always check `.env.example` for the canonical env var names before hardcoding them in source files.
- **⚠️ Potential issue:** `agent/search.py` has `SERPERE_API_KEY` (typo) — should likely be `SERPER_API_KEY`. Needs verification.

*Last updated: 2026-04-17*
