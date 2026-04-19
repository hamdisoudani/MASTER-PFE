"use client";
import React from "react";
import { useQueryState } from "nuqs";
import { useThreads } from "@/providers/Thread";
import { useThreadStore } from "@/stores/thread-store";
import { Plus, RefreshCcw, Trash2 } from "lucide-react";

function firstUserPreview(t: any): string {
  const vals = t?.values as any;
  const msgs = vals?.messages ?? [];
  const first = msgs.find((m: any) => m?.type === "human" || m?.role === "user");
  const c = first?.content;
  if (typeof c === "string") return c.slice(0, 60);
  if (Array.isArray(c)) {
    const t0 = c.find((p: any) => p?.type === "text");
    if (t0?.text) return String(t0.text).slice(0, 60);
  }
  return t?.thread_id?.slice(0, 8) ?? "(empty)";
}

export function ThreadHistory() {
  const { threads, isLoading, isValidating, refreshThreads, createThread, deleteThread } = useThreads();
  const [threadId, setThreadId] = useQueryState("threadId");
  const setActive = useThreadStore((s) => s.setActiveThread);

  const onNew = async () => {
    const t = await createThread();
    await setThreadId(t.thread_id);
    setActive(t.thread_id);
  };

  const onPick = async (id: string) => {
    await setThreadId(id);
    setActive(id);
  };

  const onDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteThread(id);
    if (threadId === id) {
      await setThreadId(null);
      setActive(null);
    }
  };

  return (
    <div className="flex h-full flex-col border-r border-neutral-800 bg-neutral-950 text-neutral-100 text-sm">
      <div className="flex items-center gap-1 border-b border-neutral-800 p-2">
        <button onClick={onNew} className="flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-xs hover:bg-blue-500">
          <Plus className="h-3 w-3" /> New
        </button>
        <button onClick={() => refreshThreads()} className="rounded bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700">
          <RefreshCcw className={`h-3 w-3 ${isValidating ? "animate-spin" : ""}`} />
        </button>
        <span className="ml-auto text-[10px] opacity-50">{threads.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <div className="p-2 text-xs opacity-60">Loading threads...</div>}
        {!isLoading && threads.length === 0 && (
          <div className="p-2 text-xs opacity-60">No threads yet. Click New.</div>
        )}
        {threads.map((t: any) => {
          const active = t.thread_id === threadId;
          return (
            <div
              key={t.thread_id}
              onClick={() => onPick(t.thread_id)}
              className={`group flex cursor-pointer items-start gap-2 border-b border-neutral-900 px-2 py-2 hover:bg-neutral-900 ${
                active ? "bg-neutral-900" : ""
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate">{firstUserPreview(t)}</div>
                <div className="text-[10px] opacity-40">
                  {t.thread_id.slice(0, 8)} · {t.status ?? "idle"}
                </div>
              </div>
              <button
                onClick={(e) => onDelete(e, t.thread_id)}
                className="opacity-0 group-hover:opacity-100 text-neutral-400 hover:text-red-400"
                title="Delete"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
