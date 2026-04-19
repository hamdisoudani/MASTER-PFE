"use client";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useSyllabusStore } from "@/store/syllabusStore";
import { FileTree } from "@/components/FileTree";
import { BlockNoteEditor, EmptyEditorState } from "@/components/BlockNoteEditor";
import { ChatPane } from "@/components/chat/ChatPane";
import { ThreadHistory } from "@/components/chat/ThreadHistory";

export default function SyllabusViewerClient() {
  const { getActiveLesson } = useSyllabusStore();
  const activeLesson = getActiveLesson();
  return (
    <PanelGroup direction="horizontal" className="h-screen w-screen">
      <Panel defaultSize={14} minSize={10}><ThreadHistory /></Panel>
      <PanelResizeHandle className="w-px bg-neutral-800" />
      <Panel defaultSize={16} minSize={10}><FileTree /></Panel>
      <PanelResizeHandle className="w-px bg-neutral-800" />
      <Panel defaultSize={44} minSize={25}>
        {activeLesson ? <BlockNoteEditor lessonId={activeLesson.id} initialContent={activeLesson.content} /> : <EmptyEditorState />}
      </Panel>
      <PanelResizeHandle className="w-px bg-neutral-800" />
      <Panel defaultSize={26} minSize={18}><ChatPane /></Panel>
    </PanelGroup>
  );
}
