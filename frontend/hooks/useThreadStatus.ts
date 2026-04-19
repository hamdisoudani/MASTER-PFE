"use client";
import useSWR from "swr";
import { getLangGraphClient } from "@/providers/client";

export type ThreadStatus = "idle" | "busy" | "interrupted" | "error" | "unknown";

export function useThreadStatus(threadId: string | null | undefined, refreshInterval = 0) {
  const swr = useSWR<ThreadStatus>(
    threadId ? ["thread-status", threadId] : null,
    async () => {
      if (!threadId) return "unknown";
      try {
        const t = await getLangGraphClient().threads.get(threadId);
        const s = (t as any)?.status;
        if (s === "idle" || s === "busy" || s === "interrupted" || s === "error") return s;
        return "unknown";
      } catch {
        return "unknown";
      }
    },
    { refreshInterval, revalidateOnFocus: true, keepPreviousData: true }
  );
  return { status: swr.data ?? "unknown", mutate: swr.mutate };
}
