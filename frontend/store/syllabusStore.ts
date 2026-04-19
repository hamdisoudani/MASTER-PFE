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

interface SyllabusStore {
  syllabi: Syllabus[];
  activeSyllabusId: string | null;
  activeItemId: string | null;
  renderErrors: Record<string, string>;
  lastMutation: Record<string, LessonMutation>;

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
}

export const useSyllabusStore = create<SyllabusStore>()(
  persist(
    (set, get) => ({
      syllabi: [],
      activeSyllabusId: null,
      activeItemId: null,
      renderErrors: {},
      lastMutation: {},

      createSyllabus: (id, title, subject, description) =>
        set((state) => ({
          syllabi: [
            ...state.syllabi.filter((s) => s.id !== id),
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
        })),

      addChapter: (syllabusId, chapterId, title, description) =>
        set((state) => ({
          syllabi: state.syllabi.map((s) =>
            s.id === syllabusId
              ? {
                  ...s,
                  chapters: [
                    ...s.chapters.filter((c) => c.id !== chapterId),
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
              : s
          ),
        })),

      addLesson: (chapterId, lessonId, title, content) =>
        set((state) => ({
          syllabi: state.syllabi.map((s) => ({
            ...s,
            chapters: s.chapters.map((ch) =>
              ch.id === chapterId
                ? {
                    ...ch,
                    lessons: [
                      ...ch.lessons.filter((l) => l.id !== lessonId),
                      { id: lessonId, title, content: content || [] },
                    ],
                  }
                : ch
            ),
          })),
          activeItemId: lessonId,
        })),

      updateLessonContent: (lessonId, content) =>
        set((state) => ({
          syllabi: state.syllabi.map((s) => ({
            ...s,
            chapters: s.chapters.map((ch) => ({
              ...ch,
              lessons: ch.lessons.map((l) =>
                l.id === lessonId ? { ...l, content } : l
              ),
            })),
          })),
        })),

      appendLessonContent: (lessonId, blocks) =>
        set((state) => ({
          syllabi: state.syllabi.map((s) => ({
            ...s,
            chapters: s.chapters.map((ch) => ({
              ...ch,
              lessons: ch.lessons.map((l) =>
                l.id === lessonId
                  ? { ...l, content: [...(l.content || []), ...blocks] }
                  : l
              ),
            })),
          })),
        })),

      recordMutation: (lessonId, mutation) =>
        set((state) => ({
          lastMutation: { ...state.lastMutation, [lessonId]: mutation },
        })),

      removeSyllabus: (syllabusId) =>
        set((state) => ({
          syllabi: state.syllabi.filter((s) => s.id !== syllabusId),
          activeSyllabusId:
            state.activeSyllabusId === syllabusId
              ? (state.syllabi.find((s) => s.id !== syllabusId)?.id ?? null)
              : state.activeSyllabusId,
          activeItemId: state.syllabi
            .find((s) => s.id === syllabusId)
            ?.chapters.flatMap((c) => c.lessons)
            .some((l) => l.id === state.activeItemId)
            ? null
            : state.activeItemId,
        })),

      removeChapter: (chapterId) =>
        set((state) => {
          const chapter = state.syllabi
            .flatMap((s) => s.chapters)
            .find((ch) => ch.id === chapterId);
          const lessonIds = chapter?.lessons.map((l) => l.id) ?? [];
          return {
            syllabi: state.syllabi.map((s) => ({
              ...s,
              chapters: s.chapters.filter((ch) => ch.id !== chapterId),
            })),
            activeItemId: lessonIds.includes(state.activeItemId ?? '')
              ? null
              : state.activeItemId,
          };
        }),

      removeLesson: (lessonId) =>
        set((state) => ({
          syllabi: state.syllabi.map((s) => ({
            ...s,
            chapters: s.chapters.map((ch) => ({
              ...ch,
              lessons: ch.lessons.filter((l) => l.id !== lessonId),
            })),
          })),
          activeItemId:
            state.activeItemId === lessonId ? null : state.activeItemId,
        })),

      setActiveItem: (id) => set({ activeItemId: id }),

      toggleChapter: (chapterId) =>
        set((state) => ({
          syllabi: state.syllabi.map((s) => ({
            ...s,
            chapters: s.chapters.map((ch) =>
              ch.id === chapterId ? { ...ch, isExpanded: !ch.isExpanded } : ch
            ),
          })),
        })),

      setActiveSyllabus: (id) => set({ activeSyllabusId: id }),

      setRenderError: (lessonId, error) =>
        set((state) => {
          const errors = { ...state.renderErrors };
          if (error === null) {
            delete errors[lessonId];
          } else {
            errors[lessonId] = error;
          }
          return { renderErrors: errors };
        }),

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
    { name: 'syllabus-store' }
  )
);
