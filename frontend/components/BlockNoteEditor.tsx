'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { Block, useSyllabusStore } from '@/store/syllabusStore';

interface EBProps {
  lessonId: string;
  onError: (lessonId: string, error: string) => void;
  children: ReactNode;
}
interface EBState { hasError: boolean; error: Error | null; }

class BlockNoteErrorBoundary extends Component<EBProps, EBState> {
  constructor(props: EBProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: Error): EBState {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError(this.props.lessonId, error.message);
    console.error('BlockNote render error:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-4 text-[var(--destructive)]">
          <svg className="w-10 h-10 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <div className="text-center">
            <p className="text-sm font-semibold">Render Error</p>
            <p className="text-xs text-[var(--muted-foreground)] mt-1 max-w-xs px-4">
              {this.state.error?.message ?? 'Failed to render lesson content'}
            </p>
            <p className="text-xs text-[var(--muted-foreground)] opacity-40 mt-2">
              The AI will automatically detect and fix this.
            </p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const BlockNoteEditorCore = dynamic(
  () => import('./BlockNoteEditorCore'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full">
        <div className="flex gap-1.5 items-center">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] opacity-50 animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] opacity-50 animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] opacity-50 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    ),
  }
);

export interface BlockNoteEditorProps {
  lessonId: string;
  initialContent: Block[];
}

export function BlockNoteEditor({ lessonId, initialContent }: BlockNoteEditorProps) {
  const { setRenderError } = useSyllabusStore();
  return (
    <div className="h-full overflow-hidden">
      <BlockNoteErrorBoundary lessonId={lessonId} onError={setRenderError}>
        <BlockNoteEditorCore lessonId={lessonId} initialContent={initialContent} />
      </BlockNoteErrorBoundary>
    </div>
  );
}

export function EmptyEditorState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-[var(--muted-foreground)]">
      <svg className="w-20 h-20 opacity-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.75}
          d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
      </svg>
      <div className="text-center">
        <p className="text-sm font-medium opacity-50">No lesson open</p>
        <p className="text-xs opacity-25 mt-1">Select a lesson or ask the AI to build a course</p>
      </div>
    </div>
  );
}
