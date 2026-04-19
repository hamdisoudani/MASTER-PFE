"use client";
import { getLangGraphClient } from "@/providers/client";

export function useCancelStream() {
  return async (threadId: string, runId: string) => {
    try {
      await getLangGraphClient().runs.cancel(threadId, runId, true);
    } catch (e) {
      console.error("cancel run failed", e);
    }
  };
}
