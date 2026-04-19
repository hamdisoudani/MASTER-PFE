"use client";
import { useStream } from "@langchain/langgraph-sdk/react";

export function useSyllabusAgent(threadId?: string) {
  return useStream<{ messages: any[] }>({
    apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? "http://localhost:2024",
    assistantId: "syllabus_agent",
    threadId,
    messagesKey: "messages",
  });
}
