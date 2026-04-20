import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface InlineContent {
  type: 'text';
  text: string;
  styles: Record<string, unknown>;
}

export interface Block {
  id: string;
  type: string;
  props: Record<string, unknown>;
  content: InlineContent[];
  children: Block[];
}

export interface Lesson {
  id: string;
  title: string;
  content: Block[];
}

export interface Chapter {
  id: string;
  syllabusId: string;
  title: string;
  description?: string;
  lessons: Lesson[];
  isExpanded: boolean;
}

export interface Syllabus {
  id: string;
  title: string;
  subject: string;
  description?: string;
  chapters: Chapter[];
  createdAt: string;
}

/**
 * Diff record captured by each agent-driven mutation so the tool card can
 * render an old-vs-new view even after the store has already been updated.
 */
export interface LessonMutation {
  op: 'replace' | 'append';
  previous: Block[];
  next: Block[];
  at: string;
  error?: string | null;
}

/**
 * Per-thread slice: each chat thread owns its own file tree + editor state.
 * Switching threads swaps the active slice; the on-screen `syllabi`,
 * `activeSyllabusId`, `activeItemId`, `renderErrors`, `lastMutation` fields
 * are live mirrors of the current slice so no consumer needs to change.
 */
export interface ThreadSyllabusSlice {
  syllabi: Syllabus[];
  activeSyllabusId: string | null;
  activeItemId: string | null;
  renderErrors: Record<string, string>;
  lastMutation: Record<string, LessonMutation>;
}


/**
 * Coerce any persisted or agent-supplied "content" value into a safe Block[].
 * Earlier agent runs sometimes sent a JSON string or an object like {blocks:[...]}
 * which caused runtime crashes (".slice(...).map is not a function") when the
 * store assumed a plain array. This normalizes without losing data.
 */
export function toBlockArray(raw: unknown): Block[] {
  if (Array.isArray(raw)) return raw as Block[];
  if (raw == null) return [];
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed as Block[];
      if (parsed && Array.isArray((parsed as any).blocks)) return (parsed as any).blocks as Block[];
    } catch { /* fall through to markdown-wrap */ }
    return [
      {
        id: `blk_${Math.random().toString(36).slice(2, 10)}`,
        type: 'paragraph',
        props: {},
        content: [{ type: 'text', text: trimmed, styles: {} }],
        children: [],
      } as Block,
    ];
  }
  if (typeof raw === 'object') {
    const obj = raw as any;
    if (Array.isArray(obj.blocks)) return obj.blocks as Block[];
    if (Array.isArray(obj.content)) return obj.content as Block[];
  }
  return [];
}

const DEFAULT_BUCKET = '__default__';

const emptySlice = (): ThreadSyllabusSlice => ({
  syllabi: [],
  activeSyllabusId: null,
  activeItemId: null,
  renderErrors: {},
  lastMutation: {},
});

interface SyllabusStore extends ThreadSyllabusSlice {
  byThread: Record<string, ThreadSyllabusSlice>;
  currentThreadId: string | null;

  setCurrentThread: (threadId: string | null) => void;
  resetThread: (threadId?: string | null) => void;

  createSyllabus: (id: string, title: string, subject: string, description?: string) => void;
  addChapter: (syllabusId: string, chapterId: string, title: string, description?: string) => void;
  addLesson: (chapterId: string, lessonId: string, title: string, content: Block[]) => void;
  updateLessonContent: (lessonId: string, content: Block[]) => void;
  appendLessonContent: (lessonId: string, blocks: Block[]) => void;
  recordMutation: (lessonId: string, mutation: LessonMutation) => void;
  removeSyllabus: (syllabusId: string) => void;
  removeChapter: (chapterId: string) => void;
  removeLesson: (lessonId: string) => void;
  setActiveItem: (id: string | null) => void;
  toggleChapter: (chapterId: string) => void;
  setActiveSyllabus: (id: string) => void;
  setRenderError: (lessonId: string, error: string | null) => void;
  getLessonById: (lessonId: string) => Lesson | null;
  getActiveLesson: () => Lesson | null;
  getActiveSyllabus: () => Syllabus | null;
  patchLessonBlocks: (
    lessonId: string,
    op: 'replace' | 'insert' | 'delete',
    startBlock: number,
    endBlock: number | null,
    blocks: Block[]
  ) => { ok: boolean; error?: string; changed?: number; totalBlocks?: number };
  getSyllabusOutline: (syllabusId?: string) => {
    syllabusId: string | null;
    title: string | null;
    subject: string | null;
    description?: string;
    chapters: Array<{
      id: string;
      title: string;
      description?: string;
      lessons: Array<{ id: string; title: string; blockCount: number }>;
    }>;
    allSyllabi: Array<{ id: string; title: string; subject: string }>;
  };
  readLessonBlocks: (
    lessonId: string,
    startBlock: number,
    endBlock: number
  ) => {
    ok: boolean;
    error?: string;
    lessonId?: string;
    title?: string;
    totalBlocks?: number;
    start?: number;
    end?: number;
    blocks?: Array<{ index: number; id: string; type: string; text: string }>;
  };
}

/** Resolve the bucket key for the slice currently bound to the UI. */
function keyOf(state: { currentThreadId: string | null }): string {
  return state.currentThreadId ?? DEFAULT_BUCKET;
}

/**
 * Apply a pure slice update for the active thread and mirror the result to
 * the top-level fields so existing selectors (`syllabi`, `activeSyllabusId`,
 * `activeItemId`, …) keep working without any call-site changes.
 */
function updateSlice(
  state: SyllabusStore,
  updater: (slice: ThreadSyllabusSlice) => ThreadSyllabusSlice
): Partial<SyllabusStore> {
  const key = keyOf(state);
  const current = state.byThread[key] ?? emptySlice();
  const next = updater(current);
  return {
    byThread: { ...state.byThread, [key]: next },
    syllabi: next.syllabi,
    activeSyllabusId: next.activeSyllabusId,
    activeItemId: next.activeItemId,
    renderErrors: next.renderErrors,
    lastMutation: next.lastMutation,
  };
}

/**
 * @deprecated (PR4) — Lesson/chapter/syllabus mutations are now performed by
 * the agent via the curriculum-mcp server, which writes directly to Supabase.
 * The browser should treat the store as read-only for these entities and
 * rely on a Supabase realtime subscription to stay in sync. These methods
 * remain here only as a reference and a local-fallback for offline demos.
 */
export const useSyllabusStore = create<SyllabusStore>()(
  persist(
    (set, get) => ({
      byThread: {},
      currentThreadId: null,
      syllabi: [],
      activeSyllabusId: null,
      activeItemId: null,
      renderErrors: {},
      lastMutation: {},

      setCurrentThread: (threadId) =>
        set((state) => {
          const key = threadId ?? DEFAULT_BUCKET;
          const slice = state.byThread[key] ?? emptySlice();
          const byThread = state.byThread[key]
            ? state.byThread
            : { ...state.byThread, [key]: slice };
          return {
            currentThreadId: threadId,
            byThread,
            syllabi: slice.syllabi,
            activeSyllabusId: slice.activeSyllabusId,
            activeItemId: slice.activeItemId,
            renderErrors: slice.renderErrors,
            lastMutation: slice.lastMutation,
          };
        }),

      resetThread: (threadId) =>
        set((state) => {
          const key = threadId ?? keyOf(state);
          const byThread = { ...state.byThread, [key]: emptySlice() };
          const isActive = key === keyOf(state);
          const fresh = emptySlice();
          return isActive
            ? {
                byThread,
                syllabi: fresh.syllabi,
                activeSyllabusId: fresh.activeSyllabusId,
                activeItemId: fresh.activeItemId,
                renderErrors: fresh.renderErrors,
                lastMutation: fresh.lastMutation,
              }
            : { byThread };
        }),

      // @deprecated (PR4) — use curriculum-mcp via the agent; see syllabusStore banner.
      createSyllabus: (id, title, subject, description) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: [
              ...s.syllabi.filter((x) => x.id !== id),
              {
                id,
                title,
                subject,
                description,
                chapters: [],
                createdAt: new Date().toISOString(),
              },
            ],
            activeSyllabusId: id,
          }))
        ),

      // @deprecated (PR4) — use curriculum-mcp via the agent; see syllabusStore banner.
      addChapter: (syllabusId, chapterId, title, description) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: s.syllabi.map((x) =>
              x.id === syllabusId
                ? {
                    ...x,
                    chapters: [
                      ...x.chapters.filter((c) => c.id !== chapterId),
                      {
                        id: chapterId,
                        syllabusId,
                        title,
                        description,
                        lessons: [],
                        isExpanded: true,
                      },
                    ],
                  }
                : x
            ),
          }))
        ),

      // @deprecated (PR4) — use curriculum-mcp via the agent; see syllabusStore banner.
      addLesson: (chapterId, lessonId, title, content) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: s.syllabi.map((x) => ({
              ...x,
              chapters: x.chapters.map((ch) =>
                ch.id === chapterId
                  ? {
                      ...ch,
                      lessons: [
                        ...ch.lessons.filter((l) => l.id !== lessonId),
                        { id: lessonId, title, content: toBlockArray(content) },
                      ],
                    }
                  : ch
              ),
            })),
            activeItemId: lessonId,
          }))
        ),

      // @deprecated (PR4) — use curriculum-mcp via the agent; see syllabusStore banner.
      updateLessonContent: (lessonId, content) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: s.syllabi.map((x) => ({
              ...x,
              chapters: x.chapters.map((ch) => ({
                ...ch,
                lessons: ch.lessons.map((l) =>
                  l.id === lessonId ? { ...l, content: toBlockArray(content) } : l
                ),
              })),
            })),
          }))
        ),

      // @deprecated (PR4) — use curriculum-mcp via the agent; see syllabusStore banner.
      appendLessonContent: (lessonId, blocks) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: s.syllabi.map((x) => ({
              ...x,
              chapters: x.chapters.map((ch) => ({
                ...ch,
                lessons: ch.lessons.map((l) =>
                  l.id === lessonId
                    ? { ...l, content: [...toBlockArray(l.content), ...toBlockArray(blocks)] }
                    : l
                ),
              })),
            })),
          }))
        ),

      recordMutation: (lessonId, mutation) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            lastMutation: { ...s.lastMutation, [lessonId]: mutation },
          }))
        ),

      removeSyllabus: (syllabusId) =>
        set((state) =>
          updateSlice(state, (s) => {
            const removedLessonIds = new Set(
              s.syllabi
                .find((x) => x.id === syllabusId)
                ?.chapters.flatMap((c) => c.lessons.map((l) => l.id)) ?? []
            );
            const syllabi = s.syllabi.filter((x) => x.id !== syllabusId);
            return {
              ...s,
              syllabi,
              activeSyllabusId:
                s.activeSyllabusId === syllabusId
                  ? (syllabi[0]?.id ?? null)
                  : s.activeSyllabusId,
              activeItemId:
                s.activeItemId && removedLessonIds.has(s.activeItemId)
                  ? null
                  : s.activeItemId,
            };
          })
        ),

      removeChapter: (chapterId) =>
        set((state) =>
          updateSlice(state, (s) => {
            const chapter = s.syllabi
              .flatMap((x) => x.chapters)
              .find((ch) => ch.id === chapterId);
            const lessonIds = new Set(chapter?.lessons.map((l) => l.id) ?? []);
            return {
              ...s,
              syllabi: s.syllabi.map((x) => ({
                ...x,
                chapters: x.chapters.filter((ch) => ch.id !== chapterId),
              })),
              activeItemId:
                s.activeItemId && lessonIds.has(s.activeItemId)
                  ? null
                  : s.activeItemId,
            };
          })
        ),

      removeLesson: (lessonId) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: s.syllabi.map((x) => ({
              ...x,
              chapters: x.chapters.map((ch) => ({
                ...ch,
                lessons: ch.lessons.filter((l) => l.id !== lessonId),
              })),
            })),
            activeItemId: s.activeItemId === lessonId ? null : s.activeItemId,
          }))
        ),

      setActiveItem: (id) =>
        set((state) => updateSlice(state, (s) => ({ ...s, activeItemId: id }))),

      toggleChapter: (chapterId) =>
        set((state) =>
          updateSlice(state, (s) => ({
            ...s,
            syllabi: s.syllabi.map((x) => ({
              ...x,
              chapters: x.chapters.map((ch) =>
                ch.id === chapterId ? { ...ch, isExpanded: !ch.isExpanded } : ch
              ),
            })),
          }))
        ),

      setActiveSyllabus: (id) =>
        set((state) => updateSlice(state, (s) => ({ ...s, activeSyllabusId: id }))),

      setRenderError: (lessonId, error) =>
        set((state) =>
          updateSlice(state, (s) => {
            const errors = { ...s.renderErrors };
            if (error === null) delete errors[lessonId];
            else errors[lessonId] = error;
            return { ...s, renderErrors: errors };
          })
        ),

      // @deprecated (PR4) — use curriculum-mcp via the agent; see syllabusStore banner.
      patchLessonBlocks: (lessonId, op, startBlock, endBlock, blocks) => {
        let result: { ok: boolean; error?: string; changed?: number; totalBlocks?: number } = { ok: false, error: 'unknown' };
        set((state) =>
          updateSlice(state, (s) => {
            let found = false;
            let outcome = result;
            const syllabi = s.syllabi.map((syl) => ({
              ...syl,
              chapters: syl.chapters.map((ch) => ({
                ...ch,
                lessons: ch.lessons.map((l) => {
                  if (l.id !== lessonId) return l;
                  found = true;
                  const current = toBlockArray(l.content);
                  const total = current.length;
                  const start1 = Math.max(1, Math.floor(startBlock || 1));
                  const end1 = endBlock == null ? start1 : Math.max(start1, Math.floor(endBlock));
                  const startIdx = Math.min(start1 - 1, total);
                  const endIdx = Math.min(end1, total);
                  const insertBlocks = toBlockArray(blocks);
                  let nextContent = current;
                  let changed = 0;
                  if (op === 'replace') {
                    nextContent = [
                      ...current.slice(0, startIdx),
                      ...insertBlocks,
                      ...current.slice(endIdx),
                    ];
                    changed = Math.max(endIdx - startIdx, insertBlocks.length);
                  } else if (op === 'insert') {
                    nextContent = [
                      ...current.slice(0, startIdx),
                      ...insertBlocks,
                      ...current.slice(startIdx),
                    ];
                    changed = insertBlocks.length;
                  } else if (op === 'delete') {
                    nextContent = [
                      ...current.slice(0, startIdx),
                      ...current.slice(endIdx),
                    ];
                    changed = Math.max(0, endIdx - startIdx);
                  } else {
                    outcome = { ok: false, error: `unknown op: ${op}` };
                    return l;
                  }
                  outcome = { ok: true, changed, totalBlocks: nextContent.length };
                  return { ...l, content: nextContent };
                }),
              })),
            }));
            if (!found) {
              outcome = { ok: false, error: `lesson not found: ${lessonId}` };
              return s;
            }
            result = outcome;
            const mutation: LessonMutation = {
              op: op === 'insert' ? 'append' : 'replace',
              previous: [],
              next: [],
              at: new Date().toISOString(),
            };
            return { ...s, syllabi, lastMutation: { ...s.lastMutation, [lessonId]: mutation } };
          })
        );
        return result;
      },

      getSyllabusOutline: (syllabusId) => {
        const { syllabi, activeSyllabusId } = get();
        const target =
          (syllabusId && syllabi.find((s) => s.id === syllabusId)) ||
          syllabi.find((s) => s.id === activeSyllabusId) ||
          syllabi[0] ||
          null;
        const allSyllabi = syllabi.map((s) => ({ id: s.id, title: s.title, subject: s.subject }));
        if (!target) {
          return {
            syllabusId: null,
            title: null,
            subject: null,
            chapters: [],
            allSyllabi,
          };
        }
        return {
          syllabusId: target.id,
          title: target.title,
          subject: target.subject,
          description: target.description,
          chapters: target.chapters.map((ch) => ({
            id: ch.id,
            title: ch.title,
            description: ch.description,
            lessons: ch.lessons.map((l) => ({
              id: l.id,
              title: l.title,
              blockCount: toBlockArray(l.content).length,
            })),
          })),
          allSyllabi,
        };
      },

      readLessonBlocks: (lessonId, startBlock, endBlock) => {
        const { getLessonById } = get();
        const lesson = getLessonById(lessonId);
        if (!lesson) return { ok: false, error: `lesson not found: ${lessonId}` };
        const total = toBlockArray(lesson.content).length;
        const start1 = Math.max(1, Math.floor(startBlock || 1));
        const end1 = Math.max(start1, Math.floor(endBlock || total));
        const startIdx = Math.min(start1 - 1, total);
        const endIdx = Math.min(end1, total);
        const slice = toBlockArray(lesson.content).slice(startIdx, endIdx);
        const blocks = slice.map((b, i) => {
          const text = (b.content || [])
            .map((c: any) => (typeof c?.text === 'string' ? c.text : ''))
            .join('');
          return { index: startIdx + i + 1, id: b.id, type: b.type, text };
        });
        return {
          ok: true,
          lessonId,
          title: lesson.title,
          totalBlocks: total,
          start: startIdx + 1,
          end: endIdx,
          blocks,
        };
      },

      getLessonById: (lessonId) => {
        const { syllabi } = get();
        for (const s of syllabi) {
          for (const ch of s.chapters) {
            const l = ch.lessons.find((x) => x.id === lessonId);
            if (l) return l;
          }
        }
        return null;
      },

      getActiveLesson: () => {
        const { syllabi, activeItemId } = get();
        if (!activeItemId) return null;
        for (const s of syllabi) {
          for (const ch of s.chapters) {
            const lesson = ch.lessons.find((l) => l.id === activeItemId);
            if (lesson) return lesson;
          }
        }
        return null;
      },

      getActiveSyllabus: () => {
        const { syllabi, activeSyllabusId } = get();
        return syllabi.find((s) => s.id === activeSyllabusId) ?? null;
      },
    }),
    {
      name: 'syllabus-store',
      version: 2,
      /**
       * v1 persisted a single flat `{ syllabi, activeSyllabusId, ... }` blob.
       * v2 partitions by thread under `byThread`. Migrate legacy blobs into
       * the `__default__` bucket so pre-thread data stays accessible whenever
       * no threadId is selected.
       */
      migrate: (persisted: any, version) => {
        if (!persisted) return persisted;
        if (version >= 2 && persisted.byThread) return persisted;
        const legacySlice: ThreadSyllabusSlice = {
          syllabi: persisted.syllabi ?? [],
          activeSyllabusId: persisted.activeSyllabusId ?? null,
          activeItemId: persisted.activeItemId ?? null,
          renderErrors: persisted.renderErrors ?? {},
          lastMutation: persisted.lastMutation ?? {},
        };
        return {
          byThread: { [DEFAULT_BUCKET]: legacySlice },
          currentThreadId: null,
          ...legacySlice,
        };
      },
    }
  )
);
