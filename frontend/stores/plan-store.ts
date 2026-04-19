import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type PlanItemStatus = 'pending' | 'in_progress' | 'done';

export interface PlanItem {
  id: string;
  title: string;
  status: PlanItemStatus;
}

interface PlanSlice {
  items: PlanItem[];
}

const emptySlice = (): PlanSlice => ({ items: [] });

interface PlanStore {
  byThread: Record<string, PlanSlice>;
  currentThreadId: string | null;
  items: PlanItem[];

  setCurrentThread: (threadId: string | null) => void;
  setPlan: (
    items: Array<{ id?: string; title: string; status?: PlanItemStatus }>
  ) => PlanItem[];
  updatePlanItem: (id: string, status: PlanItemStatus) => PlanItem | null;
  clearPlan: () => void;
}

const DEFAULT_BUCKET = '__default__';
const keyOf = (state: { currentThreadId: string | null }) =>
  state.currentThreadId ?? DEFAULT_BUCKET;

const rand = () =>
  Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);

const normalizeId = (raw: string | undefined, fallback: string): string => {
  const v = (raw ?? '').trim();
  return v.length > 0 ? v : fallback;
};

const updateSlice = (
  state: PlanStore,
  updater: (slice: PlanSlice) => PlanSlice
): Partial<PlanStore> => {
  const key = keyOf(state);
  const prev = state.byThread[key] ?? emptySlice();
  const next = updater(prev);
  return {
    byThread: { ...state.byThread, [key]: next },
    items: next.items,
  };
};

export const usePlanStore = create<PlanStore>()(
  persist(
    (set, get) => ({
      byThread: {},
      currentThreadId: null,
      items: [],

      setCurrentThread: (threadId) =>
        set((state) => {
          const key = threadId ?? DEFAULT_BUCKET;
          const slice = state.byThread[key] ?? emptySlice();
          return {
            byThread: state.byThread[key] ? state.byThread : { ...state.byThread, [key]: slice },
            currentThreadId: threadId,
            items: slice.items,
          };
        }),

      setPlan: (items) => {
        let out: PlanItem[] = [];
        set((state) =>
          updateSlice(state, () => {
            out = items.map((it, i) => ({
              id: normalizeId(it.id, `todo-${i}-${rand()}`),
              title: String(it.title ?? '').trim() || `Task ${i + 1}`,
              status: (it.status as PlanItemStatus) ?? 'pending',
            }));
            return { items: out };
          })
        );
        return out;
      },

      updatePlanItem: (id, status) => {
        let updated: PlanItem | null = null;
        set((state) =>
          updateSlice(state, (slice) => {
            const items = slice.items.map((it) => {
              if (it.id === id) {
                const next = { ...it, status };
                updated = next;
                return next;
              }
              return it;
            });
            return { items };
          })
        );
        return updated;
      },

      clearPlan: () => set((state) => updateSlice(state, () => ({ items: [] }))),
    }),
    {
      name: 'plan-store',
      version: 1,
    }
  )
);
