"use client";

import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useSyllabusStore } from "@/store/syllabusStore";
import { FileTree } from "@/components/FileTree";
import { BlockNoteEditor, EmptyEditorState } from "@/components/BlockNoteEditor";
import { CopilotChat } from "@copilotkit/react-ui";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";

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

        {/*
          Right: CopilotChat with the AgentActivityPanel floating above
          the prompt input. The Panel is position:relative so the panel's
          absolute positioning docks it to the bottom of the chat column.
        */}
        <Panel
          id="chat"
          order={3}
          defaultSize={28}
          minSize={20}
          maxSize={45}
          className="relative flex flex-col overflow-hidden border-l border-[var(--border)]"
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
          <AgentActivityPanel />
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
