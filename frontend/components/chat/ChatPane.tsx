"use client";
import React, { useEffect, useRef, useState } from "react";
import { useQueryState } from "nuqs";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { subscribeToolCalls } from "@/lib/pusherClient";
import { useSyllabusStore } from "@/store/syllabusStore";
import { useThreadStore } from "@/stores/thread-store";
import { useThreads } from "@/providers/Thread";
import { useCancelStream } from "@/hooks/useCancelStream";
import { Send, Loader2, Square } from "lucide-react";

export function ChatPane() {
  const [threadIdParam, setThreadIdParam] = useQueryState("threadId");
  const activeFromStore = useThreadStore((s) => s.activeThreadId);
  const setActive = useThreadStore((s) => s.setActiveThread);
  const { createThread, refreshThreads } = useThreads();

  const threadId = threadIdParam ?? activeFromStore;

  useEffect(() => {
    if (threadIdParam && threadIdParam !== activeFromStore) {
      setActive(threadIdParam);
    }
  }, [threadIdParam, activeFromStore, setActive]);

  const stream = useSyllabusAgent(threadId);
  const [input, setInput] = useState("");
  const store = useSyllabusStore();
  const endRef = useRef<HTMLDivElement>(null);
  const cancel = useCancelStream();

  const joinedRunId = useRef<string | null>(null);
  useEffect(() => {
    const vals = (stream as any).values as any;
    const runId = vals?.run_id as string | undefined;
    if (threadId && runId && runId !== joinedRunId.current) {
      joinedRunId.current = runId;
      (stream as any).joinStream?.(runId)?.catch?.((e: any) => console.error("joinStream failed", e));
    }
  }, [stream, threadId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [stream.messages]);

  useEffect(() => {
    if (!threadId) return;
    return subscribeToolCalls(threadId, async (payload) => {
      const activeNow = useThreadStore.getState().activeThreadId;
      if (activeNow && activeNow !== threadId) return;
      const { id, name, args } = payload;
      try {
        const anyStore = store as any;
        const fn = anyStore?.[name];
        const result = typeof fn === "function" ? await fn(args) : { ok: false, error: `unknown tool ${name}` };
        await fetch(`${process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? "http://localhost:2024"}/threads/${threadId}/state`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ values: { tool_result: { id, name, result } } }),
        });
      } catch (e) {
        console.error("tool exec failed", name, e);
      }
    });
  }, [threadId, store]);

  const onSend = async () => {
    const text = input.trim();
    if (!text || stream.isLoading) return;
    setInput("");
    let tid = threadId;
    if (!tid) {
      const t = await createThread();
      tid = t.thread_id;
      await setThreadIdParam(tid);
      setActive(tid);
    }
    stream.submit({ messages: [{ role: "user", content: text }] });
    refreshThreads();
  };

  const onStop = async () => {
    const runId = (stream as any).values?.run_id as string | undefined;
    if (threadId && runId) await cancel(threadId, runId);
    (stream as any).stop?.();
  };

  return (
    <div className="flex h-full flex-col bg-neutral-950 text-neutral-100">
      <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-1 text-xs opacity-70">
        <span>{threadId ? `thread ${threadId.slice(0, 8)}` : "no thread"}</span>
        <span>{stream.isLoading ? "streaming..." : ""}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2 text-sm">
        {stream.messages.map((m: any, i: number) => (
          <div key={i} className={m.type === "human" ? "text-blue-300" : "text-neutral-200"}>
            <span className="text-xs opacity-60">{m.type}</span>
            <div className="whitespace-pre-wrap">{typeof m.content === "string" ? m.content : JSON.stringify(m.content)}</div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-neutral-800 p-2 flex gap-2">
        <textarea
          className="flex-1 resize-none rounded bg-neutral-900 p-2 text-sm outline-none"
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
          placeholder="Ask the syllabus agent..."
        />
        {stream.isLoading ? (
          <button onClick={onStop} className="rounded bg-red-600 px-3 text-sm hover:bg-red-500" title="Stop">
            <Square className="h-4 w-4" />
          </button>
        ) : (
          <button onClick={onSend} className="rounded bg-blue-600 px-3 text-sm disabled:opacity-50" disabled={!input.trim()}>
            <Send className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
