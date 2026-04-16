"use client";

import { useCopilotAction } from "@copilotkit/react-core";
import { useAgentContext } from "@copilotkit/react-core/v2";
import { useSyllabusStore, Block } from "@/store/syllabusStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";

// ─── Status indicator ─────────────────────────────────────────────────────────
function StatusDot({ status }: { status: string }) {
  if (status === "complete") return <span className="text-green-400 text-xs">✓</span>;
  return (
    <span className="inline-block h-2 w-2 rounded-full bg-primary animate-pulse" />
  );
}

// ─── Shared tool card wrapper ─────────────────────────────────────────────────
function ToolCard({
  icon,
  title,
  status,
  children,
}: {
  icon: string;
  title: string;
  status: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="my-1 text-sm">
      <CardHeader className="py-2 px-3">
        <CardTitle className="flex items-center justify-between text-xs">
          <span className="flex items-center gap-1.5">
            <span>{icon}</span>
            {title}
          </span>
          <StatusDot status={status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="px-3 pb-2 pt-0">{children}</CardContent>
    </Card>
  );
}

// ─── Individual tool renderers ────────────────────────────────────────────────

function CreateSyllabusRender({ status, args }: { status: string; args: Record<string, string> }) {
  return (
    <ToolCard icon="📚" title="Create Syllabus" status={status}>
      <p className="font-medium text-foreground">{args.title || "…"}</p>
      {args.subject && (
        <Badge variant="secondary" className="mt-1">{args.subject}</Badge>
      )}
      {args.description && (
        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{args.description}</p>
      )}
    </ToolCard>
  );
}

function AddChapterRender({ status, args }: { status: string; args: Record<string, string> }) {
  return (
    <ToolCard icon="📖" title="Add Chapter" status={status}>
      <p className="font-medium text-foreground">{args.title || "…"}</p>
      <p className="text-xs text-muted-foreground mt-0.5">
        in <code className="bg-muted rounded px-1">{args.syllabusId}</code>
      </p>
      {args.description && (
        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{args.description}</p>
      )}
    </ToolCard>
  );
}

function AddLessonRender({
  status,
  args,
}: {
  status: string;
  args: Record<string, unknown>;
}) {
  const blockCount = Array.isArray(args.content) ? (args.content as unknown[]).length : 0;
  return (
    <ToolCard icon="📝" title="Add Lesson" status={status}>
      <p className="font-medium text-foreground">{String(args.title || "…")}</p>
      <p className="text-xs text-muted-foreground mt-0.5">
        in <code className="bg-muted rounded px-1">{String(args.chapterId || "")}</code>
      </p>
      {blockCount > 0 && (
        <Badge variant="muted" className="mt-1">
          {blockCount} blocks
        </Badge>
      )}
    </ToolCard>
  );
}

function UpdateLessonRender({
  status,
  args,
}: {
  status: string;
  args: Record<string, unknown>;
}) {
  const blockCount = Array.isArray(args.content) ? (args.content as unknown[]).length : 0;
  return (
    <ToolCard icon="✏️" title="Update Lesson" status={status}>
      <p className="text-xs text-muted-foreground">
        lesson <code className="bg-muted rounded px-1">{String(args.lessonId || "")}</code>
      </p>
      {blockCount > 0 && (
        <Badge variant="muted" className="mt-1">
          {blockCount} blocks
        </Badge>
      )}
    </ToolCard>
  );
}

function RemoveRender({
  status,
  args,
  kind,
}: {
  status: string;
  args: Record<string, string>;
  kind: "chapter" | "lesson";
}) {
  const id = kind === "chapter" ? args.chapterId : args.lessonId;
  return (
    <ToolCard icon="🗑️" title={`Remove ${kind}`} status={status}>
      <p className="text-xs text-muted-foreground">
        <code className="bg-muted rounded px-1">{id || "…"}</code>
      </p>
    </ToolCard>
  );
}

function ErrorRender({ status, args }: { status: string; args: Record<string, string> }) {
  return (
    <ToolCard icon="⚠️" title="Render Error" status={status}>
      <p className="text-xs text-destructive-foreground bg-destructive/20 rounded p-1.5 mt-0.5">
        {args.error || "Unknown error"}
      </p>
    </ToolCard>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────────

export function CopilotTools() {
  const {
    syllabi,
    renderErrors,
    createSyllabus,
    addChapter,
    addLesson,
    updateLessonContent,
    removeChapter,
    removeLesson,
    setRenderError,
  } = useSyllabusStore();

  // ── Inject current editor state as agent context ─────────────────────────────
  //
  // useAgentContext (from @copilotkit/react-core/v2) serializes `value` with
  // JSON.stringify and stores { description, value: "<json-string>" } into
  // state["copilotkit"]["context"] on the agent side.
  //
  // The agent reads state["copilotkit"]["context"] in _build_system_prompt()
  // inside nodes.py and manually injects this data into the LLM system prompt.
  // CopilotKit does NOT do the injection automatically — we own that step.
  //
  // The agent uses this to:
  //   • avoid recreating existing syllabuses/chapters/lessons
  //   • use correct IDs when the user refers to existing content
  //   • proactively fix any render errors
  useAgentContext({
    description:
      "Courses currently open in the editor. Each entry lists the syllabus id, " +
      "title, subject, and its chapters with their lessons. " +
      "Do NOT create a syllabus or chapter whose id already appears here.",
    value: syllabi.map((s) => ({
      id: s.id,
      title: s.title,
      subject: s.subject,
      chapters: s.chapters.map((ch) => ({
        id: ch.id,
        title: ch.title,
        lessons: ch.lessons.map((l) => ({ id: l.id, title: l.title })),
      })),
    })),
  });

  useAgentContext({
    description:
      "Lessons that currently have BlockNote render errors. " +
      "Call update_lesson_content for each listed lessonId to fix them.",
    value: Object.entries(renderErrors)
      .filter(([, err]) => err !== null)
      .map(([lessonId, error]) => ({ lessonId, error })),
  });

  // ── Frontend tools (dispatched by CopilotKit / AG-UI) ──────────────────────

  useCopilotAction({
    name: "create_syllabus",
    description: "Create a new course/syllabus. Call this first before adding chapters or lessons.",
    parameters: [
      { name: "id", type: "string", description: 'URL-friendly unique slug, e.g. "python-beginners"', required: true },
      { name: "title", type: "string", description: "Display title of the course", required: true },
      { name: "subject", type: "string", description: "Subject area", required: true },
      { name: "description", type: "string", description: "Short course description", required: false },
    ],
    render: ({ status, args }) => (
      <CreateSyllabusRender status={status} args={args as Record<string, string>} />
    ),
    handler: ({ id, title, subject, description }) => {
      createSyllabus(id, title, subject, description);
      return `Created course: "${title}" (${subject})`;
    },
  });

  useCopilotAction({
    name: "add_chapter",
    description: "Add a chapter/module to an existing syllabus.",
    parameters: [
      { name: "syllabusId", type: "string", required: true },
      { name: "chapterId", type: "string", required: true },
      { name: "title", type: "string", required: true },
      { name: "description", type: "string", required: false },
    ],
    render: ({ status, args }) => (
      <AddChapterRender status={status} args={args as Record<string, string>} />
    ),
    handler: ({ syllabusId, chapterId, title, description }) => {
      addChapter(syllabusId, chapterId, title, description);
      return `Added chapter: "${title}"`;
    },
  });

  useCopilotAction({
    name: "add_lesson",
    description: "Add a lesson with BlockNote JSON content to a chapter.",
    parameters: [
      { name: "chapterId", type: "string", required: true },
      { name: "lessonId", type: "string", required: true },
      { name: "title", type: "string", required: true },
      {
        name: "content",
        type: "object[]",
        description: "BlockNote JSON blocks array.",
        required: true,
      },
    ],
    render: ({ status, args }) => (
      <AddLessonRender status={status} args={args as Record<string, unknown>} />
    ),
    handler: ({ chapterId, lessonId, title, content }) => {
      addLesson(chapterId, lessonId, title, content as Block[]);
      return `Added lesson: "${title}"`;
    },
  });

  useCopilotAction({
    name: "update_lesson_content",
    description: "Update or fix the BlockNote JSON content of an existing lesson.",
    parameters: [
      { name: "lessonId", type: "string", required: true },
      { name: "content", type: "object[]", required: true },
    ],
    render: ({ status, args }) => (
      <UpdateLessonRender status={status} args={args as Record<string, unknown>} />
    ),
    handler: ({ lessonId, content }) => {
      updateLessonContent(lessonId, content as Block[]);
      setRenderError(lessonId, null);
      return `Updated lesson: ${lessonId}`;
    },
  });

  useCopilotAction({
    name: "remove_chapter",
    description: "Remove a chapter and all its lessons.",
    parameters: [{ name: "chapterId", type: "string", required: true }],
    render: ({ status, args }) => (
      <RemoveRender status={status} args={args as Record<string, string>} kind="chapter" />
    ),
    handler: ({ chapterId }) => {
      removeChapter(chapterId);
      return `Removed chapter: ${chapterId}`;
    },
  });

  useCopilotAction({
    name: "remove_lesson",
    description: "Remove a single lesson from its chapter.",
    parameters: [{ name: "lessonId", type: "string", required: true }],
    render: ({ status, args }) => (
      <RemoveRender status={status} args={args as Record<string, string>} kind="lesson" />
    ),
    handler: ({ lessonId }) => {
      removeLesson(lessonId);
      return `Removed lesson: ${lessonId}`;
    },
  });

  useCopilotAction({
    name: "report_render_error",
    description: "Report a render error for a lesson so the agent can fix it.",
    parameters: [
      { name: "lessonId", type: "string", required: true },
      { name: "error", type: "string", required: true },
    ],
    render: ({ status, args }) => (
      <ErrorRender status={status} args={args as Record<string, string>} />
    ),
    handler: ({ lessonId, error }) => {
      setRenderError(lessonId, error);
      return `Recorded error for lesson ${lessonId}: ${error}`;
    },
  });

  // Renders agent state (plan, search, scrape) inside the CopilotSidebar
  return <AgentActivityPanel />;
}
