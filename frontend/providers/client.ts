"use client";
import { Client } from "@langchain/langgraph-sdk";

const AGENT_URL = "https://agent-production-43c3.up.railway.app";
const DEFAULT_ASSISTANT = "syllabus_agent";

function nonEmpty(v: string | undefined | null): string | undefined {
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t.length > 0 ? t : undefined;
}

let _client: Client | null = null;
export function getLangGraphClient(): Client {
  if (_client) return _client;
  const apiUrl = nonEmpty(process.env.NEXT_PUBLIC_LANGGRAPH_URL) ?? AGENT_URL;
  _client = new Client({ apiUrl });
  return _client;
}

export const ASSISTANT_ID =
  nonEmpty(process.env.NEXT_PUBLIC_ASSISTANT_ID) ?? DEFAULT_ASSISTANT;
