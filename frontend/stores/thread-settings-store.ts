"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ThreadSettings {
  autoAccept: boolean;
}

interface ThreadSettingsState {
  byThread: Record<string, ThreadSettings>;
  getSettings: (threadId: string | null | undefined) => ThreadSettings;
  getAutoAccept: (threadId: string | null | undefined) => boolean;
  setAutoAccept: (threadId: string | null | undefined, enabled: boolean) => void;
  toggleAutoAccept: (threadId: string | null | undefined) => void;
  clearThread: (threadId: string) => void;
}

const DEFAULT_SETTINGS: ThreadSettings = { autoAccept: false };
const NO_THREAD_KEY = "__default__";

function keyFor(threadId: string | null | undefined): string {
  return threadId && threadId.length > 0 ? threadId : NO_THREAD_KEY;
}

export const useThreadSettingsStore = create<ThreadSettingsState>()(
  persist(
    (set, get) => ({
      byThread: {},
      getSettings: (threadId) => {
        const key = keyFor(threadId);
        return get().byThread[key] ?? DEFAULT_SETTINGS;
      },
      getAutoAccept: (threadId) => {
        const key = keyFor(threadId);
        return get().byThread[key]?.autoAccept ?? false;
      },
      setAutoAccept: (threadId, enabled) => {
        const key = keyFor(threadId);
        set((state) => ({
          byThread: {
            ...state.byThread,
            [key]: { ...(state.byThread[key] ?? DEFAULT_SETTINGS), autoAccept: enabled },
          },
        }));
      },
      toggleAutoAccept: (threadId) => {
        const key = keyFor(threadId);
        set((state) => {
          const prev = state.byThread[key] ?? DEFAULT_SETTINGS;
          return {
            byThread: {
              ...state.byThread,
              [key]: { ...prev, autoAccept: !prev.autoAccept },
            },
          };
        });
      },
      clearThread: (threadId) => {
        set((state) => {
          if (!(threadId in state.byThread)) return state;
          const next = { ...state.byThread };
          delete next[threadId];
          return { byThread: next };
        });
      },
    }),
    { name: "thread-settings-v1", version: 1 }
  )
);
