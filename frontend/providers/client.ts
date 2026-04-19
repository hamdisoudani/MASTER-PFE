"use client";
import { Client } from "@langchain/langgraph-sdk";

const DEFAULT_AGENT_URL = "https://agent-production-43c3.up.railway.app";
const DEFAULT_ASSISTANT = "syllabus_agent";

function nonEmpty(v: string | undefined | null): string | undefined {
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t.length > 0 ? t : undefined;
}

export const LANGGRAPH_API_URL =
  nonEmpty(process.env.NEXT_PUBLIC_LANGGRAPH_URL) ?? DEFAULT_AGENT_URL;

export const ASSISTANT_ID =
  nonEmpty(process.env.NEXT_PUBLIC_ASSISTANT_ID) ?? DEFAULT_ASSISTANT;

/** Optional API key for an auth-enabled LangGraph deployment. */
export function langgraphHeaders(): Record<string, string> | undefined {
  const key = nonEmpty(process.env.NEXT_PUBLIC_LANGGRAPH_API_KEY);
  return key ? { "x-api-key": key } : undefined;
}

let _client: Client | null = null;
export function getLangGraphClient(): Client {
  if (_client) return _client;
  _client = new Client({
    apiUrl: LANGGRAPH_API_URL,
    defaultHeaders: langgraphHeaders(),
  });
  return _client;
}
