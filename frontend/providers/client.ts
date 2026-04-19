"use client";
import { Client } from "@langchain/langgraph-sdk";

let _client: Client | null = null;
export function getLangGraphClient(): Client {
  if (_client) return _client;
  const apiUrl = process.env.NEXT_PUBLIC_LANGGRAPH_URL ?? "http://localhost:2024";
  _client = new Client({ apiUrl });
  return _client;
}

export const ASSISTANT_ID =
  process.env.NEXT_PUBLIC_ASSISTANT_ID ?? "syllabus_agent";
