"use client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { ASSISTANT_ID } from "@/providers/client";

const AGENT_URL = "https://agent-production-43c3.up.railway.app";

type StreamOpts = {
  threadId?: string | null;
  onThreadId?: (id: string) => void;
};

export function useSyllabusAgent({ threadId, onThreadId }: StreamOpts = {}) {
  const base = {
    apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? AGENT_URL,
    assistantId: ASSISTANT_ID,
    messagesKey: "messages" as const,
    reconnectOnMount: true,
    fetchStateHistory: true,
    onThreadId,
  };
  // IMPORTANT: omit the `threadId` key entirely when we don't have one, so the
  // SDK's `useControllableThreadId` falls back to uncontrolled mode and the
  // thread it auto-creates on the first submit is used for subsequent submits
  // (instead of resetting to null on every render and creating a new thread).
  const options = threadId ? { ...base, threadId } : base;
  return useStream<{ messages: any[] }>(options as any);
}
