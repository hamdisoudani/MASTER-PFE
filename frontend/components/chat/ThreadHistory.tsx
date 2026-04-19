"use client";
import React from "react";
import { useQueryState } from "nuqs";
import { useThreads } from "@/providers/Thread";
import { useThreadStore } from "@/stores/thread-store";
import { Loader2, Plus, RefreshCcw, Trash2 } from "lucide-react";

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
    <div className="flex h-full flex-col border-r border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] text-sm">
      <div className="flex items-center gap-1 border-b border-[var(--border)] px-2 py-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mr-auto">Threads</p>
        <button
          onClick={onNew}
          className="flex items-center gap-1 rounded-md bg-[var(--primary)] text-[var(--primary-foreground)] px-2 py-1 text-xs font-medium hover:opacity-90 transition-opacity"
          title="New thread"
        >
          <Plus className="h-3 w-3" /> New
        </button>
        <button
          onClick={() => refreshThreads()}
          className="rounded-md bg-[var(--muted)] text-[var(--muted-foreground)] px-2 py-1 text-xs hover:bg-[var(--accent)] hover:text-[var(--accent-foreground)] transition-colors"
          title="Refresh"
        >
          <RefreshCcw className={`h-3 w-3 ${isValidating ? "animate-spin" : ""}`} />
        </button>
        <span className="text-[10px] text-[var(--muted-foreground)] opacity-70 tabular-nums ml-1">{threads.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center gap-2 p-3 text-xs text-[var(--muted-foreground)]">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading threads…
          </div>
        )}
        {!isLoading && isValidating && (
          <div className="flex items-center gap-2 px-3 py-1 text-[10px] text-[var(--muted-foreground)] border-b border-[var(--border)]">
            <Loader2 className="h-3 w-3 animate-spin" /> Refreshing…
          </div>
        )}
        {!isLoading && threads.length === 0 && (
          <div className="p-3 text-xs text-[var(--muted-foreground)]">No threads yet. Click <span className="text-[var(--primary)] font-medium">New</span>.</div>
        )}
        {threads.map((t: any) => {
          const active = t.thread_id === threadId;
          return (
            <div
              key={t.thread_id}
              onClick={() => onPick(t.thread_id)}
              className={`group flex cursor-pointer items-start gap-2 border-b border-[var(--border)] px-3 py-2 transition-colors ${
                active
                  ? "bg-[var(--accent)] text-[var(--accent-foreground)] border-l-2 border-l-[var(--primary)]"
                  : "hover:bg-[var(--muted)]"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate text-[var(--foreground)]">{firstUserPreview(t)}</div>
                <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                  {t.thread_id.slice(0, 8)} · {t.status ?? "idle"}
                </div>
              </div>
              <button
                onClick={(e) => onDelete(e, t.thread_id)}
                className="opacity-0 group-hover:opacity-100 text-[var(--muted-foreground)] hover:text-[var(--destructive)] transition-opacity"
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
