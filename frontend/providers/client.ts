"use client";
import { Client } from "@langchain/langgraph-sdk";

const AGENT_URL = "https://agent-production-43c3.up.railway.app";

let _client: Client | null = null;
export function getLangGraphClient(): Client {
  if (_client) return _client;
  const apiUrl = process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? AGENT_URL;
  _client = new Client({ apiUrl });
  return _client;
}

export const ASSISTANT_ID =
  process.env.NEXT_PUBLIC_ASSISTANT_ID ?? "syllabus_agent";
