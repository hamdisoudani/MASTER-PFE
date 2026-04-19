"use client";
import useSWR from "swr";
import type { Thread } from "@langchain/langgraph-sdk";
import { getLangGraphClient, ASSISTANT_ID } from "@/providers/client";

interface UseThreadsSWROptions {
  assistantId?: string | null;
  limit?: number;
  offset?: number;
  sortBy?: "created_at" | "updated_at";
  sortOrder?: "asc" | "desc";
  refreshInterval?: number;
  useMetadata?: boolean;
}

function isUuid(v: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
}

function metadataForAssistant(assistantId: string) {
  return isUuid(assistantId)
    ? { assistant_id: assistantId }
    : { graph_id: assistantId };
}

export function useThreadsSWR(opts: UseThreadsSWROptions = {}) {
  const {
    assistantId = ASSISTANT_ID,
    limit = 25,
    offset = 0,
    sortBy = "updated_at",
    sortOrder = "desc",
    refreshInterval = 0,
    useMetadata = false,
  } = opts;

  const key = [
    "threads",
    assistantId ?? "all",
    limit,
    offset,
    sortBy,
    sortOrder,
    useMetadata ? "meta" : "nometa",
  ];

  const swr = useSWR<Thread[]>(
    key,
    async () => {
      const client = getLangGraphClient();
      const base: any = { limit, offset, sortBy, sortOrder };
      if (useMetadata && assistantId) {
        const primary = metadataForAssistant(assistantId);
        let res = await client.threads.search({ ...base, metadata: primary });
        if (!res || res.length === 0) {
          const fallbackKey =
            "assistant_id" in primary ? "graph_id" : "assistant_id";
          res = await client.threads.search({
            ...base,
            metadata: { [fallbackKey]: assistantId },
          });
        }
        return res;
      }
      return client.threads.search(base);
    },
    {
      refreshInterval,
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
      keepPreviousData: true,
    }
  );

  return {
    threads: swr.data ?? [],
    isLoading: swr.isLoading,
    isValidating: swr.isValidating,
    mutate: swr.mutate,
    error: swr.error,
    hasMore: (swr.data?.length ?? 0) >= limit,
  };
}
