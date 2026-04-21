"use client";
import { getSupabase } from "./supabase";
import type { Block } from "@/store/syllabusStore";

/**
 * Thin read helpers around the curriculum tables. These are used for the
 * initial hydration (page-load and on-demand expand/select); ongoing
 * updates come from the realtime subscription instead.
 *
 * The MCP server remains the only writer for agent-driven mutations.
 * User-driven edits from the BlockNote editor can use `saveLessonBlocks`
 * for direct persistence.
 */

export interface SyllabusRow {
  id: string;
  thread_id: string;
  title: string;
  description: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ChapterRow {
  id: string;
  syllabus_id: string;
  position: number;
  title: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface LessonMetaRow {
  id: string;
  chapter_id: string;
  position: number;
  title: string;
  block_count: number;
  version: number;
  last_author: string | null;
  updated_at: string;
}

export interface LessonBlocksRow {
  id: string;
  title: string;
  blocks: Block[];
  version: number;
}

function sb() {
  const c = getSupabase();
  if (!c) throw new Error("Supabase client unavailable (missing env vars).");
  return c;
}

export async function fetchSyllabusByThread(threadId: string): Promise<SyllabusRow | null> {
  const { data, error } = await sb()
    .from("syllabi")
    .select("*")
    .eq("thread_id", threadId)
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return (data as SyllabusRow) ?? null;
}

export async function fetchChaptersForSyllabus(syllabusId: string): Promise<ChapterRow[]> {
  const { data, error } = await sb()
    .from("chapters")
    .select("*")
    .eq("syllabus_id", syllabusId)
    .order("position", { ascending: true });
  if (error) throw error;
  return (data as ChapterRow[]) ?? [];
}

export async function fetchLessonsMetaForChapter(chapterId: string): Promise<LessonMetaRow[]> {
  const { data, error } = await sb()
    .from("lessons")
    .select("id, chapter_id, position, title, block_count, version, last_author, updated_at")
    .eq("chapter_id", chapterId)
    .order("position", { ascending: true });
  if (error) throw error;
  return (data as LessonMetaRow[]) ?? [];
}

export async function fetchLessonBlocks(lessonId: string): Promise<LessonBlocksRow | null> {
  const { data, error } = await sb()
    .from("lessons")
    .select("id, title, blocks, version")
    .eq("id", lessonId)
    .maybeSingle();
  if (error) throw error;
  return (data as LessonBlocksRow) ?? null;
}

export async function saveLessonBlocks(
  lessonId: string,
  blocks: Block[],
  expectedVersion?: number
): Promise<{ version: number } | null> {
  let query = sb()
    .from("lessons")
    .update({ blocks, last_author: "user" })
    .eq("id", lessonId);
  if (typeof expectedVersion === "number") {
    query = query.eq("version", expectedVersion);
  }
  const { data, error } = await query.select("version").maybeSingle();
  if (error) throw error;
  return data as { version: number } | null;
}
