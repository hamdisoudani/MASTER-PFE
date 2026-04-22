"use client";
/**
 * Per-thread message snapshot cache (localStorage-backed).
 *
 * Purpose: when the user reloads the page while a thread is in-flight, we
 * want to paint the chat from this cache immediately and only reconnect the
 * live SSE stream -- without downloading the full state history from the
 * server (`fetchStateHistory: true` on `useStream` is what produces the
 * 1 Mbit/s spike reported on reconnect).
 *
 * Writes are throttled by the caller (ChatPane) on every `values.messages`
 * update. Cache stores the tail 200 messages so localStorage stays under the
 * 5 MB budget even for multi-hour threads.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

const MAX_CACHED_MESSAGES = 200;
const STALE_MS = 1000 * 60 * 60 * 24; // 24h -- older entries are GC'd at read

type CacheEntry = { messages: any[]; updatedAt: number };

interface ThreadMessagesCacheState {
  entries: Record<string, CacheEntry>;
  get: (threadId: string) => CacheEntry | undefined;
  has: (threadId: string) => boolean;
  set: (threadId: string, messages: any[]) => void;
  clear: (threadId: string) => void;
  clearAll: () => void;
}

export const useThreadMessagesCache = create<ThreadMessagesCacheState>()(
  persist(
    (set, get) => ({
      entries: {},
      get: (threadId) => {
        const e = get().entries[threadId];
        if (!e) return undefined;
        if (Date.now() - e.updatedAt > STALE_MS) return undefined;
        return e;
      },
      has: (threadId) => {
        const e = get().entries[threadId];
        return !!e && Date.now() - e.updatedAt <= STALE_MS && e.messages.length > 0;
      },
      set: (threadId, messages) => {
        const tail = messages.length > MAX_CACHED_MESSAGES
          ? messages.slice(messages.length - MAX_CACHED_MESSAGES)
          : messages;
        set((s) => ({
          entries: {
            ...s.entries,
            [threadId]: { messages: tail, updatedAt: Date.now() },
          },
        }));
      },
      clear: (threadId) =>
        set((s) => {
          const { [threadId]: _drop, ...rest } = s.entries;
          return { entries: rest };
        }),
      clearAll: () => set({ entries: {} }),
    }),
    {
      name: "mpfe-thread-messages-cache-v1",
      storage: createJSONStorage(() =>
        typeof window === "undefined"
          ? (undefined as any)
          : window.localStorage
      ),
      partialize: (s) => ({ entries: s.entries }),
      version: 1,
    }
  )
);
