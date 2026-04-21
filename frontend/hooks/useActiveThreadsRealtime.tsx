"use client";
import { useSyllabusRealtime } from "./useSyllabusRealtime";
import { useThreads } from "@/providers/Thread";

/**
 * Open realtime subscriptions for the top-N most recently active threads
 * (sorted by `updated_at desc` via `useThreadsSWR`). This lets the sidebar
 * / background threads stay in sync even if the user hasn't opened them.
 *
 * Called once at the top of the app tree (`SyllabusViewerClient`).
 * N=5 per the product requirement; low realtime overhead because each
 * thread's syllabus is small.
 */
function ThreadSubscription({ threadId }: { threadId: string }) {
  useSyllabusRealtime(threadId);
  return null;
}

export function ActiveThreadsRealtime({ limit = 5 }: { limit?: number }) {
  const { threads } = useThreads();
  const top = (threads ?? []).slice(0, limit);
  return (
    <>
      {top.map((t: any) => (
        <ThreadSubscription key={t.thread_id} threadId={t.thread_id} />
      ))}
    </>
  );
}
