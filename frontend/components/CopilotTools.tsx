"use client";

import React from "react";
import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useSyllabusStore } from "@/store/syllabusStore";
import type { Block, Lesson, Chapter, Syllabus, LessonMutation } from "@/store/syllabusStore";
import { validateBlockNoteContent } from "@/lib/blocknoteValidate";
import { CheckCircle2, Loader2, AlertTriangle, Plus, Minus } from "lucide-react";

function ToolCallCard({ title, status, args, error, children }: { title: string; status: "inProgress" | "executing" | "complete" | string; args?: Record<string, unknown>; error?: string | null; children?: React.ReactNode }) {
  const isRunning = status === "inProgress" || status === "executing";
  const isDone = status === "complete";
  return (
    <div
      className="my-2 rounded-[var(--radius)] px-3 py-2 text-xs"
      style={{
        fontFamily: "var(--font-sans)",
        background: "color-mix(in srgb, var(--card) 85%, transparent)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-center gap-2">
        {error ? (
          <AlertTriangle className="w-3.5 h-3.5" style={{ color: "var(--destructive)" }} />
        ) : isDone ? (
          <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--secondary)" }} />
        ) : (
          <Loader2 className={["w-3.5 h-3.5", isRunning ? "animate-spin" : ""].join(" ")} style={{ color: "var(--primary)" }} />
        )}
        <span className="text-[11px]" style={{ fontFamily: "var(--font-mono)", color: "var(--foreground)" }}>{title}</span>
        <span
          className="ml-auto text-[9px] px-1.5 py-0.5 rounded-[3px] uppercase tracking-[0.1em]"
          style={{
            fontFamily: "var(--font-mono)",
            color: error ? "var(--destructive)" : isDone ? "var(--secondary)" : "var(--primary)",
            background: "color-mix(in srgb, currentColor 12%, transparent)",
            border: "1px solid color-mix(in srgb, currentColor 30%, transparent)",
          }}
        >
          {error ? "error" : isDone ? "done" : "running"}
        </span>
      </div>
      {args && Object.keys(args).length > 0 && (
        <pre
          className="mt-1 text-[10px] leading-snug whitespace-pre-wrap break-words max-h-32 overflow-auto"
          style={{ fontFamily: "var(--font-mono)", color: "var(--muted-foreground)" }}
        >{JSON.stringify(args, null, 2)}</pre>
      )}
      {error && (<p className="mt-1 text-[10px]" style={{ color: "var(--destructive)" }}>{error}</p>)}
      {children}
    </div>
  );
}

/** Extract a short preview string from a BlockNote block's inline content. */
function blockPreview(b: Block | undefined): string {
  if (!b) return "";
  const c = b.content;
  if (Array.isArray(c)) {
    const parts: string[] = [];
    for (const piece of c) {
      if (piece && typeof piece === "object" && "text" in piece && typeof (piece as { text: unknown }).text === "string") {
        parts.push((piece as { text: string }).text);
      }
    }
    return parts.join(" ").trim();
  }
  return "";
}

/**
 * Render a git-style diff of two block arrays. Matches by block.id when
 * present, otherwise by positional index. This is a visual aid, not a
 * semantic merge — the actual mutation is always the full next[].
 */
function BlockDiff({ previous, next }: { previous: Block[]; next: Block[] }) {
  const prevIds = new Set(previous.map((b) => b.id).filter(Boolean));
  const nextIds = new Set(next.map((b) => b.id).filter(Boolean));
  type Row = { kind: "same" | "add" | "del" | "mod"; prev?: Block; next?: Block };
  const rows: Row[] = [];
  const max = Math.max(previous.length, next.length);
  for (let i = 0; i < max; i++) {
    const p = previous[i];
    const n = next[i];
    if (p && n) {
      const prevText = blockPreview(p);
      const nextText = blockPreview(n);
      if (p.id && n.id && p.id === n.id && prevText === nextText) rows.push({ kind: "same", prev: p, next: n });
      else if (prevText === nextText && p.type === n.type) rows.push({ kind: "same", prev: p, next: n });
      else rows.push({ kind: "mod", prev: p, next: n });
    } else if (p && !n) {
      rows.push({ kind: "del", prev: p });
    } else if (!p && n) {
      const isExistingMoved = n.id && prevIds.has(n.id) && !nextIds.has(n.id);
      rows.push({ kind: isExistingMoved ? "same" : "add", next: n });
    }
  }
  if (rows.length === 0) return null;
  return (
    <div className="mt-2 border rounded-[3px] overflow-hidden" style={{ borderColor: "var(--border)" }}>
      <div className="text-[9px] uppercase tracking-[0.12em] px-2 py-1" style={{ fontFamily: "var(--font-mono)", color: "var(--muted-foreground)", background: "color-mix(in srgb, var(--muted) 60%, transparent)" }}>
        diff · {rows.filter((r) => r.kind === "add").length} added · {rows.filter((r) => r.kind === "del").length} removed · {rows.filter((r) => r.kind === "mod").length} modified
      </div>
      <div className="max-h-56 overflow-auto">
        {rows.map((r, i) => {
          if (r.kind === "same") {
            return (
              <div key={i} className="flex gap-1 px-2 py-0.5 text-[10px]" style={{ fontFamily: "var(--font-mono)", color: "var(--muted-foreground)" }}>
                <span className="opacity-40 w-3 shrink-0">·</span>
                <span className="truncate">[{r.next?.type}] {blockPreview(r.next).slice(0, 120)}</span>
              </div>
            );
          }
          if (r.kind === "add") {
            return (
              <div key={i} className="flex gap-1 px-2 py-0.5 text-[10px]" style={{ fontFamily: "var(--font-mono)", color: "var(--secondary)", background: "color-mix(in srgb, var(--secondary) 10%, transparent)" }}>
                <Plus className="w-3 h-3 shrink-0" />
                <span className="truncate">[{r.next?.type}] {blockPreview(r.next).slice(0, 140)}</span>
              </div>
            );
          }
          if (r.kind === "del") {
            return (
              <div key={i} className="flex gap-1 px-2 py-0.5 text-[10px] line-through" style={{ fontFamily: "var(--font-mono)", color: "var(--destructive)", background: "color-mix(in srgb, var(--destructive) 10%, transparent)" }}>
                <Minus className="w-3 h-3 shrink-0" />
                <span className="truncate">[{r.prev?.type}] {blockPreview(r.prev).slice(0, 140)}</span>
              </div>
            );
          }
          return (
            <div key={i} className="px-2 py-0.5">
              <div className="flex gap-1 text-[10px] line-through" style={{ fontFamily: "var(--font-mono)", color: "var(--destructive)", background: "color-mix(in srgb, var(--destructive) 10%, transparent)" }}>
                <Minus className="w-3 h-3 shrink-0" />
                <span className="truncate">[{r.prev?.type}] {blockPreview(r.prev).slice(0, 140)}</span>
              </div>
              <div className="flex gap-1 text-[10px]" style={{ fontFamily: "var(--font-mono)", color: "var(--secondary)", background: "color-mix(in srgb, var(--secondary) 10%, transparent)" }}>
                <Plus className="w-3 h-3 shrink-0" />
                <span className="truncate">[{r.next?.type}] {blockPreview(r.next).slice(0, 140)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LessonDiffCard({ lessonId, title, status, args }: { lessonId?: string; title: string; status: string; args?: Record<string, unknown> }) {
  const mutation: LessonMutation | undefined = useSyllabusStore((s) => (lessonId ? s.lastMutation[lessonId] : undefined));
  const preview = args ? { lessonId: args.lessonId, blocks: Array.isArray(args.content) ? (args.content as unknown[]).length : 0 } : undefined;
  const err = mutation?.error ?? null;
  return (
    <ToolCallCard title={title} status={status} args={preview as Record<string, unknown> | undefined} error={err}>
      {mutation && !err && <BlockDiff previous={mutation.previous} next={mutation.next} />}
    </ToolCallCard>
  );
}

function approxLessonSize(blocks: Block[] | undefined): number {
  if (!blocks || blocks.length === 0) return 0;
  let n = 0;
  const walk = (bs: Block[]) => {
    for (const b of bs) {
      for (const c of b.content ?? []) {
        if (c && typeof c === "object" && "text" in c && typeof (c as { text: unknown }).text === "string") {
          n += ((c as { text: string }).text).length;
        }
      }
      if (b.children && b.children.length) walk(b.children);
    }
  };
  walk(blocks);
  return n;
}

function buildSkeleton(syllabi: Syllabus[], activeSyllabusId: string | null, activeItemId: string | null) {
  return {
    activeSyllabusId,
    activeItemId,
    syllabi: syllabi.map((s) => ({
      id: s.id,
      title: s.title,
      subject: s.subject,
      description: s.description,
      chapters: s.chapters.map((c: Chapter) => ({
        id: c.id,
        title: c.title,
        description: c.description,
        lessons: c.lessons.map((l: Lesson) => ({
          id: l.id,
          title: l.title,
          blocks: l.content?.length ?? 0,
          chars: approxLessonSize(l.content),
        })),
      })),
    })),
  };
}

export function CopilotTools() {
  const syllabi = useSyllabusStore((s) => s.syllabi);
  const activeSyllabusId = useSyllabusStore((s) => s.activeSyllabusId);
  const activeItemId = useSyllabusStore((s) => s.activeItemId);
  const createSyllabus = useSyllabusStore((s) => s.createSyllabus);
  const addChapter = useSyllabusStore((s) => s.addChapter);
  const addLesson = useSyllabusStore((s) => s.addLesson);
  const updateLessonContent = useSyllabusStore((s) => s.updateLessonContent);
  const appendLessonContent = useSyllabusStore((s) => s.appendLessonContent);
  const recordMutation = useSyllabusStore((s) => s.recordMutation);
  const removeChapter = useSyllabusStore((s) => s.removeChapter);
  const removeLesson = useSyllabusStore((s) => s.removeLesson);
  const setRenderError = useSyllabusStore((s) => s.setRenderError);

  useCopilotReadable({
    description:
      "Skeleton of all syllabi (ids, titles, chapter/lesson metadata, block counts). " +
      "This does NOT include lesson content. " +
      "Call the `read_lesson` tool with a lessonId to fetch a lesson's full BlockNote content on demand.",
    value: buildSkeleton(syllabi, activeSyllabusId, activeItemId),
  });

  useCopilotAction({
    name: "read_lesson",
    description:
      "Read the full BlockNote content of a single lesson by id. " +
      "ALSO use this after calling `add_lesson`, `update_lesson_content`, or `append_lesson_content` " +
      "to verify the content was persisted correctly.",
    parameters: [
      { name: "lessonId", type: "string", description: "Id of the lesson to read" },
      { name: "from", type: "number", description: "Optional start block index (inclusive, 0-based)", required: false },
      { name: "to", type: "number", description: "Optional end block index (exclusive)", required: false },
    ],
    handler: ({ lessonId, from, to }) => {
      const state = useSyllabusStore.getState();
      const found = state.getLessonById(lessonId as string);
      if (!found) return { ok: false, error: `Lesson ${lessonId} not found` };
      const blocks = found.content ?? [];
      const total = blocks.length;
      const a = typeof from === "number" ? Math.max(0, Math.min(from as number, total)) : 0;
      const b = typeof to === "number" ? Math.max(a, Math.min(to as number, total)) : total;
      return {
        ok: true,
        lessonId: found.id,
        title: found.title,
        totalBlocks: total,
        from: a,
        to: b,
        content: blocks.slice(a, b),
      };
    },
    render: ({ status, args }) => (<ToolCallCard title="read_lesson" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "create_syllabus",
    description: "Create a new syllabus with a unique id, title, subject and optional description",
    parameters: [
      { name: "id", type: "string", description: "Unique syllabus id" },
      { name: "title", type: "string", description: "Syllabus title" },
      { name: "subject", type: "string", description: "Subject area" },
      { name: "description", type: "string", description: "Optional description", required: false },
    ],
    handler: ({ id, title, subject, description }) => {
      createSyllabus(id as string, title as string, subject as string, description as string | undefined);
      return { ok: true, id };
    },
    render: ({ status, args }) => (<ToolCallCard title="create_syllabus" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "add_chapter",
    description: "Add a chapter to an existing syllabus",
    parameters: [
      { name: "syllabusId", type: "string", description: "Parent syllabus id" },
      { name: "chapterId", type: "string", description: "Unique chapter id" },
      { name: "title", type: "string", description: "Chapter title" },
      { name: "description", type: "string", description: "Optional description", required: false },
    ],
    handler: ({ syllabusId, chapterId, title, description }) => {
      addChapter(syllabusId as string, chapterId as string, title as string, description as string | undefined);
      return { ok: true, chapterId };
    },
    render: ({ status, args }) => (<ToolCallCard title="add_chapter" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "add_lesson",
    description:
      "Add a lesson to a chapter with optional BlockNote content. " +
      "Content is validated with BlockNote before it is saved. " +
      "On validation failure the lesson is NOT created and the handler returns { ok: false, error }.",
    parameters: [
      { name: "chapterId", type: "string", description: "Parent chapter id" },
      { name: "lessonId", type: "string", description: "Unique lesson id" },
      { name: "title", type: "string", description: "Lesson title" },
      { name: "content", type: "object[]", description: "Initial BlockNote content blocks", required: false },
    ],
    handler: ({ chapterId, lessonId, title, content }) => {
      const blocks = (content ?? []) as Block[];
      const v = validateBlockNoteContent(blocks);
      if (!v.ok) { const err = v.error ?? "invalid";
        recordMutation(lessonId as string, { op: "replace", previous: [], next: blocks, at: new Date().toISOString(), error: err });
        setRenderError(lessonId as string, err);
        return { ok: false, error: err, hint: "Fix the BlockNote JSON and call add_lesson again." };
      }
      addLesson(chapterId as string, lessonId as string, title as string, blocks as unknown as never);
      recordMutation(lessonId as string, { op: "replace", previous: [], next: blocks, at: new Date().toISOString() });
      return { ok: true, lessonId, blocks: blocks.length };
    },
    render: ({ status, args }) => {
      const raw = args as Record<string, unknown> | undefined;
      const lessonId = raw?.lessonId as string | undefined;
      return <LessonDiffCard lessonId={lessonId} title="add_lesson" status={status} args={raw} />;
    },
  });

  useCopilotAction({
    name: "update_lesson_content",
    description:
      "REPLACE the full BlockNote content of an existing lesson. " +
      "Content is validated with BlockNote before it is saved. " +
      "On validation failure the lesson is NOT modified and the handler returns { ok: false, error }. " +
      "After a successful update, call `read_lesson` to verify the result.",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id to update" },
      { name: "content", type: "object[]", description: "New BlockNote content blocks (replaces existing)" },
    ],
    handler: ({ lessonId, content }) => {
      const id = lessonId as string;
      const next = (content ?? []) as Block[];
      const state = useSyllabusStore.getState();
      const prev = state.getLessonById(id)?.content ?? [];
      const v = validateBlockNoteContent(next);
      if (!v.ok) { const err = v.error ?? "invalid";
        recordMutation(id, { op: "replace", previous: prev, next, at: new Date().toISOString(), error: err });
        setRenderError(id, err);
        return { ok: false, error: err, hint: "Fix the BlockNote JSON and call update_lesson_content again." };
      }
      updateLessonContent(id, next as unknown as never);
      recordMutation(id, { op: "replace", previous: prev, next, at: new Date().toISOString() });
      setRenderError(id, null);
      return { ok: true, lessonId: id, blocks: next.length, previousBlocks: prev.length };
    },
    render: ({ status, args }) => {
      const raw = args as Record<string, unknown> | undefined;
      const lessonId = raw?.lessonId as string | undefined;
      return <LessonDiffCard lessonId={lessonId} title="update_lesson_content" status={status} args={raw} />;
    },
  });

  useCopilotAction({
    name: "append_lesson_content",
    description:
      "APPEND new BlockNote blocks to the END of an existing lesson (non-destructive). " +
      "Use this instead of update_lesson_content whenever you only want to add material. " +
      "Content is validated with BlockNote before it is saved; on failure the lesson is NOT modified. " +
      "After a successful append, call `read_lesson` to verify the result.",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id to append to" },
      { name: "blocks", type: "object[]", description: "BlockNote blocks to append at the end" },
    ],
    handler: ({ lessonId, blocks }) => {
      const id = lessonId as string;
      const toAppend = (blocks ?? []) as Block[];
      const state = useSyllabusStore.getState();
      const prev = state.getLessonById(id)?.content ?? [];
      const next = [...prev, ...toAppend];
      const v = validateBlockNoteContent(next);
      if (!v.ok) { const err = v.error ?? "invalid";
        recordMutation(id, { op: "append", previous: prev, next, at: new Date().toISOString(), error: err });
        setRenderError(id, err);
        return { ok: false, error: err, hint: "Fix the BlockNote JSON of the new blocks and call append_lesson_content again." };
      }
      appendLessonContent(id, toAppend as unknown as never);
      recordMutation(id, { op: "append", previous: prev, next, at: new Date().toISOString() });
      setRenderError(id, null);
      return { ok: true, lessonId: id, appended: toAppend.length, totalBlocks: next.length };
    },
    render: ({ status, args }) => {
      const raw = args as Record<string, unknown> | undefined;
      const lessonId = raw?.lessonId as string | undefined;
      const preview = raw ? { lessonId: raw.lessonId, appending: Array.isArray(raw.blocks) ? (raw.blocks as unknown[]).length : 0 } : undefined;
      const mutation = useSyllabusStore.getState().lastMutation[lessonId ?? ""];
      return (
        <ToolCallCard title="append_lesson_content" status={status} args={preview as Record<string, unknown> | undefined} error={mutation?.error ?? null}>
          {mutation && !mutation.error && <BlockDiff previous={mutation.previous} next={mutation.next} />}
        </ToolCallCard>
      );
    },
  });

  useCopilotAction({
    name: "remove_chapter",
    description: "Remove a chapter and all its lessons",
    parameters: [{ name: "chapterId", type: "string", description: "Chapter id to remove" }],
    handler: ({ chapterId }) => { removeChapter(chapterId as string); return { ok: true }; },
    render: ({ status, args }) => (<ToolCallCard title="remove_chapter" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "remove_lesson",
    description: "Remove a lesson by id",
    parameters: [{ name: "lessonId", type: "string", description: "Lesson id to remove" }],
    handler: ({ lessonId }) => { removeLesson(lessonId as string); return { ok: true }; },
    render: ({ status, args }) => (<ToolCallCard title="remove_lesson" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "report_render_error",
    description: "Store a render error for a lesson (pass null error to clear it)",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id" },
      { name: "error", type: "string", description: "Error message, or null to clear" },
    ],
    handler: ({ lessonId, error }) => { setRenderError(lessonId as string, (error as string | null) ?? null); return { ok: true }; },
    render: ({ status, args }) => (<ToolCallCard title="report_render_error" status={status} args={args as Record<string, unknown>} />),
  });

  return null;
}
