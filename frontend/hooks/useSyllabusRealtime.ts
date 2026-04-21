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
 *   1. Build ONE Supabase channel synchronously and register all
 *      `postgres_changes` handlers BEFORE calling `.subscribe()`. Supabase
 *      disallows adding handlers after subscribe, so we must not defer the
 *      `.on()` calls into an async block.
 *   2. Fetch `syllabi` row for the thread -> apply to store.
 *   3. Fetch `chapters` for that syllabus -> apply to store.
 *      (Lessons are fetched lazily when a chapter is expanded.)
 *   4. Call `.subscribe()` once hydration resolves (or is cancelled).
 *
 * The channel topic includes a per-mount random suffix so that rapid remounts
 * (StrictMode double-invoke, threadId change, HMR) never collide with a
 * channel the previous effect run hasn't finished tearing down yet. Without
 * this, `supa.channel(\`curriculum:${threadId}\`)` would return the cached,
 * already-subscribed channel and the chained `.on()` would throw:
 *   "cannot add `postgres_changes` callbacks for realtime:curriculum:... after `subscribe()`."
 *
 * Lesson events carry meta only - the full `blocks` array is NOT dispatched
 * to the store automatically, to avoid clobbering the active editor.
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

    // Unique topic per mount so rapid remounts never reuse a still-subscribed
    // channel from the previous effect run.
    const topicSuffix =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2);
    const topic = `curriculum:${threadId}:${topicSuffix}`;

    // Build channel + register ALL handlers synchronously, before subscribe().
    const channel = supa
      .channel(topic)
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
      );

    channelRef.current = channel;

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
      // Safe to subscribe now - all `.on()` handlers are already attached.
      channel.subscribe();
    })();

    return () => {
      cancelled = true;
      try {
        supa.removeChannel(channel);
      } catch {
        // no-op: channel may already be torn down
      }
      channelRef.current = null;
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
