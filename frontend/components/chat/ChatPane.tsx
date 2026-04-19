"use client";
import React, { useEffect, useRef, useState } from "react";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { subscribeToolCalls } from "@/lib/pusherClient";
import { useSyllabusStore } from "@/store/syllabusStore";
import { Send, Loader2 } from "lucide-react";

export function ChatPane() {
  const [threadId] = useState(() => (typeof crypto !== "undefined" ? crypto.randomUUID() : String(Date.now())));
  const stream = useSyllabusAgent(threadId);
  const [input, setInput] = useState("");
  const store = useSyllabusStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [stream.messages]);

  useEffect(() => {
    return subscribeToolCalls(threadId, async ({ id, name, args }) => {
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

  const onSend = () => {
    const text = input.trim();
    if (!text || stream.isLoading) return;
    setInput("");
    stream.submit({ messages: [{ role: "user", content: text }] });
  };

  return (
    <div className="flex h-full flex-col bg-neutral-950 text-neutral-100">
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
        <button onClick={onSend} disabled={stream.isLoading} className="rounded bg-blue-600 px-3 text-sm disabled:opacity-50">
          {stream.isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}
