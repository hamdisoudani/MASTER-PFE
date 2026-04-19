"use client";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryState } from "nuqs";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { useSyllabusStore } from "@/store/syllabusStore";
import { useThreadStore } from "@/stores/thread-store";
import { useThreads } from "@/providers/Thread";
import { useCancelStream } from "@/hooks/useCancelStream";
import { Markdown } from "@/components/chat/Markdown";
import { Loader2, Send, Square, Wrench } from "lucide-react";

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

function InterruptBanner({ call }: { call: FrontendToolCall }) {
  return (
    <div className="mx-3 my-1 rounded-md border border-dashed border-[var(--primary)]/40 bg-[var(--primary)]/5 px-3 py-2 text-xs flex items-center gap-2">
      <Loader2 className="h-3 w-3 animate-spin text-[var(--primary)]" />
      <span>
        Applying <code className="font-mono">{call.name}</code>…
      </span>
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

  const resumingIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!interruptValue || interruptValue.type !== "frontend_tool_call") return;
    if (resumingIdRef.current === interruptValue.tool_call_id) return;
    resumingIdRef.current = interruptValue.tool_call_id;
    const { name, args } = interruptValue;
    (async () => {
      let result: any;
      try {
        const fn = (store as any)[name];
        if (typeof fn !== "function") {
          result = { ok: false, error: `unknown frontend tool: ${name}` };
        } else {
          const argList = Array.isArray(args) ? args : Object.values(args ?? {});
          const out = await fn(...argList);
          result = { ok: true, result: out ?? null };
        }
      } catch (e: any) {
        result = { ok: false, error: String(e?.message ?? e) };
      }
      try {
        (stream as any).submit(undefined, { command: { resume: result } });
      } catch (e) {
        console.error("resume failed", e);
      }
    })();
  }, [interruptValue, store, stream]);

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

  const header = useMemo(() => {
    return (
      <div className="flex items-center justify-between border-b border-[var(--border)] px-3 py-2 text-xs">
        <span className="text-[var(--muted-foreground)] font-medium">
          {threadId ? `Thread ${threadId.slice(0, 8)}` : "No thread"}
        </span>
        <span className="flex items-center gap-1">
          {isStreaming && (
            <span className="flex items-center gap-1 text-[var(--primary)]">
              <Loader2 className="h-3 w-3 animate-spin" />
              streaming…
            </span>
          )}
        </span>
      </div>
    );
  }, [threadId, isStreaming]);

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
        {messages.map((m, i) => (
          <MessageBubble key={visibleKey(m, i)} m={m} />
        ))}
        {interruptValue && <InterruptBanner call={interruptValue} />}
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
