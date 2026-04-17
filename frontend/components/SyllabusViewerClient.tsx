"use client";

import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useSyllabusStore } from "@/store/syllabusStore";
import { FileTree } from "@/components/FileTree";
import { BlockNoteEditor, EmptyEditorState } from "@/components/BlockNoteEditor";
import { CopilotChat } from "@copilotkit/react-ui";

/**
 * 3-panel resizable layout:
 *
 *  ┌──────────────┬──────────────────────────────┬───────────────┐
 *  │  FileTree     │      BlockNote editor         │  CopilotChat │
 *  │  (left)      │      (center, biggest)       │  (right)     │
 *  │  min 12%     │      min 35%                 │  min 20%     │
 *  │  default 17% │      flex                    │  default 28% │
 *  └──────────────┴───────────────────────────────┴───────────────┘
 *
 * Using CopilotChat (from @copilotkit/react-ui) instead of the custom
 * headless Chat component so that:
 *  - All message types are rendered (TextMessage, ActionExecutionMessage,
 *    ResultMessage, and useCoAgentStateRender results from AgentActivityPanel)
 *  - Tool-call progress is shown inline in the message list
 *  - AG-UI streaming state renders (plan, search results, scrape) appear
 *    naturally in the conversation thread
 */
export interface PlanStep {
  description: string;
  type: "search" | "task";
  status: "done" | "searching" | "pending" | string;
  queries?: string[];
}

export default function SyllabusViewerClient() {
  const { getActiveLesson } = useSyllabusStore();
  const activeLesson = getActiveLesson();

  return (
    <div className="h-screen w-full overflow-hidden flex flex-col">
      <PanelGroup direction="horizontal" className="flex-1 min-h-0">

        {/* Left: file explorer */}
        <Panel
          id="file-tree"
          order={1}
          defaultSize={17}
          minSize={12}
          maxSize={28}
          className="bg-[var(--card)] border-r border-[var(--border)] flex flex-col overflow-hidden"
        >
          <FileTree />
        </Panel>

        <ResizeHandle />

        {/* Center: BlockNote editor */}
        <Panel
          id="editor"
          order={2}
          defaultSize={55}
          minSize={35}
          className="flex flex-col overflow-hidden bg-[#1a140e]"
        >
          {activeLesson ? (
            <BlockNoteEditor
              key={activeLesson.id}
              lessonId={activeLesson.id}
              initialContent={activeLesson.content}
            />
          ) : (
            <EmptyEditorState />
          )}
        </Panel>

        <ResizeHandle />

        {/* Right: CopilotChat — handles all message types natively */}
        <Panel
          id="chat"
          order={3}
          defaultSize={28}
          minSize={20}
          maxSize={45}
          className="flex flex-col overflow-hidden border-l border-[var(--border)]"
        >
          <CopilotChat
            className="h-full"
            labels={{
              title: "Syllabus AI",
              placeholder: "Describe the course you want to plan...",
              stopGenerating: "Stop",
              regenerateResponse: "Regenerate",
            }}
            instructions="You are a syllabus-building AI. Help the user design course outlines, chapters, and lessons. Use the available tools to create and update syllabi."
          />
        </Panel>

      </PanelGroup>
    </div>
  );
}

function ResizeHandle() {
  return (
    <PanelResizeHandle className="group relative w-1 flex items-center justify-center bg-transparent hover:bg-[var(--border)] data-[resize-handle-active]:bg-[var(--primary)] transition-colors duration-150 cursor-col-resize">
      <div className="absolute inset-y-0 -left-1.5 -right-1.5" />
      <div className="w-0.5 h-8 rounded-full bg-[var(--border)] group-hover:bg-[var(--primary)] group-data-[resize-handle-active]:bg-[var(--primary)] transition-colors" />
    </PanelResizeHandle>
  );
}
