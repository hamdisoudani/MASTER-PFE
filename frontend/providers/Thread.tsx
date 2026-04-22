"use client";
import React, { createContext, useCallback, useContext, useMemo } from "react";
import type { Thread } from "@langchain/langgraph-sdk";
import {
  getLangGraphClient,
  assistantIdFor,
  type AgentVariant,
} from "@/providers/client";
import { useThreadsSWR } from "@/hooks/useThreadsSWR";

interface ThreadContextValue {
  threads: Thread[];
  isLoading: boolean;
  isValidating: boolean;
  refreshThreads: () => Promise<any>;
  getThread: (id: string) => Promise<Thread | null>;
  /** `variant` is persisted in thread metadata and CANNOT be changed later. */
  createThread: (
    variant?: AgentVariant,
    extraMetadata?: Record<string, unknown>
  ) => Promise<Thread>;
  deleteThread: (id: string) => Promise<void>;
}

const ThreadContext = createContext<ThreadContextValue | null>(null);

export function ThreadProvider({
  children,
  useMetadata = false,
  refreshInterval = 0,
}: {
  children: React.ReactNode;
  useMetadata?: boolean;
  refreshInterval?: number;
}) {
  const { threads, isLoading, isValidating, mutate } = useThreadsSWR({
    useMetadata,
    refreshInterval,
  });

  const refreshThreads = useCallback(() => mutate(), [mutate]);

  const getThread = useCallback(async (id: string) => {
    try {
      return await getLangGraphClient().threads.get(id);
    } catch (e) {
      console.error("getThread failed", e);
      return null;
    }
  }, []);

  const createThread = useCallback(
    async (variant: AgentVariant = "classic", extraMetadata?: Record<string, unknown>) => {
      const graph_id = assistantIdFor(variant);
      const meta = { graph_id, variant, ...(extraMetadata ?? {}) };
      const t = await getLangGraphClient().threads.create({ metadata: meta });
      await mutate();
      return t;
    },
    [mutate]
  );

  const deleteThread = useCallback(
    async (id: string) => {
      await getLangGraphClient().threads.delete(id);
      await mutate();
    },
    [mutate]
  );

  const value = useMemo<ThreadContextValue>(
    () => ({
      threads,
      isLoading,
      isValidating,
      refreshThreads,
      getThread,
      createThread,
      deleteThread,
    }),
    [threads, isLoading, isValidating, refreshThreads, getThread, createThread, deleteThread]
  );

  return <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>;
}

export function useThreads() {
  const ctx = useContext(ThreadContext);
  if (!ctx) throw new Error("useThreads must be used inside <ThreadProvider>");
  return ctx;
}

/** Read the locked agent variant from a thread's metadata. Defaults to "classic". */
export function threadVariant(t: Thread | null | undefined): AgentVariant {
  const v = (t?.metadata as any)?.variant;
  if (v === "deep") return "deep";
  if (v === "v2") return "v2";
  return "classic";
}
