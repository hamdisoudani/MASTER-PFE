"use client";

import React from "react";
import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useSyllabusStore } from "@/store/syllabusStore";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";
import { CheckCircle2, Loader2, AlertTriangle } from "lucide-react";

function ToolCallCard({ title, status, args, error }: { title: string; status: "inProgress" | "executing" | "complete" | string; args?: Record<string, unknown>; error?: string | null; }) {
  const isRunning = status === "inProgress" || status === "executing";
  const isDone = status === "complete";
  return (
    <div className="my-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs">
      <div className="flex items-center gap-2">
        {error ? (<AlertTriangle className="w-3.5 h-3.5 text-red-400" />) : isDone ? (<CheckCircle2 className="w-3.5 h-3.5 text-green-400" />) : (<Loader2 className={["w-3.5 h-3.5 text-indigo-300", isRunning ? "animate-spin" : ""].join(" ")} />)}
        <span className="font-mono text-[11px] text-white/85">{title}</span>
        <span className={["ml-auto text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wider", error ? "bg-red-500/15 text-red-300" : isDone ? "bg-green-500/15 text-green-300" : "bg-indigo-500/15 text-indigo-300"].join(" ")}>{error ? "error" : isDone ? "done" : "running"}</span>
      </div>
      {args && Object.keys(args).length > 0 && (<pre className="mt-1 text-[10px] leading-snug text-white/55 whitespace-pre-wrap break-words max-h-32 overflow-auto">{JSON.stringify(args, null, 2)}</pre>)}
      {error && (<p className="mt-1 text-[10px] text-red-300/80">{error}</p>)}
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

  return <AgentActivityPanel />;
}
