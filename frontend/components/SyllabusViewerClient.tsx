"use client";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useSyllabusStore } from "@/store/syllabusStore";
import { FileTree } from "@/components/FileTree";
import { BlockNoteEditor, EmptyEditorState } from "@/components/BlockNoteEditor";
import { ChatPane } from "@/components/chat/ChatPane";

export default function SyllabusViewerClient() {
  const { getActiveLesson } = useSyllabusStore();
  const activeLesson = getActiveLesson();
  return (
    <PanelGroup direction="horizontal" className="h-screen w-screen">
      <Panel defaultSize={18} minSize={12}><FileTree /></Panel>
      <PanelResizeHandle className="w-px bg-neutral-800" />
      <Panel defaultSize={52} minSize={30}>
        {activeLesson ? <BlockNoteEditor lesson={activeLesson} /> : <EmptyEditorState />}
      </Panel>
      <PanelResizeHandle className="w-px bg-neutral-800" />
      <Panel defaultSize={30} minSize={20}><ChatPane /></Panel>
    </PanelGroup>
  );
}
