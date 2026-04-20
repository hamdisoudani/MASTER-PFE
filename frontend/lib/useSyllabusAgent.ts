"use client";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  LANGGRAPH_API_URL,
  langgraphHeaders,
  assistantIdFor,
  type AgentVariant,
} from "@/providers/client";

type StreamOpts = {
  threadId?: string | null;
  onThreadId?: (id: string) => void;
  /**
   * Picked at thread creation and stored in `thread.metadata.variant`.
   * Cannot change for an existing thread — ChatPane passes whatever the
   * current thread's metadata says, so switching the picker only affects
   * NEW threads.
   */
  variant?: AgentVariant | null;
};

export function useSyllabusAgent({ threadId, onThreadId, variant }: StreamOpts = {}) {
  const assistantId = assistantIdFor(variant ?? "classic");
  const base = {
    apiUrl: LANGGRAPH_API_URL,
    assistantId,
    messagesKey: "messages" as const,
    reconnectOnMount: true,
    fetchStateHistory: true,
    // Stream messages from deepagents subagent subgraphs so the user sees
    // researcher / writer / reviser work live. Subagent messages are NOT
    // persisted into parent state (deepagents default), so they naturally
    // disappear from the thread once the run ends.
    streamSubgraphs: true,
    defaultHeaders: langgraphHeaders(),
    onThreadId,
  };
  // IMPORTANT: omit `threadId` entirely when absent, so the SDK's
  // `useControllableThreadId` falls back to uncontrolled mode and the
  // thread auto-created on first submit sticks.
  const options = threadId ? { ...base, threadId } : base;
  return useStream<{ messages: any[] }>(options as any);
}
