'use client';

import { useCopilotAction } from '@copilotkit/react-core';
import { useSyllabusStore, Block } from '@/store/syllabusStore';

export function CopilotTools() {
  const {
    createSyllabus,
    addChapter,
    addLesson,
    updateLessonContent,
    removeChapter,
    removeLesson,
    setRenderError,
    syllabi,
    renderErrors,
  } = useSyllabusStore();

  useCopilotAction({
    name: 'create_syllabus',
    description: 'Create a new course/syllabus. Call this first before adding chapters or lessons.',
    parameters: [
      { name: 'id', type: 'string', description: 'URL-friendly unique slug, e.g. "python-beginners"', required: true },
      { name: 'title', type: 'string', description: 'Display title of the course', required: true },
      { name: 'subject', type: 'string', description: 'Subject area, e.g. "Python", "Mathematics"', required: true },
      { name: 'description', type: 'string', description: 'Short course description', required: false },
    ],
    handler: ({ id, title, subject, description }) => {
      createSyllabus(id, title, subject, description);
      return `Created course: "${title}" (${subject})`;
    },
  });

  useCopilotAction({
    name: 'add_chapter',
    description: 'Add a chapter/module to an existing syllabus.',
    parameters: [
      { name: 'syllabusId', type: 'string', description: 'ID of the target syllabus', required: true },
      { name: 'chapterId', type: 'string', description: 'Unique chapter slug, e.g. "ch1-introduction"', required: true },
      { name: 'title', type: 'string', description: 'Chapter display title', required: true },
      { name: 'description', type: 'string', description: 'Chapter description', required: false },
    ],
    handler: ({ syllabusId, chapterId, title, description }) => {
      addChapter(syllabusId, chapterId, title, description);
      return `Added chapter: "${title}"`;
    },
  });

  useCopilotAction({
    name: 'add_lesson',
    description: 'Add a lesson with BlockNote JSON content to a chapter.',
    parameters: [
      { name: 'chapterId', type: 'string', description: 'ID of the parent chapter', required: true },
      { name: 'lessonId', type: 'string', description: 'Unique lesson slug, e.g. "l1-1-what-is-python"', required: true },
      { name: 'title', type: 'string', description: 'Lesson display title', required: true },
      {
        name: 'content',
        type: 'object[]',
        description: 'BlockNote JSON blocks array. Each block: { id, type, props: { textColor, backgroundColor, textAlignment, ...typeProps }, content: [{ type: "text", text: "", styles: {} }], children: [] }',
        required: true,
      },
    ],
    handler: ({ chapterId, lessonId, title, content }) => {
      addLesson(chapterId, lessonId, title, content as Block[]);
      return `Added lesson: "${title}"`;
    },
  });

  useCopilotAction({
    name: 'update_lesson_content',
    description: 'Update or fix the BlockNote JSON content of an existing lesson (e.g. to fix render errors).',
    parameters: [
      { name: 'lessonId', type: 'string', description: 'ID of the lesson to update', required: true },
      {
        name: 'content',
        type: 'object[]',
        description: 'New BlockNote JSON blocks array',
        required: true,
      },
    ],
    handler: ({ lessonId, content }) => {
      updateLessonContent(lessonId, content as Block[]);
      setRenderError(lessonId, null);
      return `Updated lesson content for: ${lessonId}`;
    },
  });

  useCopilotAction({
    name: 'remove_chapter',
    description: 'Remove a chapter and all its lessons from the syllabus.',
    parameters: [
      { name: 'chapterId', type: 'string', description: 'ID of the chapter to remove', required: true },
    ],
    handler: ({ chapterId }) => {
      removeChapter(chapterId);
      return `Removed chapter: ${chapterId}`;
    },
  });

  useCopilotAction({
    name: 'remove_lesson',
    description: 'Remove a single lesson from its chapter.',
    parameters: [
      { name: 'lessonId', type: 'string', description: 'ID of the lesson to remove', required: true },
    ],
    handler: ({ lessonId }) => {
      removeLesson(lessonId);
      return `Removed lesson: ${lessonId}`;
    },
  });

  useCopilotAction({
    name: 'report_render_error',
    description: 'Report a render error for a lesson so the agent can fix it automatically.',
    parameters: [
      { name: 'lessonId', type: 'string', description: 'ID of the lesson with the error', required: true },
      { name: 'error', type: 'string', description: 'Error message', required: true },
    ],
    handler: ({ lessonId, error }) => {
      setRenderError(lessonId, error);
      return `Recorded error for lesson ${lessonId}: ${error}`;
    },
  });

  return null;
}
