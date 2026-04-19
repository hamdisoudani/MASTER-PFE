"use client";
import React, { createContext, useCallback, useContext, useMemo } from "react";
import type { Thread } from "@langchain/langgraph-sdk";
import { getLangGraphClient, ASSISTANT_ID } from "@/providers/client";
import { useThreadsSWR } from "@/hooks/useThreadsSWR";

interface ThreadContextValue {
  threads: Thread[];
  isLoading: boolean;
  isValidating: boolean;
  refreshThreads: () => Promise<any>;
  getThread: (id: string) => Promise<Thread | null>;
  createThread: (metadata?: Record<string, unknown>) => Promise<Thread>;
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
    async (metadata?: Record<string, unknown>) => {
      const meta = metadata ?? { graph_id: ASSISTANT_ID };
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

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}

export function useThreads() {
  const ctx = useContext(ThreadContext);
  if (!ctx) throw new Error("useThreads must be used inside <ThreadProvider>");
  return ctx;
}
