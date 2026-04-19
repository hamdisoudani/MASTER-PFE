"use client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { ASSISTANT_ID } from "@/providers/client";

const AGENT_URL = "https://agent-production-43c3.up.railway.app";

type StreamOpts = {
  threadId?: string | null;
  onThreadId?: (id: string) => void;
};

export function useSyllabusAgent({ threadId, onThreadId }: StreamOpts = {}) {
  return useStream<{ messages: any[] }>({
    apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? AGENT_URL,
    assistantId: ASSISTANT_ID,
    threadId: threadId ?? undefined,
    messagesKey: "messages",
    reconnectOnMount: true,
    fetchStateHistory: true,
    onThreadId: (id: string) => {
      onThreadId?.(id);
    },
  });
}
