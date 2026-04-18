"use client";

import React from "react";
import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useSyllabusStore } from "@/store/syllabusStore";
import { CheckCircle2, Loader2, AlertTriangle } from "lucide-react";

function ToolCallCard({ title, status, args, error }: { title: string; status: "inProgress" | "executing" | "complete" | string; args?: Record<string, unknown>; error?: string | null; }) {
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
    </div>
  );
}

export function CopilotTools() {
  const { syllabi, createSyllabus, addChapter, addLesson, updateLessonContent, removeChapter, removeLesson, setRenderError, getActiveSyllabus } = useSyllabusStore();
  useCopilotReadable({ description: "All syllabi currently in the store, including their chapters and lessons", value: syllabi });
  useCopilotReadable({ description: "The currently active syllabus (chapters + lessons)", value: getActiveSyllabus() });

  useCopilotAction({
    name: "create_syllabus",
    description: "Create a new syllabus with a unique id, title, subject and optional description",
    parameters: [
      { name: "id", type: "string", description: "Unique syllabus id" },
      { name: "title", type: "string", description: "Syllabus title" },
      { name: "subject", type: "string", description: "Subject area" },
      { name: "description", type: "string", description: "Optional description", required: false },
    ],
    handler: ({ id, title, subject, description }) => { createSyllabus(id as string, title as string, subject as string, description as string | undefined); },
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
    handler: ({ syllabusId, chapterId, title, description }) => { addChapter(syllabusId as string, chapterId as string, title as string, description as string | undefined); },
    render: ({ status, args }) => (<ToolCallCard title="add_chapter" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "add_lesson",
    description: "Add a lesson to a chapter with optional BlockNote content",
    parameters: [
      { name: "chapterId", type: "string", description: "Parent chapter id" },
      { name: "lessonId", type: "string", description: "Unique lesson id" },
      { name: "title", type: "string", description: "Lesson title" },
      { name: "content", type: "object[]", description: "Initial BlockNote content blocks", required: false },
    ],
    handler: ({ chapterId, lessonId, title, content }) => { addLesson(chapterId as string, lessonId as string, title as string, (content ?? []) as unknown as never); },
    render: ({ status, args }) => {
      const raw = args as Record<string, unknown> | undefined;
      const preview = raw ? { chapterId: raw.chapterId, lessonId: raw.lessonId, title: raw.title, blocks: Array.isArray(raw.content) ? (raw.content as unknown[]).length : 0 } : undefined;
      return (<ToolCallCard title="add_lesson" status={status} args={preview as Record<string, unknown> | undefined} />);
    },
  });

  useCopilotAction({
    name: "update_lesson_content",
    description: "Replace the BlockNote content of an existing lesson",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id to update" },
      { name: "content", type: "object[]", description: "New BlockNote content blocks" },
    ],
    handler: ({ lessonId, content }) => { updateLessonContent(lessonId as string, (content ?? []) as unknown as never); },
    render: ({ status, args }) => {
      const raw = args as Record<string, unknown> | undefined;
      const preview = raw ? { lessonId: raw.lessonId, blocks: Array.isArray(raw.content) ? (raw.content as unknown[]).length : 0 } : undefined;
      return (<ToolCallCard title="update_lesson_content" status={status} args={preview as Record<string, unknown> | undefined} />);
    },
  });

  useCopilotAction({
    name: "remove_chapter",
    description: "Remove a chapter and all its lessons",
    parameters: [{ name: "chapterId", type: "string", description: "Chapter id to remove" }],
    handler: ({ chapterId }) => { removeChapter(chapterId as string); },
    render: ({ status, args }) => (<ToolCallCard title="remove_chapter" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "remove_lesson",
    description: "Remove a lesson by id",
    parameters: [{ name: "lessonId", type: "string", description: "Lesson id to remove" }],
    handler: ({ lessonId }) => { removeLesson(lessonId as string); },
    render: ({ status, args }) => (<ToolCallCard title="remove_lesson" status={status} args={args as Record<string, unknown>} />),
  });

  useCopilotAction({
    name: "report_render_error",
    description: "Store a render error for a lesson (pass null error to clear it)",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id" },
      { name: "error", type: "string", description: "Error message, or null to clear" },
    ],
    handler: ({ lessonId, error }) => { setRenderError(lessonId as string, (error as string | null) ?? null); },
    render: ({ status, args }) => (<ToolCallCard title="report_render_error" status={status} args={args as Record<string, unknown>} />),
  });

  return null;
}
