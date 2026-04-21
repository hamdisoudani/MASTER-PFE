"use client";
import { useEffect, useRef } from "react";
import { fetchLessonsMetaForChapter } from "@/lib/curriculumApi";
import { useSyllabusStore } from "@/store/syllabusStore";

/**
 * When `enabled` flips to true (chapter expanded), fetch lesson meta rows
 * for that chapter once. Further updates arrive via the realtime channel.
 */
export function useChapterLessons(chapterId: string, enabled: boolean) {
  const applyRemoteLessonMeta = useSyllabusStore((s) => s.applyRemoteLessonMeta);
  const loaded = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!enabled || !chapterId || loaded.current.has(chapterId)) return;
    loaded.current.add(chapterId);
    let cancelled = false;
    (async () => {
      try {
        const rows = await fetchLessonsMetaForChapter(chapterId);
        if (cancelled) return;
        for (const r of rows) applyRemoteLessonMeta(r);
      } catch (err) {
        console.warn("[useChapterLessons] fetch failed:", err);
        loaded.current.delete(chapterId);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chapterId, enabled, applyRemoteLessonMeta]);
}
