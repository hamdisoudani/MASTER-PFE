"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useSyllabusStore } from "@/store/syllabusStore";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";

export function CopilotTools() {
  const {
    syllabi,
    createSyllabus,
    addChapter,
    addLesson,
    updateLessonContent,
    removeChapter,
    removeLesson,
    setRenderError,
    getActiveSyllabus,
  } = useSyllabusStore();

  useCopilotReadable({
    description: "All syllabi currently in the store, including their chapters and lessons",
    value: syllabi,
  });

  useCopilotReadable({
    description: "The currently active syllabus (chapters + lessons)",
    value: getActiveSyllabus(),
  });

  useCopilotAction({
    name: "create_syllabus",
    description: "Create a new syllabus with a unique id, title, subject and optional description",
    parameters: [
      { name: "id",          type: "string", description: "Unique syllabus id" },
      { name: "title",       type: "string", description: "Syllabus title" },
      { name: "subject",     type: "string", description: "Subject area" },
      { name: "description", type: "string", description: "Optional description", required: false },
    ],
    handler: ({ id, title, subject, description }) => {
      createSyllabus(
        id as string,
        title as string,
        subject as string,
        description as string | undefined,
      );
    },
  });

  useCopilotAction({
    name: "add_chapter",
    description: "Add a chapter to an existing syllabus",
    parameters: [
      { name: "syllabusId",  type: "string", description: "Parent syllabus id" },
      { name: "chapterId",   type: "string", description: "Unique chapter id" },
      { name: "title",       type: "string", description: "Chapter title" },
      { name: "description", type: "string", description: "Optional description", required: false },
    ],
    handler: ({ syllabusId, chapterId, title, description }) => {
      addChapter(
        syllabusId as string,
        chapterId as string,
        title as string,
        description as string | undefined,
      );
    },
  });

  useCopilotAction({
    name: "add_lesson",
    description: "Add a lesson to a chapter with optional BlockNote content",
    parameters: [
      { name: "chapterId", type: "string",   description: "Parent chapter id" },
      { name: "lessonId",  type: "string",   description: "Unique lesson id" },
      { name: "title",     type: "string",   description: "Lesson title" },
      { name: "content",   type: "object[]", description: "Initial BlockNote content blocks", required: false },
    ],
    handler: ({ chapterId, lessonId, title, content }) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      addLesson(chapterId as string, lessonId as string, title as string, (content ?? []) as any);
    },
  });

  useCopilotAction({
    name: "update_lesson_content",
    description: "Replace the BlockNote content of an existing lesson",
    parameters: [
      { name: "lessonId", type: "string",   description: "Lesson id to update" },
      { name: "content",  type: "object[]", description: "New BlockNote content blocks" },
    ],
    handler: ({ lessonId, content }) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      updateLessonContent(lessonId as string, (content ?? []) as any);
    },
  });

  useCopilotAction({
    name: "remove_chapter",
    description: "Remove a chapter and all its lessons",
    parameters: [
      { name: "chapterId", type: "string", description: "Chapter id to remove" },
    ],
    handler: ({ chapterId }) => {
      removeChapter(chapterId as string);
    },
  });

  useCopilotAction({
    name: "remove_lesson",
    description: "Remove a lesson by id",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id to remove" },
    ],
    handler: ({ lessonId }) => {
      removeLesson(lessonId as string);
    },
  });

  useCopilotAction({
    name: "report_render_error",
    description: "Store a render error for a lesson (pass null error to clear it)",
    parameters: [
      { name: "lessonId", type: "string", description: "Lesson id" },
      { name: "error",    type: "string", description: "Error message, or null to clear" },
    ],
    handler: ({ lessonId, error }) => {
      setRenderError(lessonId as string, (error as string | null) ?? null);
    },
  });

  // AgentActivityPanel is self-contained: it uses useCoAgentStateRender
  // internally and renders inside CopilotKit's overlay (returns null from DOM).
  return <AgentActivityPanel />;
}
