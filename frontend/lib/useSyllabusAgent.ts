"use client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { ASSISTANT_ID } from "@/providers/client";

const AGENT_URL = "https://agent-production-43c3.up.railway.app";

export function useSyllabusAgent(threadId?: string | null) {
  return useStream<{ messages: any[] }>({
    apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? AGENT_URL,
    assistantId: ASSISTANT_ID,
    threadId: threadId ?? undefined,
    messagesKey: "messages",
    reconnectOnMount: true,
    fetchStateHistory: false,
  });
}
