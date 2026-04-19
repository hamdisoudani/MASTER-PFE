"use client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { ASSISTANT_ID } from "@/providers/client";

export function useSyllabusAgent(threadId?: string | null) {
  return useStream<{ messages: any[] }>({
    apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? "http://localhost:2024",
    assistantId: ASSISTANT_ID,
    threadId: threadId ?? undefined,
    messagesKey: "messages",
    reconnectOnMount: true,
    fetchStateHistory: false,
  });
}
