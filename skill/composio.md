# Composio — Skills & Reference

> **Purpose:** Everything learned about using Composio as the bridge between Browser-Use agents and external services (GitHub, E2B, and 1,000+ others).  
> Keep this file updated every time new patterns are discovered so future sessions never need to re-learn from scratch.

---

## What is Composio?

Composio is the **gateway / bridge** that gives the agent pre-authenticated access to external APIs.  
Instead of managing OAuth flows, API keys, or SDK versions yourself, you call Composio tools and it handles auth, retries, and transport.

Key integrations used in this project:
- **GitHub** — read/write files, commit, branch, PR
- **E2B** — cloud sandboxes for running untrusted code
- **1,000+ more** — Gmail, Slack, Notion, Google Sheets, etc.

---

## Two Ways to Call Composio

### 1. `execute_composio_tool` (single call, from main agent loop)

```python
result = execute_composio_tool(
    tool_name="TOOL_SLUG",
    args='{"key": "value"}'   # JSON string, NOT a dict
)
# result["data"] contains the response
# result["success"] is True/False
```

### 2. `composio_workbench` (Python sandbox, best for loops & batch work)

```python
composio_workbench(code="""
res, _ = run_composio_tool("TOOL_SLUG", {"key": "value"})
# res["data"] contains the payload
print(res["data"])
""")
```

> **Critical difference:**
> - `execute_composio_tool` → result is a flat dict, access via `result["data"]`
> - Inside `composio_workbench`, `run_composio_tool(...)` returns a **tuple** `(data_dict, log_string)`
> - Always unpack: `res, _ = run_composio_tool(...)`
> - Access payload via `res["data"]`, NEVER `res["response"]`

---

## Checking Connection Status

Before using any integration, verify it is connected:

```python
result = execute_composio_tool("GITHUB_GET_A_REPOSITORY", args='{"owner": "x", "repo": "y"}')
# If result["success"] is False and mentions auth → integration not connected
# If True → ready to use
```

`search_composio_tools` also returns `connection_statuses` per provider.

---

## GitHub Tools

### Search for tools

```
search_composio_tools(query="github push commit file")
```

### Available GitHub tools (commonly used)

| Tool | Description |
|------|-------------|
| `GITHUB_GET_A_REPOSITORY` | Get repo metadata, default branch, permissions |
| `GITHUB_GET_A_BRANCH` | Get branch HEAD SHA, check if branch exists |
| `GITHUB_GET_REPOSITORY_CONTENT` | Read a file (returns base64-encoded content) |
| `GITHUB_GET_A_TREE` | List all files/dirs in a repo recursively |
| `GITHUB_COMMIT_MULTIPLE_FILES` | Atomic multi-file commit (preferred) |
| `GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS` | Single-file create/update |
| `GITHUB_CREATE_A_PULL_REQUEST` | Open a PR between two branches |
| `GITHUB_LIST_CHECK_RUNS_FOR_A_REF` | Check CI status for a commit/branch |

### Reading a file

```python
res, _ = run_composio_tool("GITHUB_GET_REPOSITORY_CONTENT", {
    "owner": "myorg",
    "repo":  "myrepo",
    "path":  "agent/nodes.py"
})
import base64
content = base64.b64decode(res["data"]["content"]["content"]).decode("utf-8")
sha     = res["data"]["content"]["sha"]   # needed for single-file updates
```

### Writing / updating a single file

```python
import base64
encoded = base64.b64encode(new_content.encode()).decode()

run_composio_tool("GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS", {
    "owner":   "myorg",
    "repo":    "myrepo",
    "path":    "agent/nodes.py",
    "message": "fix: repair corrupted string literals",
    "content": encoded,
    "sha":     existing_sha,   # omit sha if creating a brand-new file
    "branch":  "main"
})
```

### Committing multiple files at once (PREFERRED)

```python
run_composio_tool("GITHUB_COMMIT_MULTIPLE_FILES", {
    "owner":   "myorg",
    "repo":    "myrepo",
    "branch":  "main",
    "message": "chore: add skill docs and update README",
    "upserts": [                              # <-- key is "upserts", NOT "files"
        {"path": "skill/composio.md", "content": file1_content},
        {"path": "README.md",          "content": readme_content},
    ]
    # add "base_branch": "main" ONLY when the target branch is new
})
```

> **GOTCHA:** The parameter is `"upserts"`, **not** `"files"`. Using `"files"` silently passes no data and returns `Bad Request: At least one file must be specified`.

> `GITHUB_COMMIT_MULTIPLE_FILES` uses Git Data APIs (not Contents API) — avoids SHA-mismatch conflicts on parallel writes. Always prefer it for multi-file changes.

### Listing all files in a repo

```python
res, _ = run_composio_tool("GITHUB_GET_A_TREE", {
    "owner":     "myorg",
    "repo":      "myrepo",
    "tree_sha":  "main",
    "recursive": True
})
files = [item["path"] for item in res["data"]["tree"]["tree"] if item["type"] == "blob"]
```

---

## E2B Tools

### Search for tools

```
search_composio_tools(query="e2b code execution sandbox")
```

### Available E2B tools

| Tool | Description |
|------|-------------|
| `E2B_LIST_TEMPLATES` | List available sandbox templates |
| `E2B_POST_SANDBOXES` | Create a new sandbox |
| `E2B_CONNECT_SANDBOX` | Reconnect to an existing sandbox |
| `E2B_GET_SANDBOX` | Get sandbox status/details |
| `E2B_GET_SANDBOXES_LOGS` | Retrieve sandbox stdout/stderr logs |
| `E2B_REFRESH_SANDBOX` | Extend sandbox TTL |
| `E2B_DELETE_SANDBOXES` | Terminate and delete a sandbox |

### Creating a sandbox

```python
res, _ = run_composio_tool("E2B_POST_SANDBOXES", {"templateID": "base"})
sandbox_id = res["data"]["sandboxID"]
```

> **Note:** `"base"` is the default Python environment. Use `E2B_LIST_TEMPLATES` to see custom templates (empty for new accounts).

### Important E2B gotchas

1. **Sandboxes expire fast** (default TTL ~5 min). Create the sandbox and do all your work in the **same `composio_workbench` call** — don't create in one call and use in another.
2. **E2B via Composio ≠ shell access** — it only manages sandbox lifecycle. To actually run code, use `composio_workbench` with `subprocess`.
3. **For real code execution**, `composio_workbench` is already a Python runtime — no separate E2B sandbox needed:

```python
# composio_workbench already IS a Python runtime
import subprocess, sys
proc = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/"],
    capture_output=True, text=True, timeout=120
)
print(proc.stdout)
print(proc.stderr)
```

---

## `composio_workbench` — The Remote Python Sandbox

This is the most powerful tool. It runs arbitrary Python with full Composio access.

### Basic pattern

```python
composio_workbench(code="""
# run_composio_tool is pre-injected — no import needed
# invoke_llm is also available for AI sub-tasks

res, _ = run_composio_tool("GITHUB_GET_A_REPOSITORY", {
    "owner": "myorg", "repo": "myrepo"
})
print(res["data"])
""")
```

### Parallel calls with ThreadPoolExecutor

```python
composio_workbench(code="""
from concurrent.futures import ThreadPoolExecutor

paths = ["agent/nodes.py", "agent/tools.py", "agent/graph.py"]

def fetch_file(path):
    res, _ = run_composio_tool("GITHUB_GET_REPOSITORY_CONTENT", {
        "owner": "myorg", "repo": "myrepo", "path": path
    })
    return path, res["data"]["content"]["content"]

with ThreadPoolExecutor(max_workers=5) as ex:
    results = dict(ex.map(fetch_file, paths))

print(list(results.keys()))
""")
```

### Using `invoke_llm` for AI sub-tasks

```python
composio_workbench(code="""
code = open("/tmp/nodes.py").read()
review = invoke_llm(f"Review this Python code for bugs:\\n\\n{code}")
print(review)
""")
```

### Timeout
- Hard limit: **4 minutes** per `composio_workbench` call
- Use `subprocess` with explicit `timeout=` for shell commands
- For pip installs, use `--dry-run` first to check if packages are already installed

---

## Response Schema Reference

### `execute_composio_tool` (called directly from agent)

```python
result = execute_composio_tool("TOOL_SLUG", args='{"k": "v"}')
result["success"]      # bool
result["data"]         # dict — the actual payload
result["error"]        # str or None
result["provider"]     # e.g. "github"
result["display_name"] # e.g. "GitHub"
```

### `run_composio_tool` (inside `composio_workbench`)

```python
res, log = run_composio_tool("TOOL_SLUG", {"k": "v"})
# res  -> dict with keys: "data", "error", "log_id"
# log  -> string with stdout from the tool run
res["data"]   # actual payload
res["error"]  # None if successful
```

---

## Common Patterns

### Pattern 1 — Read → modify → commit (single file)

```python
composio_workbench(code="""
import base64

res, _ = run_composio_tool("GITHUB_GET_REPOSITORY_CONTENT", {
    "owner": "myorg", "repo": "myrepo", "path": "agent/nodes.py"
})
sha     = res["data"]["content"]["sha"]
current = base64.b64decode(res["data"]["content"]["content"]).decode()

new_content = current.replace("old_string", "new_string")
encoded     = base64.b64encode(new_content.encode()).decode()

run_composio_tool("GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS", {
    "owner": "myorg", "repo": "myrepo", "path": "agent/nodes.py",
    "message": "fix: replace old_string", "content": encoded, "sha": sha
})
print("Done")
""")
```

### Pattern 2 — Fetch many files, audit, push fixes

```python
composio_workbench(code="""
import base64, ast
from concurrent.futures import ThreadPoolExecutor

PATHS = ["agent/nodes.py", "agent/tools.py", "agent/graph.py"]

def fetch(path):
    res, _ = run_composio_tool("GITHUB_GET_REPOSITORY_CONTENT", {
        "owner": "myorg", "repo": "myrepo", "path": path
    })
    raw = base64.b64decode(res["data"]["content"]["content"]).decode()
    sha = res["data"]["content"]["sha"]
    return path, raw, sha

with ThreadPoolExecutor() as ex:
    results = list(ex.map(fetch, PATHS))

upserts = []
for path, src, _ in results:
    try:
        ast.parse(src)
        print(f"OK   {path}")
    except SyntaxError as e:
        print(f"ERR  {path}: {e}")
        fixed   = src  # replace with your fix logic
        upserts.append({"path": path, "content": fixed})

if upserts:
    run_composio_tool("GITHUB_COMMIT_MULTIPLE_FILES", {
        "owner": "myorg", "repo": "myrepo", "branch": "main",
        "message": "fix: syntax errors",
        "upserts": upserts      # <-- always "upserts"
    })
""")
```

### Pattern 3 — pip dry-run + import check (no E2B needed)

```python
composio_workbench(code="""
import subprocess, sys, os, tempfile, base64

PATHS = ["agent/requirements.txt", "agent/nodes.py"]
tmpdir = tempfile.mkdtemp()

for path in PATHS:
    res, _ = run_composio_tool("GITHUB_GET_REPOSITORY_CONTENT", {
        "owner": "myorg", "repo": "myrepo", "path": path
    })
    src  = base64.b64decode(res["data"]["content"]["content"]).decode()
    full = os.path.join(tmpdir, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w").write(src)

proc = subprocess.run(
    [sys.executable, "-m", "pip", "install", "--quiet", "--dry-run",
     "-r", os.path.join(tmpdir, "agent/requirements.txt")],
    capture_output=True, text=True, timeout=60
)
print("pip dry-run rc:", proc.returncode)

import_script = f"""
import sys
sys.path.insert(0, {repr(tmpdir)})
for m in ["agent.state","agent.tools","agent.nodes","agent.graph"]:
    try:
        __import__(m, fromlist=[""])
        print("OK", m)
    except Exception as e:
        print("ERR", m, e)
"""
proc2 = subprocess.run(
    [sys.executable, "-c", import_script],
    capture_output=True, text=True, timeout=30,
    env={**os.environ, "PYTHONPATH": tmpdir, "LLM_API_KEY": "dummy", "DATABASE_URL": "dummy"}
)
print(proc2.stdout)
if proc2.stderr:
    print(proc2.stderr[-500:])
""")
```

---

## Pitfalls & Lessons Learned

| Pitfall | Fix |
|---------|-----|
| `run_composio_tool` returns a tuple, not a dict | Always unpack: `res, _ = run_composio_tool(...)` |
| Accessing `res["response"]` | Wrong key — use `res["data"]` |
| Passing `"files"` to `GITHUB_COMMIT_MULTIPLE_FILES` | Wrong key — use `"upserts"` |
| Creating E2B sandbox in one call, using it in another | Sandbox expires; do everything in one `composio_workbench` call |
| `execute_composio_tool(args=...)` expects a JSON string | Pass `args='{"key": "val"}'` not `args={"key": "val"}` |
| `GITHUB_COMMIT_MULTIPLE_FILES` on a new branch without `base_branch` | Include `"base_branch": "main"` when the branch does not yet exist |
| `AnnAssign` nodes missed in AST export scan | Use both `ast.Assign` AND `ast.AnnAssign` when scanning top-level names |
| pip install timing out | Use `--dry-run` first; packages are often pre-installed in the workbench |

---

## Searching for Tools

Always run `search_composio_tools` before assuming a tool name:

```
search_composio_tools(query="send email gmail")
search_composio_tools(query="create google calendar event")
search_composio_tools(query="post slack message")
search_composio_tools(query="create notion page")
```

Returns:
- `tools[]` — list of matching tools with `name`, `description`, `provider`
- `connection_statuses` — which providers are currently authenticated
- `tools_needing_auth` — providers that need to be connected first
- `primary_tools[]` — recommended tools for the query
- `execution_plan[]` — suggested sequence of steps

---

## Quick Reference Card

```
+---------------------+--------------------------------------------+
|              COMPOSIO QUICK REFERENCE                            |
+---------------------+--------------------------------------------+
| Discover tools      | search_composio_tools(query="...")         |
| Single call         | execute_composio_tool(tool, args='{"k":"v"}') |
| Batch / loop        | composio_workbench(code="...")             |
| Inside workbench    | res, _ = run_composio_tool(tool, {...})    |
| Result key          | res["data"]  (NOT res["response"])         |
| AI sub-task         | invoke_llm("prompt")                       |
| Parallel            | ThreadPoolExecutor inside workbench        |
+---------------------+--------------------------------------------+
| Read GitHub file    | GITHUB_GET_REPOSITORY_CONTENT              |
| Write one file      | GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS      |
| Write many files    | GITHUB_COMMIT_MULTIPLE_FILES               |
|   multi-file key    |   "upserts": [{"path":..., "content":...}] |
| List repo tree      | GITHUB_GET_A_TREE                          |
| Create sandbox      | E2B_POST_SANDBOXES {"templateID":"base"}   |
| Run code            | composio_workbench + subprocess            |
+---------------------+--------------------------------------------+
```
