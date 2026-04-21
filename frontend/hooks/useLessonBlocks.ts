"use client";
import { useEffect } from "react";
import { fetchLessonBlocks } from "@/lib/curriculumApi";
import { useSyllabusStore, toBlockArray } from "@/store/syllabusStore";

/**
 * Fetch the full blocks array for a lesson exactly once per page load
 * (idempotent via `lesson.blocksLoaded`). Called from the editor wrapper
 * when a lesson becomes active.
 *
 * Re-fetching is skipped if:
 *   - lessonId is null
 *   - or the lesson already has `blocksLoaded === true`
 *     (cleared only by a full page reload, per product requirement).
 *
 * Realtime updates for blocks are intentionally NOT streamed to avoid
 * clobbering the editor while the user types. If the agent rewrites the
 * lesson, the realtime lesson-meta event will bump `version` and the
 * editor remounts (see BlockNoteEditor key={`${id}:${version}`}) which
 * triggers another fetch.
 */
export function useLessonBlocks(lessonId: string | null | undefined) {
  const applyRemoteLessonBlocks = useSyllabusStore((s) => s.applyRemoteLessonBlocks);

  useEffect(() => {
    if (!lessonId) return;
    const state = useSyllabusStore.getState();
    const lesson = state.getLessonById(lessonId);
    if (lesson?.blocksLoaded) return;

    let cancelled = false;
    (async () => {
      try {
        const row = await fetchLessonBlocks(lessonId);
        if (cancelled || !row) return;
        applyRemoteLessonBlocks(lessonId, toBlockArray(row.blocks), row.version);
      } catch (err) {
        console.warn("[useLessonBlocks] fetch failed:", err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [lessonId, applyRemoteLessonBlocks]);
}
