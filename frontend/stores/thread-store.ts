"use client";
import { create } from "zustand";

interface ThreadStoreState {
  activeThreadId: string | null;
  isGlobalPollingEnabled: boolean;
  setActiveThread: (id: string | null) => void;
  setGlobalPolling: (enabled: boolean) => void;
}

export const useThreadStore = create<ThreadStoreState>((set) => ({
  activeThreadId: null,
  isGlobalPollingEnabled: true,
  setActiveThread: (id) => set({ activeThreadId: id }),
  setGlobalPolling: (enabled) => set({ isGlobalPollingEnabled: enabled }),
}));
