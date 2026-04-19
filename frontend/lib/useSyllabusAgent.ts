"use client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { ASSISTANT_ID, LANGGRAPH_API_URL, langgraphHeaders } from "@/providers/client";

type StreamOpts = {
  threadId?: string | null;
  onThreadId?: (id: string) => void;
};

export function useSyllabusAgent({ threadId, onThreadId }: StreamOpts = {}) {
  const base = {
    apiUrl: LANGGRAPH_API_URL,
    assistantId: ASSISTANT_ID,
    messagesKey: "messages" as const,
    reconnectOnMount: true,
    fetchStateHistory: true,
    defaultHeaders: langgraphHeaders(),
    onThreadId,
  };
  // IMPORTANT: omit the `threadId` key entirely when we don't have one, so the
  // SDK's `useControllableThreadId` falls back to uncontrolled mode and the
  // thread auto-created on first submit sticks.
  const options = threadId ? { ...base, threadId } : base;
  return useStream<{ messages: any[] }>(options as any);
}
