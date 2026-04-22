"use client";
import { useMemo } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  LANGGRAPH_API_URL,
  langgraphHeaders,
  assistantIdFor,
  type AgentVariant,
} from "@/providers/client";
import { useThreadMessagesCache } from "@/stores/thread-messages-cache";

type StreamOpts = {
  threadId?: string | null;
  onThreadId?: (id: string) => void;
  /**
   * Picked at thread creation and stored in `thread.metadata.variant`.
   * Cannot change for an existing thread.
   */
  variant?: AgentVariant | null;
};

export function useSyllabusAgent({ threadId, onThreadId, variant }: StreamOpts = {}) {
  const assistantId = assistantIdFor(variant ?? "classic");

  // If we have a cached messages snapshot for this thread, skip the
  // `fetchStateHistory` round-trip on mount. That pull downloads the full
  // checkpoint stream from the server and is the main cause of the 1 Mbit/s
  // spike when reloading the page during a long-running run. The live SSE
  // stream will still overlay any deltas on top of the cached seed.
  const hasCachedSnapshot = useThreadMessagesCache((s) =>
    threadId ? s.has(threadId) : false
  );

  const options = useMemo(() => {
    const base: any = {
      apiUrl: LANGGRAPH_API_URL,
      assistantId,
      messagesKey: "messages" as const,
      reconnectOnMount: true,
      // Only pull full checkpoint history when we have nothing to render from.
      // On warm reloads the cache seeds the UI and we rejoin the live stream
      // without re-downloading every historical snapshot.
      fetchStateHistory: !hasCachedSnapshot,
      defaultHeaders: langgraphHeaders(),
      onThreadId,
    };
    return threadId ? { ...base, threadId } : base;
  }, [assistantId, hasCachedSnapshot, threadId, onThreadId]);

  return useStream<{ messages: any[] }>(options as any);
}
