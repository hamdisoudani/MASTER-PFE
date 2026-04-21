"use client";
import { useEffect, useRef } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { getSupabase } from "@/lib/supabase";
import {
  fetchSyllabusByThread,
  fetchChaptersForSyllabus,
} from "@/lib/curriculumApi";
import { useSyllabusStore } from "@/store/syllabusStore";

/**
 * Subscribe the browser to realtime updates for a single thread's curriculum.
 *
 * On mount:
 *   1. Fetch `syllabi` row for the thread → apply to store.
 *   2. Fetch `chapters` for that syllabus → apply to store.
 *      (Lessons are fetched lazily when a chapter is expanded.)
 *   3. Open one Supabase realtime channel filtered to this thread's rows,
 *      subscribing to INSERT / UPDATE / DELETE on syllabi, chapters, lessons.
 *
 * Lesson events carry meta only — the full `blocks` array is NOT dispatched
 * to the store automatically, to avoid clobbering the active editor. When
 * the user opens a lesson, `useLessonBlocks` pulls the latest blocks. When
 * the lesson's version changes via realtime and the user is viewing it, the
 * editor remounts via the `version` key on BlockNoteEditor.
 *
 * The hook tolerates missing env vars (no-op) so local dev without Supabase
 * still loads.
 */
export function useSyllabusRealtime(threadId: string | null | undefined) {
  const applyRemoteSyllabus = useSyllabusStore((s) => s.applyRemoteSyllabus);
  const removeSyllabusById = useSyllabusStore((s) => s.removeSyllabusById);
  const applyRemoteChapter = useSyllabusStore((s) => s.applyRemoteChapter);
  const removeChapterById = useSyllabusStore((s) => s.removeChapterById);
  const applyRemoteLessonMeta = useSyllabusStore((s) => s.applyRemoteLessonMeta);
  const removeLessonById = useSyllabusStore((s) => s.removeLessonById);

  const channelRef = useRef<RealtimeChannel | null>(null);
  const syllabusIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!threadId) return;
    const supa = getSupabase();
    if (!supa) return;

    let cancelled = false;

    (async () => {
      try {
        const syl = await fetchSyllabusByThread(threadId);
        if (cancelled) return;
        if (syl) {
          syllabusIdRef.current = syl.id;
          applyRemoteSyllabus(syl);
          const chapters = await fetchChaptersForSyllabus(syl.id);
          if (cancelled) return;
          for (const ch of chapters) applyRemoteChapter(ch);
        }
      } catch (err) {
        console.warn("[useSyllabusRealtime] hydrate failed:", err);
      }

      if (cancelled) return;

      const channel = supa
        .channel(`curriculum:${threadId}`)
        // --- syllabi: filtered by thread_id ---
        .on(
          "postgres_changes",
          {
            event: "*",
            schema: "public",
            table: "syllabi",
            filter: `thread_id=eq.${threadId}`,
          },
          (payload) => {
            const t = payload.eventType;
            if (t === "DELETE") {
              const old = payload.old as { id?: string };
              if (old?.id) removeSyllabusById(old.id);
            } else {
              const row = payload.new as any;
              if (row?.id) {
                syllabusIdRef.current = row.id;
                applyRemoteSyllabus(row);
              }
            }
          }
        )
        // --- chapters: no server filter (Supabase only supports single eq
        // filters on ONE column), filter client-side by syllabus_id. Safe
        // because the realtime stream is low-volume in single-tenant mode.
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "chapters" },
          (payload) => {
            const synId = syllabusIdRef.current;
            const newRow = payload.new as any;
            const oldRow = payload.old as any;
            const belongs = (r: any) => r && synId && r.syllabus_id === synId;
            if (payload.eventType === "DELETE") {
              if (belongs(oldRow) && oldRow.id) removeChapterById(oldRow.id);
            } else if (belongs(newRow)) {
              applyRemoteChapter(newRow);
            }
          }
        )
        // --- lessons: filter client-side by chapter_id ∈ known chapters
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "lessons" },
          (payload) => {
            const newRow = payload.new as any;
            const oldRow = payload.old as any;
            const known = () => {
              const st = useSyllabusStore.getState();
              const allChapters = st.syllabi.flatMap((s) => s.chapters);
              return new Set(allChapters.map((c) => c.id));
            };
            if (payload.eventType === "DELETE") {
              if (oldRow?.id && known().has(oldRow.chapter_id)) {
                removeLessonById(oldRow.id);
              }
            } else if (newRow && known().has(newRow.chapter_id)) {
              applyRemoteLessonMeta(newRow);
            }
          }
        )
        .subscribe();

      channelRef.current = channel;
    })();

    return () => {
      cancelled = true;
      if (channelRef.current) {
        supa.removeChannel(channelRef.current);
        channelRef.current = null;
      }
      syllabusIdRef.current = null;
    };
  }, [
    threadId,
    applyRemoteSyllabus,
    removeSyllabusById,
    applyRemoteChapter,
    removeChapterById,
    applyRemoteLessonMeta,
    removeLessonById,
  ]);
}
