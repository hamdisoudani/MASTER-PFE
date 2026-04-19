"use client";
import { Client } from "@langchain/langgraph-sdk";

const DEFAULT_AGENT_URL = "https://agent-production-43c3.up.railway.app";
const DEFAULT_CLASSIC_ASSISTANT = "syllabus_agent";
const DEFAULT_DEEP_ASSISTANT = "syllabus_agent_deep";

function nonEmpty(v: string | undefined | null): string | undefined {
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t.length > 0 ? t : undefined;
}

export const LANGGRAPH_API_URL =
  nonEmpty(process.env.NEXT_PUBLIC_LANGGRAPH_URL) ?? DEFAULT_AGENT_URL;

export const CLASSIC_ASSISTANT_ID =
  nonEmpty(process.env.NEXT_PUBLIC_ASSISTANT_ID) ?? DEFAULT_CLASSIC_ASSISTANT;

export const DEEP_ASSISTANT_ID =
  nonEmpty(process.env.NEXT_PUBLIC_DEEP_ASSISTANT_ID) ?? DEFAULT_DEEP_ASSISTANT;

// Back-compat export: existing code that imports `ASSISTANT_ID` keeps working
// and falls back to the classic agent.
export const ASSISTANT_ID = CLASSIC_ASSISTANT_ID;

export type AgentVariant = "classic" | "deep";

export function assistantIdFor(variant: AgentVariant | undefined | null): string {
  return variant === "deep" ? DEEP_ASSISTANT_ID : CLASSIC_ASSISTANT_ID;
}

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
