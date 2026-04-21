'use client';

import { useEffect, useRef } from 'react';
import { useCreateBlockNote } from '@blocknote/react';
import { BlockNoteView } from '@blocknote/mantine';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';
import { Block, useSyllabusStore } from '@/store/syllabusStore';

interface Props {
  lessonId: string;
  initialContent: Block[];
}

export default function BlockNoteEditorCore({ lessonId, initialContent }: Props) {
  const { updateLessonContent, setRenderError } = useSyllabusStore();

  const safeContent =
    initialContent && initialContent.length > 0
      ? (initialContent as unknown as Parameters<typeof useCreateBlockNote>[0]['initialContent'])
      : undefined;

  const editor = useCreateBlockNote({ initialContent: safeContent });

  // Track last-applied content reference so we only replace when it actually changes.
  // This covers the case where the component is NOT remounted but the lesson blocks
  // arrive asynchronously via the store (e.g. first-time hydration for a lesson
  // whose meta was already present, so the outer `key` did not flip).
  const lastAppliedRef = useRef<Block[] | null>(null);
  useEffect(() => {
    if (!editor) return;
    if (!initialContent || initialContent.length === 0) return;
    if (lastAppliedRef.current === initialContent) return;
    try {
      const current = editor.document;
      editor.replaceBlocks(
        current,
        initialContent as unknown as Parameters<typeof editor.replaceBlocks>[1]
      );
      lastAppliedRef.current = initialContent;
    } catch (err) {
      console.error('BlockNote replaceBlocks failed:', err);
    }
  }, [editor, initialContent]);

  useEffect(() => {
    setRenderError(lessonId, null);
  }, [lessonId, setRenderError]);

  return (
    <div className="h-full overflow-y-auto">
      <BlockNoteView
        editor={editor}
        theme="dark"
        onChange={() => {
          try {
            updateLessonContent(lessonId, editor.document as unknown as Block[]);
          } catch (err) {
            console.error('BlockNote save error:', err);
          }
        }}
      />
    </div>
  );
}
