"use client";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { useSyllabusStore } from "@/store/syllabusStore";
import { useThreadStore } from "@/stores/thread-store";
import { useThreadSettingsStore } from "@/stores/thread-settings-store";
import { useThreads } from "@/providers/Thread";
import { useCancelStream } from "@/hooks/useCancelStream";
import { Markdown } from "@/components/chat/Markdown";
import { AlertCircle, Ban, BookOpen, CheckCircle2, ChevronDown, ChevronRight, Circle, Eye, FileText, Layers, ListTodo, Loader2, OctagonAlert, Pencil, RotateCw, Send, Square, Wrench, XCircle, Zap, ZapOff } from "lucide-react";
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
    name: "createSyllabus",
    description: "Create a new syllabus with an id, title, subject, and optional description. Use this only when starting a brand new course plan.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["id", "title", "subject", "description"],
      properties: {
        id: { type: "string" },
        title: { type: "string" },
        subject: { type: "string" },
        description: { type: ["string", "null"] },
      },
    },
  },
  {
    name: "addChapter",
    description: "Append a new chapter to an existing syllabus. Provide the syllabusId, a fresh chapterId, a title, and an optional description.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["syllabusId", "chapterId", "title", "description"],
      properties: {
        syllabusId: { type: "string" },
        chapterId: { type: "string" },
        title: { type: "string" },
        description: { type: ["string", "null"] },
      },
    },
  },
  {
    name: "addLesson",
    description: "Append a lesson to an existing chapter. `content` MUST be a BlockNote block array — each item a full block object matching the block schema (type, props, content[]).",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["chapterId", "lessonId", "title", "content"],
      properties: {
        chapterId: { type: "string" },
        lessonId: { type: "string" },
        title: { type: "string" },
        content: { type: "array", items: BLOCK_SCHEMA },
      },
    },
  },
  {
    name: "updateLessonContent",
    description: "Replace the full BlockNote content of an existing lesson. Prefer patchLessonBlocks when only part of a lesson changes.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["lessonId", "content"],
      properties: {
        lessonId: { type: "string" },
        content: { type: "array", items: BLOCK_SCHEMA },
      },
    },
  },
  {
    name: "appendLessonContent",
    description: "Append BlockNote blocks to the end of an existing lesson without removing prior content.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["lessonId", "blocks"],
      properties: {
        lessonId: { type: "string" },
        blocks: { type: "array", items: BLOCK_SCHEMA },
      },
    },
  },
  {
    name: "getSyllabusOutline",
    description: "Read-only. Returns the skeleton of the current thread's syllabus. Pass null for syllabusId to use the active one.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["syllabusId"],
      properties: {
        syllabusId: { type: ["string", "null"] },
      },
    },
  },
  {
    name: "readLessonBlocks",
    description: "Read-only. Returns a 1-indexed inclusive slice of a lesson's BlockNote content. Use this before patchLessonBlocks so you know what you're replacing.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["lessonId", "startBlock", "endBlock"],
      properties: {
        lessonId: { type: "string" },
        startBlock: { type: "integer" },
        endBlock: { type: "integer" },
      },
    },
  },
  {
    name: "patchLessonBlocks",
    description: "Surgical edit of a BlockNote lesson. op='replace' swaps blocks [startBlock..endBlock] with the provided blocks. op='insert' inserts before startBlock (endBlock is ignored, pass null). op='delete' removes [startBlock..endBlock] (blocks is ignored, pass null/[]). Block indices are 1-based and inclusive.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["lessonId", "op", "startBlock", "endBlock", "blocks"],
      properties: {
        lessonId: { type: "string" },
        op: { type: "string", enum: ["replace", "insert", "delete"] },
        startBlock: { type: "integer" },
        endBlock: { type: ["integer", "null"] },
        blocks: {
          type: ["array", "null"],
          items: BLOCK_SCHEMA,
        },
      },
    },
  },
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

function getToolCalls(m: AnyMsg): ToolCall[] {
  return ((m.tool_calls as any[]) || []) as ToolCall[];
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
    const status: ToolStatus = isLastAssistant && isStreaming ? "running" : "running";
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
};

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
}: {
  call: ToolCall;
  result: ParsedResult;
}) {
  const [open, setOpen] = useState(false);
  const meta = toolMeta(call.name);
  const Icon = meta.icon;
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

const ToolCallTimeline = memo(function ToolCallTimeline({
  calls,
  results,
  isLastAssistant,
  isStreaming,
}: {
  calls: ToolCall[];
  results: Map<string, string>;
  isLastAssistant: boolean;
  isStreaming: boolean;
}) {
  if (!calls.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {calls.map((tc, idx) => {
        const raw = tc.id ? results.get(tc.id) : undefined;
        const result = parseResult(raw, isLastAssistant, isStreaming);
        return <ToolCallCard key={tc.id ?? idx} call={tc} result={result} />;
      })}
    </div>
  );
});

const MessageBubble = memo(function MessageBubble({
  m,
  toolResults,
  isLastAssistant,
  isStreaming,
}: {
  m: AnyMsg;
  toolResults: Map<string, string>;
  isLastAssistant: boolean;
  isStreaming: boolean;
}) {
  const role = m.type ?? m.role;
  const isUser = role === "human" || role === "user";
  const isTool = role === "tool";
  if (isTool) return null;
  const text = messageText(m);
  const calls = getToolCalls(m);
  const msgError = getMessageError(m);
  if (!text && !calls.length && !msgError) return null;
  return (
    <div
      className={`rounded-md px-3 py-2 ${
        isUser
          ? "bg-[var(--primary)]/10 border border-[var(--primary)]/30 text-[var(--foreground)]"
          : msgError
          ? "bg-[var(--muted)] border border-[var(--destructive)]/40 text-[var(--foreground)]"
          : "bg-[var(--muted)] text-[var(--foreground)]"
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
          {isUser ? "You" : "Agent"}
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
      {calls.length > 0 && <ToolCallTimeline calls={calls} results={toolResults} isLastAssistant={isLastAssistant} isStreaming={isStreaming} />}
    </div>
  );
});

function visibleKey(m: AnyMsg, i: number): string {
  return (m.id as string) ?? `${m.type ?? m.role ?? "m"}-${i}`;
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

export function ChatPane() {
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

  const setCurrentPlanThread = usePlanStore((s) => s.setCurrentThread);
  useEffect(() => {
    setCurrentPlanThread(threadId ?? null);
  }, [threadId, setCurrentPlanThread]);

  // Per-thread settings (auto-accept etc). We subscribe to the slice for the
  // active thread so the UI re-renders when it flips.
  const autoAccept = useThreadSettingsStore((s) =>
    threadId ? s.byThread[threadId]?.autoAccept ?? false : false
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

  const stream = useSyllabusAgent({ threadId: threadId ?? undefined, onThreadId: handleThreadId });
  const [input, setInput] = useState("");
  const store = useSyllabusStore();
  const plan = usePlanStore();
  const cancel = useCancelStream();

  const messages = (stream.messages ?? []) as AnyMsg[];
  const isStreaming = stream.isLoading;
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
      createSyllabus: () => store.createSyllabus(a.id, a.title, a.subject, nn(a.description)),
      addChapter: () => store.addChapter(a.syllabusId, a.chapterId, a.title, nn(a.description)),
      addLesson: () => store.addLesson(a.chapterId, a.lessonId, a.title, a.content ?? []),
      updateLessonContent: () => store.updateLessonContent(a.lessonId, a.content ?? []),
      appendLessonContent: () => store.appendLessonContent(a.lessonId, a.blocks ?? []),
      patchLessonBlocks: () =>
        store.patchLessonBlocks(a.lessonId, a.op, a.startBlock, a.endBlock ?? null, a.blocks ?? []),
      getSyllabusOutline: () => store.getSyllabusOutline(nn(a.syllabusId)),
      readLessonBlocks: () =>
        store.readLessonBlocks(a.lessonId, a.startBlock, a.endBlock),
      setPlan: () =>
        plan.setPlan(
          (a.items ?? []).map((it: any) => ({
            ...it,
            id: nn(it?.id),
            status: nn(it?.status),
          }))
        ),
      updatePlanItem: () => plan.updatePlanItem(a.id, a.status),
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

  // Read-only tools (outline/read-blocks) never need explicit approval — they
  // only query the editor state. Everything else respects the per-thread
  // auto-accept toggle.
  const READ_ONLY_TOOL_NAMES = new Set(["getSyllabusOutline", "readLessonBlocks"]);
  useEffect(() => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (handledIdsRef.current.has(interruptValue.tool_call_id)) return;
    if (resumeBusy) return;
    const isReadOnly = READ_ONLY_TOOL_NAMES.has(interruptValue.name);
    if (!isReadOnly && !autoAccept) return;
    void onApprove();
  }, [autoAccept, interruptValue, resumeBusy, onApprove]);

  const submitUserText = useCallback(
    (text: string) => {
      stickyRef.current = true;
      stream.submit(
        { messages: [{ role: "user", content: text }] },
        { config: { configurable: { frontend_tools: FRONTEND_TOOLS } } } as any
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
        const runs = await client.threads.getState(threadId).catch(() => null);
        void runs;
        try {
          // @ts-ignore — cancelAll exists on recent SDKs
          if (typeof client.runs.cancelAll === "function") {
            await (client.runs as any).cancelAll(threadId, true);
          }
        } catch {}
      }
    } finally {
      sAny.stop?.();
    }
  }, [stream, threadId, cancel]);

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

  const header = useMemo(() => {
    return (
      <div className="flex items-center justify-between border-b border-[var(--border)] px-3 py-2 text-xs">
        <span className="text-[var(--muted-foreground)] font-medium">
          {threadId ? `Thread ${threadId.slice(0, 8)}` : "No thread"}
        </span>
        <span className="flex items-center gap-2">
          {isStreaming && (
            <span className="flex items-center gap-1 text-[var(--primary)]">
              <Loader2 className="h-3 w-3 animate-spin" />
              streaming…
            </span>
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
  }, [threadId, isStreaming, autoAccept, onToggleAutoAccept, stopReason]);

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
        {messages.map((m, i) => {
          const role = m.type ?? m.role;
          const isAssistant = role !== "human" && role !== "user" && role !== "tool";
          const isLast = isAssistant && i === messages.length - 1;
          return (
            <MessageBubble
              key={visibleKey(m, i)}
              m={m}
              toolResults={toolResults}
              isLastAssistant={isLast}
              isStreaming={isStreaming}
            />
          );
        })}
        {interruptValue && !new Set(["getSyllabusOutline", "readLessonBlocks"]).has(interruptValue.name) && <InterruptCard call={interruptValue} busy={resumeBusy} onApprove={onApprove} onReject={onReject} />}
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
            disabled={!input.trim()}
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
