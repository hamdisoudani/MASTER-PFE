'use client';

import { useEffect } from 'react';
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
