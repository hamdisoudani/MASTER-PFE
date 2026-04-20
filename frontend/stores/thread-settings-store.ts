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

// PR5 — curriculum writes now go through the Supabase-backed curriculum-mcp
// server, so there is no destructive frontend tool interrupt left that needs
// explicit approval (lesson mutations were retired in PR4). We default
// `autoAccept` to true so planning/ask-user flows run end-to-end without a
// manual approve click. Users can still toggle it off from the ChatPane.
// Previous default:
// const DEFAULT_SETTINGS: ThreadSettings = { autoAccept: false };
const DEFAULT_SETTINGS: ThreadSettings = { autoAccept: true };
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
        return get().byThread[key]?.autoAccept ?? DEFAULT_SETTINGS.autoAccept;
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
    { name: "thread-settings-v2", version: 2 }
  )
);
