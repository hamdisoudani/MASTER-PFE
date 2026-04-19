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
import { Loader2, Send, Square, Wrench, Zap, ZapOff } from "lucide-react";
import { usePlanStore } from "@/stores/plan-store";
import { PlanCard } from "@/components/chat/PlanCard";

type AnyMsg = {
  id?: string;
  type?: string;
  role?: string;
  content?: unknown;
  tool_calls?: unknown[];
  tool_call_id?: string;
  name?: string;
};

const FRONTEND_TOOLS = [
  {
    name: "createSyllabus",
    description: "Create a new syllabus with an id, title, subject, and optional description. Use this only when starting a brand new course plan.",
    parameters: {
      type: "object",
      properties: {
        id: { type: "string" },
        title: { type: "string" },
        subject: { type: "string" },
        description: { type: "string" },
      },
      required: ["id", "title", "subject"],
    },
  },
  {
    name: "addChapter",
    description: "Append a new chapter to an existing syllabus. Provide the syllabusId, a fresh chapterId, a title, and an optional description.",
    parameters: {
      type: "object",
      properties: {
        syllabusId: { type: "string" },
        chapterId: { type: "string" },
        title: { type: "string" },
        description: { type: "string" },
      },
      required: ["syllabusId", "chapterId", "title"],
    },
  },
  {
    name: "addLesson",
    description: "Append a lesson to an existing chapter. `content` is a BlockNote block array (use simple paragraph blocks if unsure).",
    parameters: {
      type: "object",
      properties: {
        chapterId: { type: "string" },
        lessonId: { type: "string" },
        title: { type: "string" },
        content: { type: "array", items: { type: "object" } },
      },
      required: ["chapterId", "lessonId", "title", "content"],
    },
  },
  {
    name: "updateLessonContent",
    description: "Replace the full BlockNote content of an existing lesson.",
    parameters: {
      type: "object",
      properties: {
        lessonId: { type: "string" },
        content: { type: "array", items: { type: "object" } },
      },
      required: ["lessonId", "content"],
    },
  },
  {
    name: "appendLessonContent",
    description: "Append BlockNote blocks to the end of an existing lesson without removing prior content.",
    parameters: {
      type: "object",
      properties: {
        lessonId: { type: "string" },
        blocks: { type: "array", items: { type: "object" } },
      },
      required: ["lessonId", "blocks"],
    },
  },
  {
    name: "getSyllabusOutline",
    description: "Read-only. Returns the skeleton of the current thread's syllabus: { syllabusId, title, subject, chapters:[{ id, title, description, lessons:[{ id, title, blockCount }] }], allSyllabi }. Call this FIRST when you need to orient yourself before editing. If no syllabusId is given, the active one is used.",
    parameters: {
      type: "object",
      properties: {
        syllabusId: { type: "string" },
      },
    },
  },
  {
    name: "readLessonBlocks",
    description: "Read-only. Returns a slice of a lesson's BlockNote content by 1-indexed inclusive block range: { totalBlocks, start, end, blocks:[{ index, id, type, text }] }. Use this before patchLessonBlocks so you know exactly what you are replacing.",
    parameters: {
      type: "object",
      properties: {
        lessonId: { type: "string" },
        startBlock: { type: "integer", minimum: 1 },
        endBlock: { type: "integer", minimum: 1 },
      },
      required: ["lessonId", "startBlock", "endBlock"],
    },
  },
  {
    name: "patchLessonBlocks",
    description: "Surgical edit of a BlockNote lesson. op='replace' swaps blocks [startBlock..endBlock] with the provided blocks. op='insert' inserts before startBlock (endBlock ignored). op='delete' removes [startBlock..endBlock]. Prefer this over updateLessonContent whenever only part of a lesson changes. Block indices are 1-based and inclusive.",
    parameters: {
      type: "object",
      properties: {
        lessonId: { type: "string" },
        op: { type: "string", enum: ["replace", "insert", "delete"] },
        startBlock: { type: "integer", minimum: 1 },
        endBlock: { type: "integer", minimum: 1 },
        blocks: { type: "array", items: { type: "object" } },
      },
      required: ["lessonId", "op", "startBlock"],
    },
  },
  {
    name: "setPlan",
    description: "Replace the thread's task plan with the given ordered list. Use this at the start of any non-trivial request to split the work into sub-tasks (e.g. 'search for references', 'draft outline', 'write chapter 1'). Status defaults to 'pending'.",
    parameters: {
      type: "object",
      properties: {
        items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              title: { type: "string" },
              status: { type: "string", enum: ["pending", "in_progress", "done"] },
            },
            required: ["title"],
          },
        },
      },
      required: ["items"],
    },
  },
  {
    name: "updatePlanItem",
    description: "Flip a single plan item's status. Mark the current task 'in_progress' when you start it and 'done' the moment it finishes, before moving on.",
    parameters: {
      type: "object",
      properties: {
        id: { type: "string" },
        status: { type: "string", enum: ["pending", "in_progress", "done"] },
      },
      required: ["id", "status"],
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

function toolCallSummary(m: AnyMsg): string | null {
  const calls = (m.tool_calls as any[]) || [];
  if (!calls.length) return null;
  return calls
    .map((tc) => `${tc.name ?? "tool"}(${Object.keys(tc.args ?? {}).join(", ")})`)
    .join(", ");
}

const MessageBubble = memo(function MessageBubble({ m }: { m: AnyMsg }) {
  const role = m.type ?? m.role;
  const isUser = role === "human" || role === "user";
  const isTool = role === "tool";
  if (isTool) return null;
  const text = messageText(m);
  const callSummary = toolCallSummary(m);
  if (!text && !callSummary) return null;
  return (
    <div
      className={`rounded-md px-3 py-2 ${
        isUser
          ? "bg-[var(--primary)]/10 border border-[var(--primary)]/30 text-[var(--foreground)]"
          : "bg-[var(--muted)] text-[var(--foreground)]"
      }`}
    >
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-1">
        {isUser ? "You" : "Agent"}
      </div>
      {text ? (
        isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed text-sm">{text}</div>
        ) : (
          <Markdown source={text} />
        )
      ) : null}
      {callSummary && (
        <div className="mt-1 flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]">
          <Wrench className="h-3 w-3" /> calling <code>{callSummary}</code>
        </div>
      )}
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
  const handledIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!interruptValue) handledIdRef.current = null;
  }, [interruptValue]);

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
    if (handledIdRef.current === interruptValue.tool_call_id) return;
    handledIdRef.current = interruptValue.tool_call_id;
    setResumeBusy(true);
    const { name, args } = interruptValue;
    const a = (args ?? {}) as any;
    const dispatch: Record<string, () => any> = {
      createSyllabus: () => store.createSyllabus(a.id, a.title, a.subject, a.description),
      addChapter: () => store.addChapter(a.syllabusId, a.chapterId, a.title, a.description),
      addLesson: () => store.addLesson(a.chapterId, a.lessonId, a.title, a.content ?? []),
      updateLessonContent: () => store.updateLessonContent(a.lessonId, a.content ?? []),
      appendLessonContent: () => store.appendLessonContent(a.lessonId, a.blocks ?? []),
      patchLessonBlocks: () =>
        store.patchLessonBlocks(a.lessonId, a.op, a.startBlock, a.endBlock ?? null, a.blocks ?? []),
      getSyllabusOutline: () => store.getSyllabusOutline(a.syllabusId),
      readLessonBlocks: () =>
        store.readLessonBlocks(a.lessonId, a.startBlock, a.endBlock),
      setPlan: () => plan.setPlan(a.items ?? []),
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
    if (handledIdRef.current === interruptValue.tool_call_id) return;
    handledIdRef.current = interruptValue.tool_call_id;
    resumeWith({ ok: false, error: "user_rejected", message: "User rejected this tool call." });
  }, [interruptValue, resumeWith]);

  // Read-only tools (outline/read-blocks) never need explicit approval — they
  // only query the editor state. Everything else respects the per-thread
  // auto-accept toggle.
  const READ_ONLY_TOOL_NAMES = new Set(["getSyllabusOutline", "readLessonBlocks"]);
  useEffect(() => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (handledIdRef.current === interruptValue.tool_call_id) return;
    if (resumeBusy) return;
    const isReadOnly = READ_ONLY_TOOL_NAMES.has(interruptValue.name);
    if (!isReadOnly && !autoAccept) return;
    void onApprove();
  }, [autoAccept, interruptValue, resumeBusy, onApprove]);

  const onSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    stickyRef.current = true;
    stream.submit(
      { messages: [{ role: "user", content: text }] },
      { config: { configurable: { frontend_tools: FRONTEND_TOOLS } } } as any
    );
  }, [input, isStreaming, stream]);

  const onStop = useCallback(async () => {
    const runId = (stream as any).values?.run_id as string | undefined;
    if (threadId && runId) await cancel(threadId, runId);
    (stream as any).stop?.();
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
  }, [threadId, isStreaming, autoAccept, onToggleAutoAccept]);

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
        <PlanCard />
        {messages.map((m, i) => (
          <MessageBubble key={visibleKey(m, i)} m={m} />
        ))}
        {interruptValue && !new Set(["getSyllabusOutline", "readLessonBlocks"]).has(interruptValue.name) && <InterruptCard call={interruptValue} busy={resumeBusy} onApprove={onApprove} onReject={onReject} />}
        <div ref={endRef} />
      </div>
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
