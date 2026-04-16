"use client";

import { useSyllabusStore } from "@/store/syllabusStore";
import { FileTree } from "@/components/FileTree";
import { BlockNoteEditor, EmptyEditorState } from "@/components/BlockNoteEditor";

export default function SyllabusViewerClient() {
  const { getActiveLesson } = useSyllabusStore();
  const activeLesson = getActiveLesson();

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ paddingRight: "400px" }}>
      {/* Left: VS Code-style file explorer */}
      <aside className="w-64 flex-shrink-0 border-r border-[var(--border)] bg-[var(--card)] flex flex-col overflow-hidden">
        <FileTree />
      </aside>

      {/* Center: BlockNote rich-text editor */}
      <main className="flex-1 overflow-hidden bg-[#1a140e]">
        {activeLesson ? (
          <BlockNoteEditor
            key={activeLesson.id}
            lessonId={activeLesson.id}
            initialContent={activeLesson.content}
          />
        ) : (
          <EmptyEditorState />
        )}
      </main>
    </div>
  );
}
