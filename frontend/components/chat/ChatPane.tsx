"use client";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { useSyllabusStore } from "@/store/syllabusStore";
import { useSyllabusRealtime } from "@/hooks/useSyllabusRealtime";
import { useThreadStore } from "@/stores/thread-store";
import { useThreadSettingsStore } from "@/stores/thread-settings-store";
import { useThreads, threadVariant } from "@/providers/Thread";
import { useCancelStream } from "@/hooks/useCancelStream";
import { useThreadStatus } from "@/hooks/useThreadStatus";
import { Markdown } from "@/components/chat/Markdown";
import { AlertCircle, Ban, BookOpen, Bot, CheckCircle2, ChevronDown, ChevronRight, Circle, Eye, FileText, Layers, ListTodo, Loader2, OctagonAlert, Pencil, RotateCw, Send, Sparkles, Square, Users, Wrench, XCircle, Zap, ZapOff } from "lucide-react";
import { usePlanStore } from "@/stores/plan-store";
import { PlanCard } from "@/components/chat/PlanCard";
import { PlanStrip } from "@/components/chat/PlanStrip";

type AnyMsg = {
  id?: string;
  type?: string;
  role?: string;
  content?: unknown;
  tool_calls?: unknown[];
  tool_call_id?: string;
  name?: string;
};

// ── Strict JSON schemas for frontend tools ────────────────────────────────
// These are forwarded to the agent via config.configurable.frontend_tools
// and turned into OpenAI function definitions in agent/nodes.py. We pass
// `strict: true` on every tool so OpenAI's Structured Outputs guarantees the
// tool_call arguments are valid JSON that matches the schema — the model
// cannot emit "...", "…", trailing commas, or invalid blocks.
//
// OpenAI strict mode rules we respect:
//   - every object sets additionalProperties:false
//   - every key in `properties` is listed in `required`
//   - optional fields are expressed as a nullable union (e.g. ["string","null"])
//   - no `$ref` self-recursion, no `minimum`/`format`/`pattern`
//
// The block schema intentionally omits `children` so the model cannot emit
// nested blocks (BlockNote supports them, but our agent loop doesn't use
// them yet and strict mode would otherwise force them to be required).

const TEXT_STYLES_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["bold", "italic", "underline", "strike", "code"],
  properties: {
    bold: { type: ["boolean", "null"] },
    italic: { type: ["boolean", "null"] },
    underline: { type: ["boolean", "null"] },
    strike: { type: ["boolean", "null"] },
    code: { type: ["boolean", "null"] },
  },
} as const;

const TEXT_RUN_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["type", "text", "styles"],
  properties: {
    type: { type: "string", enum: ["text"] },
    text: { type: "string" },
    styles: TEXT_STYLES_SCHEMA,
  },
} as const;

const BLOCK_PROPS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["level", "language", "checked"],
  properties: {
    level: {
      description: "Heading level (1, 2, or 3). Null for non-heading blocks.",
      type: ["integer", "null"],
      enum: [1, 2, 3, null],
    },
    language: {
      description: "Programming language for codeBlock. Null for non-code blocks.",
      type: ["string", "null"],
    },
    checked: {
      description: "Checked state for checkListItem. Null otherwise.",
      type: ["boolean", "null"],
    },
  },
} as const;

const BLOCK_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["type", "props", "content"],
  properties: {
    type: {
      type: "string",
      enum: [
        "paragraph",
        "heading",
        "bulletListItem",
        "numberedListItem",
        "checkListItem",
        "quote",
        "codeBlock",
      ],
    },
    props: BLOCK_PROPS_SCHEMA,
    content: {
      description: "One or more styled text runs that make up the block's text.",
      type: "array",
      items: TEXT_RUN_SCHEMA,
    },
  },
} as const;

const FRONTEND_TOOLS = [
  {
    name: "askUser",
    description: "Ask the end user one or more structured questions with clickable choices. The UI renders each question as a card with choice chips plus an optional free-text fallback. Use this whenever you need input (title, audience, language, tone, lesson count, …) instead of asking in chat. Batch related questions in ONE call. Returns {answers: {<id>: <picked or typed string or array of strings>}}.",
    strict: false,
    parameters: {
      type: "object",
      required: ["questions"],
      properties: {
        questions: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            required: ["id", "prompt"],
            properties: {
              id: { type: "string" },
              prompt: { type: "string" },
              choices: { type: "array", items: { type: "string" } },
              allow_custom: { type: "boolean" },
              multi: { type: "boolean" },
              placeholder: { type: "string" },
            },
          },
        },
      },
    },
  },
  // DEPRECATED (PR4) — createSyllabus / addChapter moved to curriculum-mcp
  // (tool names: getOrCreateSyllabus, addChapter). The agent now writes
  // directly to Supabase and the browser refreshes via realtime subscription.
  // Keeping these as frontend tools shadows the MCP versions and causes the
  // agent to mutate only the local zustand store (no DB persistence).
  // DEPRECATED (PR4) — lesson-mutation tools moved to curriculum-mcp.
  // The agent now writes lessons directly to Supabase via MCP; the browser
  // receives updates through a Supabase realtime subscription.
  // Kept commented here for reference while the migration finishes.
  // {
  //   name: "addLesson",
  //   description: "Append a lesson to an existing chapter. `content` MUST be a BlockNote block array — each item a full block object matching the block schema (type, props, content[]).",
  //   strict: true,
  //   parameters: {
  //     type: "object",
  //     additionalProperties: false,
  //     required: ["chapterId", "lessonId", "title", "content"],
  //     properties: {
  //       chapterId: { type: "string" },
  //       lessonId: { type: "string" },
  //       title: { type: "string" },
  //       content: { type: "array", items: BLOCK_SCHEMA },
  //     },
  //   },
  // },
  // {
  //   name: "updateLessonContent",
  //   description: "Replace the full BlockNote content of an existing lesson. Prefer patchLessonBlocks when only part of a lesson changes.",
  //   strict: true,
  //   parameters: {
  //     type: "object",
  //     additionalProperties: false,
  //     required: ["lessonId", "content"],
  //     properties: {
  //       lessonId: { type: "string" },
  //       content: { type: "array", items: BLOCK_SCHEMA },
  //     },
  //   },
  // },
  // {
  //   name: "appendLessonContent",
  //   description: "Append BlockNote blocks to the end of an existing lesson without removing prior content.",
  //   strict: true,
  //   parameters: {
  //     type: "object",
  //     additionalProperties: false,
  //     required: ["lessonId", "blocks"],
  //     properties: {
  //       lessonId: { type: "string" },
  //       blocks: { type: "array", items: BLOCK_SCHEMA },
  //     },
  //   },
  // },
  // DEPRECATED (PR4) — getSyllabusOutline / readLessonBlocks moved to
  // curriculum-mcp. Same shadowing problem as above: if declared here the
  // agent routes reads through the browser zustand store instead of Supabase.
  // DEPRECATED (PR4) — patchLessonBlocks moved to curriculum-mcp. See git
  // history on branch feat/supabase-mcp-curriculum for the original schema.
  // {
  //   name: "patchLessonBlocks",
  //   description: "Surgical edit of a BlockNote lesson. op='replace' swaps blocks [startBlock..endBlock] with the provided blocks. op='insert' inserts before startBlock (endBlock is ignored, pass null). op='delete' removes [startBlock..endBlock] (blocks is ignored, pass null/[]). Block indices are 1-based and inclusive.",
  //   strict: true,
  //   parameters: { /* ...see git history for full schema... */ },
  // },
  {
    name: "setPlan",
    description: "Replace the thread's task plan. Use this at the start of any non-trivial request to split the work into 3–7 sub-tasks. Status defaults to 'pending' — pass null if you don't want to set it explicitly.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["items"],
      properties: {
        items: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["id", "title", "status"],
            properties: {
              id: { type: ["string", "null"] },
              title: { type: "string" },
              status: {
                type: ["string", "null"],
                enum: ["pending", "in_progress", "done", null],
              },
            },
          },
        },
      },
    },
  },
  {
    name: "updatePlanItem",
    description: "Flip a single plan item's status. Mark the current task 'in_progress' when you start it and 'done' the moment it finishes, before moving on.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["id", "status"],
      properties: {
        id: { type: "string" },
        status: { type: "string", enum: ["pending", "in_progress", "done"] },
      },
    },
  },
] as const;

function messageText(m: AnyMsg): string {
  const c = m?.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    return c
      .map((p: any) => (typeof p === "string" ? p : p?.text ?? ""))
      .filter(Boolean)
      .join("\n");
  }
  if (c == null) return "";
  try { return JSON.stringify(c, null, 2); } catch { return String(c); }
}

type ToolCall = { id?: string; name?: string; args?: Record<string, unknown> };
type ToolStatus = "running" | "completed" | "failed" | "rejected";
type ParsedResult = { raw: string; json: any | null; status: ToolStatus };

function tryParsePartialJSON(s: string): any | null {
  if (!s) return null;
  try { return JSON.parse(s); } catch {}
  let str = s;
  let inStr = false;
  let esc = false;
  let openO = 0, openA = 0;
  for (const c of str) {
    if (esc) { esc = false; continue; }
    if (c === "\\") { esc = true; continue; }
    if (c === '"') { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === "{") openO++;
    else if (c === "}") openO--;
    else if (c === "[") openA++;
    else if (c === "]") openA--;
  }
  if (inStr) str += '"';
  str = str.replace(/[,:]\s*$/, "");
  while (openA-- > 0) str += "]";
  while (openO-- > 0) str += "}";
  try { return JSON.parse(str); } catch { return null; }
}

function getToolCalls(m: AnyMsg): ToolCall[] {
  const full = ((m.tool_calls as any[]) || []) as ToolCall[];
  const chunks = ((m as any).tool_call_chunks as any[] | undefined) || [];
  if (!chunks.length) return full;
  // Merge: prefer fully-parsed `tool_calls` when args are non-empty;
  // otherwise reconstruct a partial args object from the streaming chunks
  // so the UI can render arguments as they arrive instead of waiting for
  // the model to close the JSON blob.
  const merged = new Map<string, ToolCall>();
  full.forEach((tc, i) => merged.set(tc.id ?? `__i${i}`, { ...tc }));
  chunks.forEach((ch: any, i: number) => {
    const key = ch.id ?? `__i${ch.index ?? i}`;
    const existing = merged.get(key) ?? {};
    const existingArgs = (existing.args ?? {}) as Record<string, unknown>;
    const hasFullArgs = existingArgs && Object.keys(existingArgs).length > 0;
    const partial = hasFullArgs ? existingArgs : (tryParsePartialJSON(ch.args ?? "") ?? existingArgs);
    merged.set(key, {
      id: existing.id ?? ch.id,
      name: existing.name ?? ch.name,
      args: partial,
    });
  });
  return Array.from(merged.values());
}

function getMessageError(m: AnyMsg): { message?: string; type?: string } | null {
  const ak: any = (m as any).additional_kwargs ?? (m as any).additionalKwargs;
  const err = ak?.error;
  if (!err) return null;
  if (typeof err === "string") return { message: err };
  return { message: err.message, type: err.type };
}

// Classify the lifecycle of a tool call from its matching ToolMessage.
function parseResult(raw: string | undefined, isLastAssistant: boolean, isStreaming: boolean): ParsedResult {
  if (raw === undefined) {
    // No matching ToolMessage yet. If this assistant message is the live tail
    // of an in-flight run, the tool is still streaming its args / executing.
    const status: ToolStatus = "running";
    void isLastAssistant; void isStreaming;
    return { raw: "", json: null, status };
  }
  let json: any = null;
  try { json = JSON.parse(raw); } catch { /* plain text result */ }
  let status: ToolStatus = "completed";
  if (json && typeof json === "object") {
    if (json.ok === false) {
      status = json.error === "user_rejected" ? "rejected" : "failed";
    }
  }
  return { raw, json, status };
}

// ── Per-tool pretty renderers ────────────────────────────────────────────
// Each returns a small React node rendered inside the tool call card. The
// default renderer shows a compact JSON preview.

function ToolStatusBadge({ status }: { status: ToolStatus }) {
  const cfg: Record<ToolStatus, { label: string; icon: any; cls: string }> = {
    running:   { label: "running",   icon: Loader2,     cls: "border-[var(--primary)]/40 bg-[var(--primary)]/10 text-[var(--primary)]" },
    completed: { label: "completed", icon: CheckCircle2, cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-500" },
    failed:    { label: "failed",    icon: XCircle,      cls: "border-[var(--destructive)]/40 bg-[var(--destructive)]/10 text-[var(--destructive)]" },
    rejected:  { label: "rejected",  icon: Ban,          cls: "border-amber-500/40 bg-amber-500/10 text-amber-500" },
  };
  const c = cfg[status];
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${c.cls}`}>
      <Icon className={`h-3 w-3 ${status === "running" ? "animate-spin" : ""}`} />
      {c.label}
    </span>
  );
}

const TOOL_META: Record<string, { label: string; icon: any; tone: string }> = {
  createSyllabus:      { label: "Create syllabus",      icon: BookOpen,  tone: "text-sky-400" },
  addChapter:          { label: "Add chapter",          icon: Layers,    tone: "text-indigo-400" },
  addLesson:           { label: "Add lesson",           icon: FileText,  tone: "text-emerald-400" },
  updateLessonContent: { label: "Rewrite lesson",       icon: Pencil,    tone: "text-amber-400" },
  appendLessonContent: { label: "Append to lesson",     icon: Pencil,    tone: "text-amber-400" },
  patchLessonBlocks:   { label: "Patch lesson blocks",  icon: Pencil,    tone: "text-amber-400" },
  getSyllabusOutline:  { label: "Read outline",         icon: Eye,       tone: "text-[var(--muted-foreground)]" },
  readLessonBlocks:    { label: "Read lesson blocks",   icon: Eye,       tone: "text-[var(--muted-foreground)]" },
  setPlan:             { label: "Plan",                 icon: ListTodo,  tone: "text-[var(--primary)]" },
  updatePlanItem:      { label: "Update plan item",     icon: ListTodo,  tone: "text-[var(--primary)]" },
  task:                { label: "Dispatch subagent",    icon: Users,     tone: "text-fuchsia-400" },
  askUser:             { label: "Ask user",              icon: Wrench,    tone: "text-[var(--primary)]" },
};

function subagentIcon(name: string | null | undefined) {
  switch (name) {
    case "researcher": return Eye;
    case "writer":     return Pencil;
    case "reviser":    return Sparkles;
    default:           return Bot;
  }
}

function subagentTone(name: string | null | undefined) {
  switch (name) {
    case "researcher": return "text-sky-400";
    case "writer":     return "text-emerald-400";
    case "reviser":    return "text-amber-400";
    default:           return "text-fuchsia-400";
  }
}

function toolMeta(name: string | undefined) {
  if (!name) return { label: "Tool", icon: Wrench, tone: "text-[var(--muted-foreground)]" };
  return TOOL_META[name] ?? { label: name, icon: Wrench, tone: "text-[var(--muted-foreground)]" };
}

// Short plain-text snippet from a BlockNote block array (first ~N chars).
function previewBlocks(blocks: any[] | undefined, max = 160): string {
  if (!Array.isArray(blocks)) return "";
  const text = blocks
    .map((b: any) => {
      const c = b?.content;
      if (typeof c === "string") return c;
      if (Array.isArray(c)) return c.map((r: any) => r?.text ?? "").join("");
      return "";
    })
    .filter(Boolean)
    .join(" • ");
  return text.length > max ? text.slice(0, max) + "…" : text;
}

type PlanStatusToken = "todo" | "in_progress" | "done" | string;
function PlanItemsPreview({ items }: { items: Array<{ id?: string; title?: string; status?: PlanStatusToken }> }) {
  if (!items?.length) return <div className="text-[11px] text-[var(--muted-foreground)]">empty plan</div>;
  return (
    <ul className="space-y-1">
      {items.map((it, i) => {
        const s = it.status ?? "todo";
        const Icon =
          s === "done" ? CheckCircle2 : s === "in_progress" ? Loader2 : Circle;
        const cls =
          s === "done"
            ? "text-emerald-500"
            : s === "in_progress"
            ? "text-[var(--primary)]"
            : "text-[var(--muted-foreground)]";
        return (
          <li key={it.id ?? i} className="flex items-start gap-2 text-[12px]">
            <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${cls} ${s === "in_progress" ? "animate-spin" : ""}`} />
            <span className={s === "done" ? "line-through text-[var(--muted-foreground)]" : "text-[var(--foreground)]"}>
              {it.title ?? "(untitled task)"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function KV({ k, v }: { k: string; v: string | undefined }) {
  if (!v) return null;
  return (
    <div className="flex gap-2 text-[12px]">
      <span className="font-mono text-[var(--muted-foreground)] min-w-[72px]">{k}</span>
      <span className="whitespace-pre-wrap break-words text-[var(--foreground)]">{v}</span>
    </div>
  );
}

function ToolArgsView({ name, args }: { name: string; args: Record<string, any> }) {
  const a = args ?? {};
  switch (name) {
    case "setPlan":
      return <PlanItemsPreview items={a.items ?? []} />;
    case "updatePlanItem":
      return (
        <div className="flex items-center gap-2 text-[12px]">
          <span className="font-mono text-[var(--muted-foreground)]">{a.id}</span>
          <span className="text-[var(--muted-foreground)]">→</span>
          <span className="font-medium text-[var(--foreground)]">{a.status}</span>
        </div>
      );
    case "createSyllabus":
      return (
        <div className="space-y-0.5">
          <KV k="title" v={a.title} />
          <KV k="subject" v={a.subject} />
          <KV k="description" v={a.description} />
        </div>
      );
    case "addChapter":
      return (
        <div className="space-y-0.5">
          <KV k="title" v={a.title} />
          <KV k="description" v={a.description} />
        </div>
      );
    case "addLesson": {
      const preview = previewBlocks(a.content);
      const count = Array.isArray(a.content) ? a.content.length : 0;
      return (
        <div className="space-y-1">
          <KV k="title" v={a.title} />
          <div className="text-[11px] text-[var(--muted-foreground)]">
            {count} block{count === 1 ? "" : "s"}
          </div>
          {preview && (
            <div className="rounded bg-[var(--muted)]/50 p-1.5 text-[11px] italic text-[var(--muted-foreground)]">
              {preview}
            </div>
          )}
        </div>
      );
    }
    case "updateLessonContent":
    case "appendLessonContent": {
      const blocks = a.content ?? a.blocks;
      const count = Array.isArray(blocks) ? blocks.length : 0;
      const preview = previewBlocks(blocks);
      return (
        <div className="space-y-1">
          <KV k="lesson" v={a.lessonId} />
          <div className="text-[11px] text-[var(--muted-foreground)]">
            {count} block{count === 1 ? "" : "s"}
          </div>
          {preview && (
            <div className="rounded bg-[var(--muted)]/50 p-1.5 text-[11px] italic text-[var(--muted-foreground)]">
              {preview}
            </div>
          )}
        </div>
      );
    }
    case "patchLessonBlocks": {
      const count = Array.isArray(a.blocks) ? a.blocks.length : 0;
      return (
        <div className="space-y-0.5 text-[12px]">
          <KV k="lesson" v={a.lessonId} />
          <KV k="op" v={a.op} />
          <KV k="range" v={a.startBlock ? `${a.startBlock}${a.endBlock ? " → " + a.endBlock : ""}` : undefined} />
          <div className="text-[11px] text-[var(--muted-foreground)]">{count} new block{count === 1 ? "" : "s"}</div>
        </div>
      );
    }
    case "getSyllabusOutline":
      return <div className="text-[12px] text-[var(--muted-foreground)]">Reading outline{a.syllabusId ? ` of ${a.syllabusId}` : ""}…</div>;
    case "readLessonBlocks":
      return (
        <div className="text-[12px] text-[var(--muted-foreground)]">
          Reading lesson {a.lessonId}
          {a.startBlock ? ` · ${a.startBlock}${a.endBlock ? "–" + a.endBlock : ""}` : ""}
        </div>
      );
    default:
      return (
        <pre className="whitespace-pre-wrap break-all rounded bg-[var(--muted)]/50 p-1.5 text-[11px] font-mono text-[var(--muted-foreground)]">
          {JSON.stringify(a, null, 2).slice(0, 600)}
        </pre>
      );
  }
}

function ToolResultView({ name, result }: { name: string; result: ParsedResult }) {
  if (!result.raw) return null;
  const payload = result.json;
  if (result.status === "failed" || result.status === "rejected") {
    const msg = payload?.error ?? payload?.message ?? result.raw;
    return (
      <div className="rounded border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 p-1.5 text-[11px] text-[var(--destructive)]">
        {String(msg).slice(0, 300)}
      </div>
    );
  }
  const short =
    name === "getSyllabusOutline" || name === "readLessonBlocks"
      ? (result.raw.length > 240 ? result.raw.slice(0, 240) + "…" : result.raw)
      : null;
  if (!short) return null;
  return (
    <div className="text-[11px] font-mono text-[var(--muted-foreground)]">
      <span className="text-[var(--primary)]">→</span> {short}
    </div>
  );
}

const ToolCallCard = memo(function ToolCallCard({
  call,
  result,
  subagentMessages,
  toolResults,
  isStreaming,
}: {
  call: ToolCall;
  result: ParsedResult;
  subagentMessages?: AnyMsg[];
  toolResults?: Map<string, string>;
  isStreaming?: boolean;
}) {
  const isTask = call.name === "task";
  const args = (call.args as Record<string, any>) ?? {};
  const subagentName = isTask ? (args.subagent_type as string | undefined) ?? null : null;
  const description = isTask ? (args.description as string | undefined) ?? "" : "";
  const subMsgs = subagentMessages ?? [];
  const running = result.status === "running";
  // Auto-open while the task subagent is running, auto-close when it completes.
  const [open, setOpen] = useState<boolean>(isTask ? running : false);
  const prevRunning = useRef(running);
  useEffect(() => {
    if (!isTask) return;
    if (prevRunning.current && !running) setOpen(false);
    if (!prevRunning.current && running) setOpen(true);
    prevRunning.current = running;
  }, [isTask, running]);

  const SubIcon = isTask ? subagentIcon(subagentName) : null;
  const meta = toolMeta(call.name);
  const Icon = meta.icon;

  if (isTask) {
    const tone = subagentTone(subagentName);
    const label = subagentName
      ? subagentName.charAt(0).toUpperCase() + subagentName.slice(1)
      : "Subagent";
    return (
      <div
        className={`rounded-md border bg-[var(--background)]/60 ${
          running
            ? "border-[var(--primary)]/50 shadow-[0_0_0_1px_var(--primary)]/10"
            : "border-[var(--border)]"
        }`}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-start gap-2 px-2.5 py-2 text-left hover:bg-[var(--muted)]/40 transition-colors"
        >
          {open ? <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted-foreground)]" /> : <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted-foreground)]" />}
          <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--muted)]/60 ${tone}`}>
            {SubIcon ? <SubIcon className={`h-3.5 w-3.5 ${running ? "animate-pulse" : ""}`} /> : null}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={`text-[12px] font-semibold ${tone}`}>{label}</span>
              <span className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">subagent</span>
              {running && (
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--primary)]/40 bg-[var(--primary)]/10 px-1.5 py-0.5 text-[9px] font-medium text-[var(--primary)]">
                  <Loader2 className="h-2.5 w-2.5 animate-spin" />
                  thinking
                </span>
              )}
              {!running && subMsgs.length > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--muted)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--muted-foreground)]">
                  {subMsgs.length} msg{subMsgs.length === 1 ? "" : "s"}
                </span>
              )}
              <span className="ml-auto"><ToolStatusBadge status={result.status} /></span>
            </div>
            {description && (
              <div className="mt-0.5 line-clamp-2 text-[11px] text-[var(--muted-foreground)]">
                {description}
              </div>
            )}
          </div>
        </button>
        {open && (
          <div className="border-t border-[var(--border)] bg-[var(--muted)]/20 px-2.5 py-2 space-y-2">
            {subMsgs.length === 0 ? (
              <div className="flex items-center gap-2 text-[11px] text-[var(--muted-foreground)] italic">
                {running ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Waiting for {label} to think…
                  </>
                ) : (
                  <>No streamed messages captured for this run.</>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                {subMsgs.map((sm, i) => (
                  <SubagentTrace
                    key={(sm.id as string) ?? `sub-${i}`}
                    m={sm}
                    toolResults={toolResults ?? new Map()}
                    isStreaming={!!isStreaming}
                  />
                ))}
              </div>
            )}
            {!running && result.raw && (
              <details className="pt-1 border-t border-[var(--border)]/70">
                <summary className="cursor-pointer select-none text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                  Final summary returned to supervisor
                </summary>
                <div className="mt-1.5">
                  <ToolResultView name={call.name ?? ""} result={result} />
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--background)]/50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-[var(--muted)]/40 transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3 shrink-0 text-[var(--muted-foreground)]" /> : <ChevronRight className="h-3 w-3 shrink-0 text-[var(--muted-foreground)]" />}
        <Icon className={`h-3.5 w-3.5 shrink-0 ${meta.tone}`} />
        <span className="flex-1 min-w-0 truncate text-[12px] font-medium text-[var(--foreground)]">
          {meta.label}
        </span>
        <ToolStatusBadge status={result.status} />
      </button>
      {open && (
        <div className="border-t border-[var(--border)] px-2 py-2 space-y-2">
          <ToolArgsView name={call.name ?? ""} args={(call.args as Record<string, any>) ?? {}} />
          <ToolResultView name={call.name ?? ""} result={result} />
        </div>
      )}
    </div>
  );
});

/**
 * Compact bubble used INSIDE a Task tool card to render a single streamed
 * message from a subagent (researcher/writer/reviser). Differs from the
 * top-level MessageBubble in that it is denser, does not re-emit the
 * "live · subagent" badge (the parent card already shows that context),
 * and renders nested tool calls without letting them escape the card.
 */
const SubagentTrace = memo(function SubagentTrace({
  m,
  toolResults,
  isStreaming,
}: {
  m: AnyMsg;
  toolResults: Map<string, string>;
  isStreaming: boolean;
}) {
  const role = m.type ?? m.role;
  if (role === "tool" || role === "human" || role === "user") return null;
  const text = messageText(m);
  const calls = getToolCalls(m);
  if (!text && !calls.length) return null;
  const sub = subagentOrigin(m);
  const Icon = subagentIcon(sub);
  const tone = subagentTone(sub);
  return (
    <div className="flex gap-2">
      <div className={`mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--background)] ${tone}`}>
        <Icon className="h-3 w-3" />
      </div>
      <div className="flex-1 min-w-0 rounded border border-[var(--border)]/70 bg-[var(--background)]/70 px-2 py-1.5">
        {text ? <Markdown source={text} /> : null}
        {calls.length > 0 && (
          <ToolCallTimeline
            calls={calls}
            results={toolResults}
            isLastAssistant={false}
            isStreaming={isStreaming}
          />
        )}
      </div>
    </div>
  );
});

const ToolCallTimeline = memo(function ToolCallTimeline({
  calls,
  results,
  isLastAssistant,
  isStreaming,
  subagentsByTaskCallId,
}: {
  calls: ToolCall[];
  results: Map<string, string>;
  isLastAssistant: boolean;
  isStreaming: boolean;
  subagentsByTaskCallId?: Map<string, AnyMsg[]>;
}) {
  if (!calls.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {calls.map((tc, idx) => {
        const raw = tc.id ? results.get(tc.id) : undefined;
        const result = parseResult(raw, isLastAssistant, isStreaming);
        const subMsgs = tc.name === "task" && tc.id
          ? subagentsByTaskCallId?.get(tc.id) ?? []
          : undefined;
        return (
          <ToolCallCard
            key={tc.id ?? idx}
            call={tc}
            result={result}
            subagentMessages={subMsgs}
            toolResults={results}
            isStreaming={isStreaming}
          />
        );
      })}
    </div>
  );
});

/**
 * Detect a message that originated inside a deepagents subagent subgraph
 * so we can render it with a distinct "live · subagent" badge. These
 * messages arrive via `streamSubgraphs: true` while the subagent is
 * running and are NOT persisted into parent state — deepagents only
 * writes the task tool's final summary back to the supervisor. Once the
 * run ends useStream re-syncs with server state and the ephemeral
 * entries drop out of the thread naturally.
 */
function subagentOrigin(m: AnyMsg): string | null {
  // Detect that a streamed message originated inside a nested subgraph
  // (i.e. a deepagents `task(...)` subagent), so the grouper can hide it
  // from the main supervisor chat and attach it to the matching task
  // tool-call card.
  //
  // LangGraph's subgraph namespace shows up under different keys across
  // SDK versions / providers. We check every place we've seen it appear.
  const mk = (m as any).additional_kwargs ?? {};
  const rm = (m as any).response_metadata ?? {};
  const nsCandidates: Array<unknown> = [
    rm.langgraph_checkpoint_ns,
    mk.langgraph_checkpoint_ns,
    rm.checkpoint_ns,
    mk.checkpoint_ns,
    (m as any).langgraph_checkpoint_ns,
    (m as any).checkpoint_ns,
    rm.langgraph_path,
    mk.langgraph_path,
  ];
  const ns = nsCandidates.find((v): v is string => typeof v === "string" && v.length > 0);
  const KNOWN = /^(researcher|writer|reviser|general-purpose)$/;
  if (ns) {
    // Canonical deepagents layout: `task:<call_id>|<subagent_name>:<cp>`.
    // But langgraph may also emit just `<subagent_name>:<cp>` or deeper
    // `|`-separated chains — walk the segments right-to-left and pick the
    // first recognised subagent name.
    const segments = ns.split("|");
    for (let i = segments.length - 1; i >= 0; i--) {
      const head = segments[i].split(":")[0];
      if (head && KNOWN.test(head)) return head;
    }
    // Non-empty nested namespace but no recognised subagent name: the
    // message still came from a subgraph (anything non-empty here means
    // we're NOT on the root graph), so bucket it under a generic marker
    // and let the grouper attach it to the most recent open task call.
    if (segments.length > 1 || ns.includes(":")) return "__subagent__";
  }
  const node: string | undefined = rm.langgraph_node ?? mk.langgraph_node;
  if (node && KNOWN.test(node)) return node;
  // Fallback: messages produced by `create_agent(name="researcher", ...)`
  // carry that name on the AIMessage itself.
  const msgName = (m as any).name;
  if (typeof msgName === "string" && KNOWN.test(msgName)) return msgName;
  return null;
}

const MessageBubble = memo(function MessageBubble({
  m,
  toolResults,
  isLastAssistant,
  isStreaming,
  subagentsByTaskCallId,
}: {
  m: AnyMsg;
  toolResults: Map<string, string>;
  isLastAssistant: boolean;
  isStreaming: boolean;
  subagentsByTaskCallId?: Map<string, AnyMsg[]>;
}) {
  const role = m.type ?? m.role;
  const isUser = role === "human" || role === "user";
  const isTool = role === "tool";
  if (isTool) return null;
  const text = messageText(m);
  const calls = getToolCalls(m);
  const msgError = getMessageError(m);
  if (!text && !calls.length && !msgError) return null;
  const sub = subagentOrigin(m);
  return (
    <div
      className={`rounded-md px-3 py-2 ${
        isUser
          ? "bg-[var(--primary)]/10 border border-[var(--primary)]/30 text-[var(--foreground)]"
          : msgError
          ? "bg-[var(--muted)] border border-[var(--destructive)]/40 text-[var(--foreground)]"
          : sub
          ? "bg-[var(--muted)]/40 border border-dashed border-[var(--primary)]/40 text-[var(--foreground)]"
          : "bg-[var(--muted)] text-[var(--foreground)]"
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] flex items-center gap-1.5">
          {isUser ? "You" : "Agent"}
          {sub && (
            <span
              title="Streaming from a deepagents subagent — not persisted to the thread."
              className="inline-flex items-center gap-1 rounded border border-[var(--primary)]/40 bg-[var(--primary)]/10 px-1.5 py-0.5 text-[9px] font-medium text-[var(--primary)] normal-case tracking-normal"
            >
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              live · {sub}
            </span>
          )}
        </div>
        {msgError && (
          <span
            className="inline-flex items-center gap-1 rounded border border-[var(--destructive)]/40 bg-[var(--destructive)]/10 px-1.5 py-0.5 text-[10px] font-medium text-[var(--destructive)]"
            title={msgError.message ?? msgError.type ?? "error"}
          >
            <AlertCircle className="h-3 w-3" />
            {msgError.type ?? "error"}
          </span>
        )}
      </div>
      {text ? (
        isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed text-sm">{text}</div>
        ) : (
          <Markdown source={text} />
        )
      ) : null}
      {calls.length > 0 && <ToolCallTimeline calls={calls} results={toolResults} isLastAssistant={isLastAssistant} isStreaming={isStreaming} subagentsByTaskCallId={subagentsByTaskCallId} />}
    </div>
  );
});

function visibleKey(m: AnyMsg, i: number): string {
  return (m.id as string) ?? `${m.type ?? m.role ?? "m"}-${i}`;
}

// ── Runtime validation for frontend tool-call arguments ──────────────────
// The agent's OpenAI function schemas are strict, but MCP / non-strict tools
// (or a stale deployment) can still emit calls whose args don't match the
// declared shape. Rendering those blindly can crash React (e.g. calling
// `.every` / `.map` on a non-array). We validate defensively in the browser,
// and if the args are malformed we auto-resume the interrupt with a
// descriptive error so the agent sees the failure and can re-emit the call
// with correct arguments — instead of the UI hard-crashing with a cryptic
// "d.every is not a function".
function validateFrontendToolArgs(name: string, args: unknown): string | null {
  const a = (args ?? {}) as any;
  if (typeof a !== "object" || a === null || Array.isArray(a)) {
    return `${name} args must be a JSON object, got ${Array.isArray(args) ? "array" : typeof args}`;
  }
  switch (name) {
    case "askUser": {
      if (!Array.isArray(a.questions)) {
        return (
          "askUser.questions must be an array of " +
          "{id:string, prompt:string, choices?:string[], allow_custom?:boolean, multi?:boolean, placeholder?:string}, " +
          `got ${a.questions === undefined ? "undefined" : typeof a.questions}`
        );
      }
      if (a.questions.length === 0) {
        return "askUser.questions must contain at least one question";
      }
      for (let i = 0; i < a.questions.length; i++) {
        const q = a.questions[i];
        if (!q || typeof q !== "object" || Array.isArray(q)) {
          return `askUser.questions[${i}] must be an object`;
        }
        if (typeof q.id !== "string" || q.id.length === 0) {
          return `askUser.questions[${i}].id must be a non-empty string`;
        }
        if (typeof q.prompt !== "string" || q.prompt.length === 0) {
          return `askUser.questions[${i}].prompt must be a non-empty string`;
        }
        if (q.choices !== undefined && q.choices !== null) {
          if (!Array.isArray(q.choices)) {
            return `askUser.questions[${i}].choices must be an array of strings`;
          }
          for (let j = 0; j < q.choices.length; j++) {
            if (typeof q.choices[j] !== "string") {
              return `askUser.questions[${i}].choices[${j}] must be a string`;
            }
          }
        }
        if (q.multi !== undefined && q.multi !== null && typeof q.multi !== "boolean") {
          return `askUser.questions[${i}].multi must be a boolean`;
        }
        if (q.allow_custom !== undefined && q.allow_custom !== null && typeof q.allow_custom !== "boolean") {
          return `askUser.questions[${i}].allow_custom must be a boolean`;
        }
        if (q.placeholder !== undefined && q.placeholder !== null && typeof q.placeholder !== "string") {
          return `askUser.questions[${i}].placeholder must be a string`;
        }
      }
      return null;
    }
    case "setPlan": {
      if (!Array.isArray(a.items)) {
        return `setPlan.items must be an array of plan items, got ${a.items === undefined ? "undefined" : typeof a.items}`;
      }
      for (let i = 0; i < a.items.length; i++) {
        const it = a.items[i];
        if (!it || typeof it !== "object" || Array.isArray(it)) {
          return `setPlan.items[${i}] must be an object`;
        }
        if (typeof it.title !== "string" || it.title.length === 0) {
          return `setPlan.items[${i}].title must be a non-empty string`;
        }
        if (it.status !== undefined && it.status !== null && typeof it.status !== "string") {
          return `setPlan.items[${i}].status must be a string ('pending' | 'in_progress' | 'done')`;
        }
      }
      return null;
    }
    case "updatePlanItem": {
      if (typeof a.id !== "string" || a.id.length === 0) {
        return "updatePlanItem.id must be a non-empty string";
      }
      if (typeof a.status !== "string" || a.status.length === 0) {
        return "updatePlanItem.status must be a non-empty string ('pending' | 'in_progress' | 'done')";
      }
      return null;
    }
    default:
      return null;
  }
}


type FrontendToolCall = {
  type: "frontend_tool_call";
  tool_call_id: string;
  name: string;
  args: Record<string, unknown>;
};

function InterruptCard({
  call,
  busy,
  onApprove,
  onReject,
}: {
  call: FrontendToolCall;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const entries = Object.entries(call.args ?? {});
  return (
    <div className="mx-3 my-2 rounded-md border border-[var(--primary)]/50 bg-[var(--primary)]/5 px-3 py-3 text-sm">
      <div className="flex items-center gap-2 mb-2">
        <Wrench className="h-4 w-4 text-[var(--primary)]" />
        <span className="font-medium">Agent wants to call</span>
        <code className="font-mono text-xs bg-[var(--muted)] px-1.5 py-0.5 rounded">{call.name}</code>
      </div>
      {entries.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--background)]/50 p-2 mb-3 space-y-1">
          {entries.map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs">
              <span className="font-mono text-[var(--muted-foreground)] min-w-[90px]">{k}</span>
              <span className="font-mono break-all whitespace-pre-wrap">
                {typeof v === "string" ? v : JSON.stringify(v, null, 2)}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onReject}
          disabled={busy}
          className="px-3 py-1 text-xs rounded border border-[var(--border)] hover:bg-[var(--muted)] disabled:opacity-50"
        >
          Reject
        </button>
        <button
          type="button"
          onClick={onApprove}
          disabled={busy}
          className="px-3 py-1 text-xs rounded bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Approve & run
        </button>
      </div>
    </div>
  );
}



type AskUserQuestion = {
  id: string;
  prompt: string;
  choices?: string[];
  allow_custom?: boolean;
  multi?: boolean;
  placeholder?: string;
};

function AskUserCard({
  call,
  busy,
  onSubmit,
  onReject,
}: {
  call: FrontendToolCall;
  busy: boolean;
  onSubmit: (answers: Record<string, string | string[]>) => void;
  onReject: () => void;
}) {
  // Defensive: if the agent emitted malformed args (e.g. `questions` as a
  // string, object, null, or missing entirely), fall back to an empty array
  // so the component never crashes with `d.every is not a function`. The
  // validation effect in ChatPaneBody will still auto-reject the tool call
  // back to the agent with a descriptive error so it can retry.
  const rawQuestions = (call.args as any)?.questions;
  const questions: AskUserQuestion[] = Array.isArray(rawQuestions)
    ? (rawQuestions.filter(
        (q: any) =>
          q &&
          typeof q === "object" &&
          typeof q.id === "string" &&
          typeof q.prompt === "string",
      ) as AskUserQuestion[])
    : [];
  const [picks, setPicks] = useState<Record<string, string[]>>({});
  const [customs, setCustoms] = useState<Record<string, string>>({});

  const setPick = (q: AskUserQuestion, choice: string) => {
    setPicks((p) => {
      const cur = p[q.id] ?? [];
      if (q.multi) {
        const next = cur.includes(choice) ? cur.filter((x) => x !== choice) : [...cur, choice];
        return { ...p, [q.id]: next };
      }
      return { ...p, [q.id]: [choice] };
    });
    setCustoms((cs) => ({ ...cs, [q.id]: "" }));
  };
  const setCustom = (q: AskUserQuestion, text: string) => {
    setCustoms((cs) => ({ ...cs, [q.id]: text }));
    if (text) setPicks((p) => ({ ...p, [q.id]: [] }));
  };

  const allAnswered = questions.every((q) => {
    const pk = picks[q.id] ?? [];
    const ct = (customs[q.id] ?? "").trim();
    return pk.length > 0 || ct.length > 0;
  });

  const submit = () => {
    const out: Record<string, string | string[]> = {};
    for (const q of questions) {
      const pk = picks[q.id] ?? [];
      const ct = (customs[q.id] ?? "").trim();
      if (ct) out[q.id] = ct;
      else if (q.multi) out[q.id] = pk;
      else out[q.id] = pk[0] ?? "";
    }
    onSubmit(out);
  };

  return (
    <div className="mx-3 my-2 rounded-md border border-[var(--primary)]/50 bg-[var(--primary)]/5 px-3 py-3 text-sm">
      <div className="flex items-center gap-2 mb-3">
        <Wrench className="h-4 w-4 text-[var(--primary)]" />
        <span className="font-medium">The agent has a few quick questions</span>
      </div>
      <div className="space-y-4">
        {questions.map((q) => {
          const pk = picks[q.id] ?? [];
          const ct = customs[q.id] ?? "";
          return (
            <div key={q.id} className="space-y-1.5">
              <div className="text-[13px] font-medium text-[var(--foreground)]">{q.prompt}</div>
              {Array.isArray(q.choices) && q.choices.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {q.choices.map((ch) => {
                    const active = pk.includes(ch);
                    return (
                      <button
                        type="button"
                        key={ch}
                        onClick={() => setPick(q, ch)}
                        disabled={busy}
                        className={
                          "px-2.5 py-1 text-xs rounded-full border transition-colors " +
                          (active
                            ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)]"
                            : "border-[var(--border)] hover:bg-[var(--muted)]")
                        }
                      >
                        {ch}
                      </button>
                    );
                  })}
                </div>
              )}
              {(q.allow_custom ?? true) && (
                <input
                  type="text"
                  value={ct}
                  onChange={(e) => setCustom(q, e.target.value)}
                  disabled={busy}
                  placeholder={q.placeholder ?? "Or type your own answer…"}
                  className="w-full rounded border border-[var(--border)] bg-[var(--background)] px-2 py-1 text-xs outline-none focus:border-[var(--ring)]"
                />
              )}
            </div>
          );
        })}
      </div>
      <div className="flex gap-2 justify-end mt-3">
        <button
          type="button"
          onClick={onReject}
          disabled={busy}
          className="px-3 py-1 text-xs rounded border border-[var(--border)] hover:bg-[var(--muted)] disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={busy || !allAnswered}
          className="px-3 py-1 text-xs rounded bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Submit answers
        </button>
      </div>
    </div>
  );
}

function ChatPaneBody({ bumpEpoch }: { bumpEpoch: () => void }) {
  const [threadIdParam, setThreadIdParam] = useQueryState("threadId");
  const activeFromStore = useThreadStore((s) => s.activeThreadId);
  const setActive = useThreadStore((s) => s.setActiveThread);
  const { refreshThreads } = useThreads();

  const threadId = threadIdParam ?? activeFromStore;

  useEffect(() => {
    if (threadIdParam && threadIdParam !== activeFromStore) {
      setActive(threadIdParam);
    }
  }, [threadIdParam, activeFromStore, setActive]);

  // Bind the syllabus store to the active thread so each thread gets its own
  // file tree, syllabi, and lesson state.
  const setCurrentSyllabusThread = useSyllabusStore((s) => s.setCurrentThread);
  useEffect(() => {
    setCurrentSyllabusThread(threadId ?? null);
  }, [threadId, setCurrentSyllabusThread]);

  // Subscribe to realtime updates for the currently open thread so the
  // user sees the agent's writes as they happen (PR4).
  useSyllabusRealtime(threadId ?? null);

  const setCurrentPlanThread = usePlanStore((s) => s.setCurrentThread);
  useEffect(() => {
    setCurrentPlanThread(threadId ?? null);
  }, [threadId, setCurrentPlanThread]);

  // Per-thread settings (auto-accept etc). We subscribe to the slice for the
  // active thread so the UI re-renders when it flips.
  // PR5: default auto-accept to true so the graph flows end-to-end. Users
  // can still toggle it per-thread from the footer.
  const autoAccept = useThreadSettingsStore((s) =>
    threadId ? s.byThread[threadId]?.autoAccept ?? true : true
  );
  const toggleAutoAccept = useThreadSettingsStore((s) => s.toggleAutoAccept);
  const clearThreadSettings = useThreadSettingsStore((s) => s.clearThread);

  // If the URL points at a thread that no longer exists on the server, bounce
  // the user back to the landing state and surface a small sonner toast.
  const { getThread } = useThreads();
  const checkedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!threadIdParam) return;
    if (checkedRef.current === threadIdParam) return;
    checkedRef.current = threadIdParam;
    let cancelled = false;
    (async () => {
      const t = await getThread(threadIdParam);
      if (cancelled) return;
      if (!t) {
        toast.error("Thread not found", {
          description: "That conversation no longer exists. Returning to a fresh chat.",
        });
        void setThreadIdParam(null);
        setActive(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [threadIdParam, getThread, setThreadIdParam, setActive]);

  const handleThreadId = useCallback(
    (id: string) => {
      void setThreadIdParam(id);
      setActive(id);
      void refreshThreads();
    },
    [setThreadIdParam, setActive, refreshThreads]
  );

  // Resolve the current thread's locked agent variant from its metadata.
  // The "variant for next thread" picker in ThreadHistory only affects
  // thread creation — an existing thread always keeps its original variant.
  const { threads: _allThreads } = useThreads();
  const currentThread = threadId ? _allThreads.find((x: any) => x.thread_id === threadId) : null;
  const activeVariant = threadVariant(currentThread as any);
  const stream = useSyllabusAgent({
    threadId: threadId ?? undefined,
    onThreadId: handleThreadId,
    variant: activeVariant,
  });
  const [input, setInput] = useState("");

  // Server-side thread status. On page reload / network drop, `stream.isLoading`
  // is false until the SSE rejoins and the first token arrives — but the run
  // may still be executing on the server. Polling the thread status while we
  // are NOT locally streaming lets the UI reflect real busy state immediately
  // (disables Send, swaps to Stop, shows "Rejoining run…"). While we ARE
  // streaming locally, polling is disabled to avoid redundant requests.
  const localStreaming = stream.isLoading;
  const { status: threadStatus, mutate: refreshThreadStatus } = useThreadStatus(
    threadId,
    localStreaming ? 0 : 4000,
  );
  const serverBusy = threadStatus === "busy";
  const isStreaming = localStreaming || serverBusy;
  const store = useSyllabusStore();
  const plan = usePlanStore();
  const cancel = useCancelStream();

  const messages = (stream.messages ?? []) as AnyMsg[];

  // Deep variant uses deepagents' built-in `write_todos` tool which writes
  // into `state.todos` (not into `plan-store`). Mirror that array into the
  // existing plan-store whenever it changes so <PlanStrip/> renders one
  // live plan for both classic and deep variants without forking the UI.
  const streamedTodos = ((stream as any).values?.todos ?? null) as
    | Array<{ id?: string; content?: string; status?: string }>
    | null;
  // Signature-based change detection. We do NOT put `plan` in the dep
  // array because `usePlanStore()` returns a new object on every store
  // update — setPlan below mutates the store, which would re-run this
  // effect, which would setPlan again, which would unmount the tree
  // ("Application error: a client-side exception has occurred").
  // Instead compute a stable signature of the incoming todos and skip
  // the dispatch entirely when nothing meaningful changed.
  const todosSignature = useMemo(() => {
    if (!Array.isArray(streamedTodos)) return null;
    return streamedTodos
      .map((t, i) => `${t?.id ?? i}:${(t?.status ?? "pending")}:${(t?.content ?? "").slice(0, 120)}`)
      .join("|");
  }, [streamedTodos]);
  useEffect(() => {
    if (activeVariant !== "deep") return;
    if (todosSignature === null) return;
    if (!Array.isArray(streamedTodos)) return;
    const normalized = streamedTodos.map((t, i) => {
      const raw = (t?.status ?? "pending").toString();
      const status =
        raw === "completed" || raw === "done"
          ? "done"
          : raw === "in_progress"
          ? "in_progress"
          : "pending";
      return {
        id: t?.id ?? `deep-todo-${i}`,
        title: String(t?.content ?? "").trim() || `Task ${i + 1}`,
        status: status as "pending" | "in_progress" | "done",
      };
    });
    // Reach into the store imperatively so we don't subscribe here and
    // cause a re-render loop.
    usePlanStore.getState().setPlan(normalized);
  }, [activeVariant, todosSignature, streamedTodos]);

  // Build a tool_call_id -> ToolMessage.content lookup once per render so each
  // MessageBubble can show the matching result in its collapsible timeline.
  const toolResults = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of messages) {
      if ((m.type ?? m.role) !== "tool") continue;
      const id = (m as any).tool_call_id as string | undefined;
      if (!id) continue;
      map.set(id, messageText(m));
    }
    return map;
  }, [messages]);

  // Group ephemeral subagent messages (streamed via streamSubgraphs:true)
  // under the supervisor's matching `task(...)` tool call, so the UI can
  // render each task call as a collapsible mini-chat instead of flattening
  // them into the supervisor thread. Matching is done by:
  //   1) tracking open task() tool_calls as we walk messages in order,
  //   2) attaching any message whose subagentOrigin() matches the
  //      subagent_type arg of the most recent open task call,
  //   3) closing a task when its ToolMessage result arrives.
  const { subagentsByTaskCallId, hiddenMessageIds } = useMemo(() => {
    const groups = new Map<string, AnyMsg[]>();
    const hidden = new Set<string>();
    type ActiveTask = { id: string; subagent: string };
    const active: ActiveTask[] = [];
    const isInternal = (msg: AnyMsg): boolean => {
      const ak = (msg as any).additional_kwargs as Record<string, unknown> | undefined;
      if (ak && (ak.internal === true || typeof ak.kind === "string" && /^(compact-summary|system-note)$/i.test(ak.kind as string))) {
        return true;
      }
      const content = (msg as any).content;
      if (typeof content === "string") {
        const t = content.trimStart();
        if (t.startsWith("[compact-summary]") || t.startsWith("[system-note]")) return true;
      }
      return false;
    };
    messages.forEach((m, i) => {
      const role = m.type ?? m.role;
      if (isInternal(m)) {
        hidden.add((m.id as string) ?? `__idx:${i}`);
        return;
      }
      if (role === "tool") {
        const tcid = (m as any).tool_call_id as string | undefined;
        if (tcid) {
          const idx = active.findIndex((a) => a.id === tcid);
          if (idx >= 0) active.splice(idx, 1);
        }
        return;
      }
      const sub = subagentOrigin(m);
      if (sub && active.length > 0) {
        let match: ActiveTask | undefined;
        for (let k = active.length - 1; k >= 0; k--) {
          if (active[k].subagent === sub) { match = active[k]; break; }
        }
        if (!match) match = active[active.length - 1];
        const arr = groups.get(match.id) ?? [];
        arr.push(m);
        groups.set(match.id, arr);
        hidden.add((m.id as string) ?? `__idx:${i}`);
      }
      const calls = getToolCalls(m);
      for (const tc of calls) {
        if (tc.name === "task" && tc.id) {
          const subType = ((tc.args as any)?.subagent_type ?? "") as string;
          active.push({ id: tc.id, subagent: subType });
          if (!groups.has(tc.id)) groups.set(tc.id, []);
        }
      }
    });
    return { subagentsByTaskCallId: groups, hiddenMessageIds: hidden };
  }, [messages]);
  const stopReason = ((stream as any).values?.stop_reason ?? null) as string | null;
  // useStream surfaces the last run error here (network, tool-call JSON, LLM
  // API 4xx/5xx, etc.). We render it inline so the thread doesn't silently
  // stall and give the user a one-click retry of their last user turn.
  const streamError = (stream as any).error as unknown;
  const interruptValue = ((stream as any).interrupt?.value ?? null) as FrontendToolCall | null;

  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const stickyRef = useRef(true);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - (el.scrollTop + el.clientHeight);
    stickyRef.current = distance < 120;
  }, []);

  useEffect(() => {
    if (!stickyRef.current) return;
    const id = requestAnimationFrame(() => {
      endRef.current?.scrollIntoView({ block: "end" });
    });
    return () => cancelAnimationFrame(id);
  }, [messages.length, isStreaming]);

  const [resumeBusy, setResumeBusy] = useState(false);
  // Track all handled interrupt ids to avoid double-handling on re-renders.
  // Using a Set (not a single string) prevents races between the auto-accept
  // effect and the sync onApprove/onReject guards.
  const handledIdsRef = useRef<Set<string>>(new Set());

  const resumeWith = useCallback(
    (result: any) => {
      try {
        // IMPORTANT: resume submits MUST re-send the frontend tool schemas via
        // `config.configurable.frontend_tools`. The agent's chat_node rebuilds
        // the bound tool list from this config on every step, and
        // route_after_chat classifies tool calls against this same list. If we
        // omit it on resume, the next chat_node turn runs without any frontend
        // tools bound, so the LLM can't chain another mutation and the router
        // short-circuits to END — which looks like "the graph stopped after
        // approve". Passing the same config as the initial submit keeps the
        // ReAct loop alive until the agent produces a final text reply.
        (stream as any).submit(undefined, {
          command: { resume: result },
          config: { configurable: { frontend_tools: FRONTEND_TOOLS } },
          streamSubgraphs: true,
        });
      } catch (e) {
        console.error("resume failed", e);
      }
    },
    [stream]
  );

  const onApprove = useCallback(async () => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (handledIdsRef.current.has(interruptValue.tool_call_id)) return;
    handledIdsRef.current.add(interruptValue.tool_call_id);
    setResumeBusy(true);
    const { name, args } = interruptValue;
    const a = (args ?? {}) as any;
    // Strict-mode tool calls may send explicit nulls for optional fields.
    // Normalize null → undefined/[] so the store APIs (which use `?:` optional
    // typing) don't complain.
    const nn = <T,>(v: T | null | undefined): T | undefined => (v ?? undefined) as T | undefined;
    const dispatch: Record<string, () => any> = {
      // DEPRECATED (PR4) — createSyllabus / addChapter now handled by
      // curriculum-mcp (Supabase). The schemas are removed from FRONTEND_TOOLS
      // above so the agent never emits these as frontend tool calls, but keep
      // defensive no-ops in case a stale deployment resumes an old interrupt.
      createSyllabus: () => {
        console.warn("[PR4] createSyllabus frontend tool is deprecated — use curriculum-mcp getOrCreateSyllabus");
        return null;
      },
      addChapter: () => {
        console.warn("[PR4] addChapter frontend tool is deprecated — writes now go through curriculum-mcp");
        return null;
      },
      // DEPRECATED (PR4) — lesson mutations moved to curriculum-mcp. The MCP
      // server writes directly to Supabase; the UI re-renders via the realtime
      // subscription. The dispatch entries below are kept as a reference and
      // a defensive no-op in case a stale agent still emits them.
      addLesson: () => {
        console.warn("[PR4] addLesson frontend tool is deprecated — writes now go through curriculum-mcp");
        return null;
      },
      updateLessonContent: () => {
        console.warn("[PR4] updateLessonContent frontend tool is deprecated — writes now go through curriculum-mcp");
        return null;
      },
      appendLessonContent: () => {
        console.warn("[PR4] appendLessonContent frontend tool is deprecated — writes now go through curriculum-mcp");
        return null;
      },
      patchLessonBlocks: () => {
        console.warn("[PR4] patchLessonBlocks frontend tool is deprecated — writes now go through curriculum-mcp");
        return null;
      },
      // Original dispatch (kept for reference):
      // addLesson: () => store.addLesson(a.chapterId, a.lessonId, a.title, a.content ?? []),
      // updateLessonContent: () => store.updateLessonContent(a.lessonId, a.content ?? []),
      // appendLessonContent: () => store.appendLessonContent(a.lessonId, a.blocks ?? []),
      // patchLessonBlocks: () =>
      //   store.patchLessonBlocks(a.lessonId, a.op, a.startBlock, a.endBlock ?? null, a.blocks ?? []),
      // DEPRECATED (PR4) — reads go through curriculum-mcp (Supabase) now.
      getSyllabusOutline: () => {
        console.warn("[PR4] getSyllabusOutline frontend tool is deprecated — use curriculum-mcp");
        return null;
      },
      readLessonBlocks: () => {
        console.warn("[PR4] readLessonBlocks frontend tool is deprecated — use curriculum-mcp");
        return null;
      },
      setPlan: () =>
        plan.setPlan(
          (a.items ?? []).map((it: any) => ({
            ...it,
            id: nn(it?.id),
            status: nn(it?.status),
          }))
        ),
      updatePlanItem: () => plan.updatePlanItem(a.id, a.status),
      askUser: () => ({ answers: {} }),
    };
    let result: any;
    try {
      const run = dispatch[name];
      if (!run) {
        result = { ok: false, error: `unknown frontend tool: ${name}` };
      } else {
        const out = await run();
        result = { ok: true, result: out ?? null };
      }
    } catch (e: any) {
      result = { ok: false, error: String(e?.message ?? e) };
    }
    resumeWith(result);
    setResumeBusy(false);
  }, [interruptValue, store, resumeWith]);

  const onReject = useCallback(() => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (handledIdsRef.current.has(interruptValue.tool_call_id)) return;
    handledIdsRef.current.add(interruptValue.tool_call_id);
    resumeWith({ ok: false, error: "user_rejected", message: "User rejected this tool call." });
  }, [interruptValue, resumeWith]);


  const onSubmitAskUser = useCallback(
    (answers: Record<string, string | string[]>) => {
      if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
      if (handledIdsRef.current.has(interruptValue.tool_call_id)) return;
      handledIdsRef.current.add(interruptValue.tool_call_id);
      resumeWith({ ok: true, result: { answers } });
    },
    [interruptValue, resumeWith]
  );

  // Pre-flight validation: if the agent emitted a frontend_tool_call with
  // malformed args, auto-resume with a descriptive error so it can retry
  // instead of letting the UI render a crash (e.g. `.every is not a
  // function` on a non-array `questions`). This runs BEFORE the auto-accept
  // effect below so invalid calls never trigger the normal dispatch path.
  useEffect(() => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (handledIdsRef.current.has(interruptValue.tool_call_id)) return;
    const err = validateFrontendToolArgs(interruptValue.name, interruptValue.args);
    if (!err) return;
    handledIdsRef.current.add(interruptValue.tool_call_id);
    // eslint-disable-next-line no-console
    console.warn(
      `[frontend-tool] invalid args for ${interruptValue.name}:`,
      err,
      interruptValue.args,
    );
    toast.error("Agent sent invalid tool arguments", {
      description: `${interruptValue.name}: ${err}`,
    });
    resumeWith({
      ok: false,
      error: "invalid_arguments",
      tool: interruptValue.name,
      message: err,
      hint:
        "The arguments you sent do not match the declared JSON schema for this tool. " +
        "Re-emit the tool call with arguments matching the schema exactly — in particular, " +
        "fields declared as arrays must be JSON arrays (not strings or objects), and required " +
        "string fields must be non-empty strings. Do not wrap structured args in a single text blob.",
    });
  }, [interruptValue, resumeWith]);

  // Read-only tools (outline/read-blocks) never need explicit approval — they
  // only query the editor state. Everything else respects the per-thread
  // auto-accept toggle.
  const READ_ONLY_TOOL_NAMES = new Set(["getSyllabusOutline", "readLessonBlocks"]);
  const INTERACTIVE_TOOL_NAMES = new Set(["askUser"]);
  useEffect(() => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (handledIdsRef.current.has(interruptValue.tool_call_id)) return;
    if (resumeBusy) return;
    // If args are invalid, the validation effect above will have already
    // marked this interrupt as handled and resumed with an error — don't
    // double-dispatch here.
    if (validateFrontendToolArgs(interruptValue.name, interruptValue.args)) return;
    const isReadOnly = READ_ONLY_TOOL_NAMES.has(interruptValue.name);
    const isInteractive = INTERACTIVE_TOOL_NAMES.has(interruptValue.name);
    if (isInteractive) return;
    if (!isReadOnly && !autoAccept) return;
    void onApprove();
  }, [autoAccept, interruptValue, resumeBusy, onApprove]);

  const submitUserText = useCallback(
    (text: string) => {
      stickyRef.current = true;
      stream.submit(
        { messages: [{ role: "user", content: text }] },
        {
          config: { configurable: { frontend_tools: FRONTEND_TOOLS } },
          streamSubgraphs: true,
        } as any
      );
    },
    [stream]
  );

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    submitUserText(text);
  }, [input, isStreaming, submitUserText]);

  const onRetry = useCallback(() => {
    if (isStreaming) return;
    const lastUser = [...messages].reverse().find((m) => (m.type ?? m.role) === "user" || (m.type ?? m.role) === "human");
    const text =
      typeof lastUser?.content === "string"
        ? (lastUser.content as string)
        : messageText(lastUser as any);
    if (!text.trim()) {
      toast.error("Nothing to retry", { description: "Send a new message instead." });
      return;
    }
    submitUserText(text);
  }, [isStreaming, messages, submitUserText]);

  const onStop = useCallback(async () => {
    // SDK exposes the active run id at `stream.runId` or `stream.meta?.runId`
    // depending on version; fall back to cancelling ALL runs on the thread.
    const sAny = stream as any;
    const runId = sAny.runId ?? sAny.meta?.runId ?? sAny.values?.run_id;
    try {
      if (threadId && runId) {
        await cancel(threadId, runId);
      } else if (threadId) {
        const { getLangGraphClient } = await import("@/providers/client");
        const client = getLangGraphClient();
        try {
          // Cancel whatever run is currently marked busy on the server. This
          // covers the "reloaded mid-run" case where the local SDK has no
          // runId yet but the server-side thread is still executing.
          if (typeof (client.runs as any).cancelAll === "function") {
            await (client.runs as any).cancelAll(threadId, true);
          } else {
            const active = await (client.threads as any).getRuns?.(threadId).catch(() => []);
            if (Array.isArray(active)) {
              await Promise.all(
                active
                  .filter((r: any) => r?.status === "running" || r?.status === "pending")
                  .map((r: any) => client.runs.cancel(threadId, r.run_id, true).catch(() => null)),
              );
            }
          }
        } catch {}
      }
    } finally {
      sAny.stop?.();
      void refreshThreadStatus();
    }
  }, [stream, threadId, cancel, refreshThreadStatus]);

  // Explicit reconnect: tears down the current <ChatPaneBody/> and mounts a
  // fresh one via the parent epoch key, which re-creates the useStream hook
  // so it can re-attach to any in-flight server run immediately.
  const onReconnect = useCallback(() => {
    bumpEpoch();
  }, [bumpEpoch]);

  const onKey = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        onSend();
      }
    },
    [onSend]
  );

  const [switching, setSwitching] = useState(false);
  const lastThreadRef = useRef<string | null | undefined>(threadId);
  useEffect(() => {
    if (lastThreadRef.current === threadId) return;
    lastThreadRef.current = threadId;
    if (!threadId) { setSwitching(false); return; }
    setSwitching(true);
    const t = setTimeout(() => setSwitching(false), 800);
    return () => clearTimeout(t);
  }, [threadId]);
  useEffect(() => {
    if (switching && messages.length > 0) setSwitching(false);
  }, [messages.length, switching]);
  const isSwitchingThread = switching && messages.length === 0;

  const onToggleAutoAccept = useCallback(() => {
    if (!threadId) {
      toast.message("Start a thread first", {
        description: "Auto-accept is saved per thread.",
      });
      return;
    }
    toggleAutoAccept(threadId);
    toast.success(autoAccept ? "Auto-accept disabled" : "Auto-accept enabled", {
      description: autoAccept
        ? "You'll review each tool call before it runs."
        : "Frontend tool calls in this thread will run without asking.",
    });
  }, [threadId, autoAccept, toggleAutoAccept]);

  // We distinguish three live states in the header pill:
  //   - "streaming"    → SSE is attached and tokens are flowing locally
  //   - "rejoining"    → server says busy but no local SSE yet (reload / net drop)
  //   - idle           → nothing running
  const isRejoining = serverBusy && !localStreaming;
  const header = useMemo(() => {
    return (
      <div className="flex items-center justify-between border-b border-[var(--border)] px-3 py-2 text-xs">
        <span className="text-[var(--muted-foreground)] font-medium">
          {threadId ? `Thread ${threadId.slice(0, 8)}` : "No thread"}
        </span>
        <span className="flex items-center gap-2">
          {localStreaming && (
            <span className="flex items-center gap-1 text-[var(--primary)]">
              <Loader2 className="h-3 w-3 animate-spin" />
              streaming…
            </span>
          )}
          {isRejoining && (
            <button
              type="button"
              onClick={onReconnect}
              title="Server says this run is still executing. Click to re-attach the live stream."
              className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-500 hover:bg-amber-500/20 transition-colors"
            >
              <Loader2 className="h-3 w-3 animate-spin" />
              rejoining… reconnect
            </button>
          )}
          {!isStreaming && stopReason && <StopReasonChip reason={stopReason} />}
          <button
            type="button"
            onClick={onToggleAutoAccept}
            disabled={!threadId}
            title={
              !threadId
                ? "Start a thread to configure auto-accept"
                : autoAccept
                ? "Auto-accept is ON for this thread"
                : "Auto-accept is OFF for this thread"
            }
            className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              autoAccept
                ? "border-[var(--primary)]/60 bg-[var(--primary)]/10 text-[var(--primary)]"
                : "border-[var(--border)] text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
            }`}
          >
            {autoAccept ? <Zap className="h-3 w-3" /> : <ZapOff className="h-3 w-3" />}
            auto-accept {autoAccept ? "on" : "off"}
          </button>
        </span>
      </div>
    );
  }, [threadId, isStreaming, localStreaming, isRejoining, onReconnect, autoAccept, onToggleAutoAccept, stopReason]);

  return (
    <div className="flex h-full flex-col bg-[var(--card)] text-[var(--foreground)] border-l border-[var(--border)]">
      {header}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto p-3 space-y-3 text-sm"
      >
        {isSwitchingThread && (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-[var(--muted-foreground)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            Loading thread history…
          </div>
        )}
        {!isSwitchingThread && messages.length === 0 && !isStreaming && (
          <div className="text-xs text-[var(--muted-foreground)] text-center py-8">
            {threadId ? "No messages yet. Say hi 👋" : "Start a new thread to chat with the syllabus agent."}
          </div>
        )}
        {!isSwitchingThread && messages.length === 0 && isRejoining && (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-amber-500">
            <Loader2 className="h-3 w-3 animate-spin" />
            Rejoining in-flight run… waiting for the next token.
          </div>
        )}
        {messages.map((m, i) => {
          const role = m.type ?? m.role;
          const isAssistant = role !== "human" && role !== "user" && role !== "tool";
          const isLast = isAssistant && i === messages.length - 1;
          const key = (m.id as string) ?? `__idx:${i}`;
          if (hiddenMessageIds.has(key)) return null;
          return (
            <MessageBubble
              key={visibleKey(m, i)}
              m={m}
              toolResults={toolResults}
              isLastAssistant={isLast}
              isStreaming={isStreaming}
              subagentsByTaskCallId={subagentsByTaskCallId}
            />
          );
        })}
        {(() => {
          // "Thinking…" placeholder while the agent has been invoked but
          // hasn\'t emitted the first assistant token (no content and no
          // tool_call_chunks yet). Without this the chat looks dead between
          // user-send and the first SSE chunk — which is noticeable on slow
          // networks and during tool_call arg streaming warm-up.
          if (!isStreaming) return null;
          const last = messages[messages.length - 1];
          if (!last) return (
            <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
              <Loader2 className="h-3 w-3 animate-spin" />
              Thinking…
            </div>
          );
          const role = (last as any).type ?? (last as any).role;
          if (role === "human" || role === "user" || role === "tool") {
            return (
              <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <Loader2 className="h-3 w-3 animate-spin" />
                {role === "tool" ? "Reading tool result…" : "Thinking…"}
              </div>
            );
          }
          const hasText = !!messageText(last as any);
          const hasCalls = getToolCalls(last as any).length > 0;
          if (!hasText && !hasCalls) {
            return (
              <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <Loader2 className="h-3 w-3 animate-spin" />
                Thinking…
              </div>
            );
          }
          return null;
        })()}
        {interruptValue && interruptValue.name === "askUser" && (
          <AskUserCard call={interruptValue} busy={resumeBusy} onSubmit={onSubmitAskUser} onReject={onReject} />
        )}
        {interruptValue && !new Set(["getSyllabusOutline", "readLessonBlocks", "askUser"]).has(interruptValue.name) && !autoAccept && <InterruptCard call={interruptValue} busy={resumeBusy} onApprove={onApprove} onReject={onReject} />}
        {streamError && !isStreaming && (
          <ErrorBubble error={streamError} onRetry={onRetry} />
        )}
        <div ref={endRef} />
      </div>
      <PlanStrip />
      <div className="border-t border-[var(--border)] p-2 flex gap-2 bg-[var(--background)]">
        <textarea
          className="flex-1 resize-none rounded-md bg-[var(--input)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] p-2 text-base md:text-sm outline-none border border-[var(--border)] focus:border-[var(--ring)] transition-colors"
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask the syllabus agent…"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="rounded-md bg-[var(--destructive)] text-[var(--destructive-foreground)] px-3 text-sm hover:opacity-90 transition-opacity"
            title="Stop"
          >
            <Square className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={onSend}
            className="rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] px-3 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
            disabled={!input.trim() || isStreaming}
            title={isStreaming ? "Agent is working on this thread — wait for it to finish or click Stop." : undefined}
          >
            <Send className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

function formatStreamError(err: unknown): { title: string; detail: string } {
  if (!err) return { title: "Unknown error", detail: "" };
  const raw: any = err;
  let title = "Run failed";
  let detail = "";
  if (typeof raw === "string") {
    detail = raw;
  } else if (raw?.message) {
    detail = String(raw.message);
  } else {
    try {
      detail = JSON.stringify(raw, null, 2);
    } catch {
      detail = String(raw);
    }
  }
  // Extract the useful part of langgraph/openai error envelopes so the user
  // sees "BadRequestError: Expecting ',' delimiter" instead of a 2 KB blob.
  const m = detail.match(/BadRequestError.*?:\s*([^\n"\]}]+)/);
  if (m) {
    title = "Model returned invalid tool arguments";
    detail = m[0];
  } else if (/timeout|ECONN|fetch failed/i.test(detail)) {
    title = "Network error";
  } else if (/401|forbidden|unauthori/i.test(detail)) {
    title = "Authentication error";
  } else if (/429|rate limit/i.test(detail)) {
    title = "Rate limited";
  }
  if (detail.length > 600) detail = detail.slice(0, 600) + "…";
  return { title, detail };
}

function ErrorBubble({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const { title, detail } = formatStreamError(error);
  return (
    <div className="flex flex-col gap-2 rounded-md border border-[var(--destructive)]/40 bg-[var(--destructive)]/5 p-3 text-xs text-[var(--foreground)]">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--destructive)]" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-[var(--destructive)]">{title}</div>
          <div className={`mt-1 whitespace-pre-wrap break-words font-mono text-[11px] leading-snug text-[var(--muted-foreground)] ${expanded ? "" : "line-clamp-3"}`}>
            {detail || "The agent run failed without a message."}
          </div>
          {detail && detail.length > 160 && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-1 text-[11px] text-[var(--primary)] hover:underline"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--background)] px-2 py-1 text-[11px] font-medium text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
        >
          <RotateCw className="h-3 w-3" />
          Retry last message
        </button>
      </div>
    </div>
  );
}



export function ChatPane() {
  // Reconnect epoch: bumping this key unmounts <ChatPaneBody/> and remounts a
  // fresh one, which re-creates the langgraph useStream hook. That is the
  // cheapest way to re-attach to an in-flight server run after a network drop
  // or a stale local SSE without forcing a full page reload (which would also
  // re-download the thread history).
  const [epoch, setEpoch] = React.useState(0);
  const bumpEpoch = React.useCallback(() => setEpoch((n) => n + 1), []);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const onOnline = () => {
      // Browser just regained connectivity. Force a clean reconnect so any
      // silent SSE drop that happened while offline gets healed.
      bumpEpoch();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") bumpEpoch();
    };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [bumpEpoch]);

  return <ChatPaneBody key={epoch} bumpEpoch={bumpEpoch} />;
}

function StopReasonChip({ reason }: { reason: string }) {
  const map: Record<string, { label: string; icon: any; cls: string }> = {
    completed: {
      label: "completed",
      icon: CheckCircle2,
      cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-500",
    },
    error: {
      label: "error",
      icon: AlertCircle,
      cls: "border-[var(--destructive)]/40 bg-[var(--destructive)]/10 text-[var(--destructive)]",
    },
    interrupted_by_user: {
      label: "rejected",
      icon: OctagonAlert,
      cls: "border-amber-500/40 bg-amber-500/10 text-amber-500",
    },
    tool_budget_exhausted: {
      label: "tool budget",
      icon: OctagonAlert,
      cls: "border-amber-500/40 bg-amber-500/10 text-amber-500",
    },
    max_steps: {
      label: "max steps",
      icon: OctagonAlert,
      cls: "border-amber-500/40 bg-amber-500/10 text-amber-500",
    },
  };
  const cfg = map[reason] ?? {
    label: reason,
    icon: AlertCircle,
    cls: "border-[var(--border)] bg-[var(--muted)] text-[var(--muted-foreground)]",
  };
  const Icon = cfg.icon;
  return (
    <span
      title={`stop_reason: ${reason}`}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium ${cfg.cls}`}
    >
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}
