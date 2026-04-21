"use client";

import { useState } from "react";
import {
  useSyllabusStore,
  Syllabus,
  Chapter,
  Lesson,
} from "@/store/syllabusStore";
import { useChapterLessons } from "@/hooks/useChapterLessons";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  Trash2,
  X,
  Check,
} from "lucide-react";

export function FileTree() {
  const {
    syllabi,
    activeSyllabusId,
    activeItemId,
    setActiveSyllabus,
    setActiveItem,
    toggleChapter,
    removeSyllabus,
    removeChapter,
    removeLesson,
  } = useSyllabusStore();

  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  function handleDelete(
    e: React.MouseEvent,
    id: string,
    type: "syllabus" | "chapter" | "lesson"
  ) {
    e.stopPropagation();
    if (confirmDelete === id) {
      if (type === "syllabus") removeSyllabus(id);
      else if (type === "chapter") removeChapter(id);
      else removeLesson(id);
      setConfirmDelete(null);
    } else {
      setConfirmDelete(id);
    }
  }

  function cancelDelete(e: React.MouseEvent) {
    e.stopPropagation();
    setConfirmDelete(null);
  }

  if (syllabi.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        <BookOpen className="w-10 h-10 mb-3 text-[var(--muted)]" />
        <p className="text-sm text-[var(--muted)] font-medium">No syllabuses yet</p>
        <p className="text-xs text-[var(--muted)] mt-1 opacity-70">
          Ask the AI to create one
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--border)]">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">Explorer</p>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {syllabi.map((s) => (
          <SyllabusNode
            key={s.id}
            syllabus={s}
            isActive={s.id === activeSyllabusId}
            activeItemId={activeItemId}
            confirmDelete={confirmDelete}
            onSelect={() => setActiveSyllabus(s.id)}
            onSelectLesson={setActiveItem}
            onToggleChapter={toggleChapter}
            onDelete={handleDelete}
            onCancelDelete={cancelDelete}
          />
        ))}
      </div>
    </div>
  );
}

interface SyllabusNodeProps {
  syllabus: Syllabus;
  isActive: boolean;
  activeItemId: string | null;
  confirmDelete: string | null;
  onSelect: () => void;
  onSelectLesson: (id: string) => void;
  onToggleChapter: (id: string) => void;
  onDelete: (
    e: React.MouseEvent,
    id: string,
    type: "syllabus" | "chapter" | "lesson"
  ) => void;
  onCancelDelete: (e: React.MouseEvent) => void;
}

function SyllabusNode({
  syllabus,
  isActive,
  activeItemId,
  confirmDelete,
  onSelect,
  onSelectLesson,
  onToggleChapter,
  onDelete,
  onCancelDelete,
}: SyllabusNodeProps) {
  const [expanded, setExpanded] = useState(true);
  const isConfirming = confirmDelete === syllabus.id;

  return (
    <div>
      <div
        onClick={() => { onSelect(); setExpanded((x) => !x); }}
        className={`group flex items-center gap-1.5 px-2 py-1.5 cursor-pointer rounded-sm mx-1 text-sm select-none ${
          isActive
            ? "bg-[var(--primary)]/15 text-[var(--primary)]"
            : "hover:bg-[var(--muted)]/10 text-[var(--text)]"
        }`}
      >
        <span className="shrink-0 text-[var(--muted)]">
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </span>
        <BookOpen className="w-3.5 h-3.5 shrink-0" />
        <span className="truncate flex-1 font-medium text-xs">{syllabus.title}</span>

        {isConfirming ? (
          <span className="flex items-center gap-0.5 ml-auto" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={(e) => onDelete(e, syllabus.id, "syllabus")}
              className="p-0.5 rounded text-red-500 hover:bg-red-500/20"
              title="Confirm delete"
            >
              <Check className="w-3 h-3" />
            </button>
            <button
              onClick={onCancelDelete}
              className="p-0.5 rounded text-[var(--muted)] hover:bg-[var(--muted)]/20"
              title="Cancel"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ) : (
          <button
            onClick={(e) => onDelete(e, syllabus.id, "syllabus")}
            className="ml-auto opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--muted)] hover:text-red-500 hover:bg-red-500/20 transition-opacity"
            title="Delete syllabus"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        )}
      </div>

      {expanded && syllabus.chapters.map((ch) => (
        <ChapterNode
          key={ch.id}
          chapter={ch}
          activeItemId={activeItemId}
          confirmDelete={confirmDelete}
          onToggle={() => onToggleChapter(ch.id)}
          onSelectLesson={onSelectLesson}
          onDelete={onDelete}
          onCancelDelete={onCancelDelete}
        />
      ))}
    </div>
  );
}

interface ChapterNodeProps {
  chapter: Chapter;
  activeItemId: string | null;
  confirmDelete: string | null;
  onToggle: () => void;
  onSelectLesson: (id: string) => void;
  onDelete: (
    e: React.MouseEvent,
    id: string,
    type: "syllabus" | "chapter" | "lesson"
  ) => void;
  onCancelDelete: (e: React.MouseEvent) => void;
}

function ChapterNode({
  chapter,
  activeItemId,
  confirmDelete,
  onToggle,
  onSelectLesson,
  onDelete,
  onCancelDelete,
}: ChapterNodeProps) {
  const isConfirming = confirmDelete === chapter.id;
  useChapterLessons(chapter.id, chapter.isExpanded);
  return (
    <div>
      <div
        onClick={onToggle}
        className="group flex items-center gap-1.5 pl-5 pr-2 py-1 cursor-pointer rounded-sm mx-1 text-xs select-none hover:bg-[var(--muted)]/10 text-[var(--text)]"
      >
        <span className="shrink-0 text-[var(--muted)]">
          {chapter.isExpanded ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
        </span>
        {chapter.isExpanded ? (
          <FolderOpen className="w-3.5 h-3.5 shrink-0 text-yellow-500/80" />
        ) : (
          <Folder className="w-3.5 h-3.5 shrink-0 text-yellow-500/80" />
        )}
        <span className="truncate flex-1">{chapter.title}</span>

        {isConfirming ? (
          <span className="flex items-center gap-0.5 ml-auto" onClick={(e) => e.stopPropagation()}>
            <button onClick={(e) => onDelete(e, chapter.id, "chapter")} className="p-0.5 rounded text-red-500 hover:bg-red-500/20" title="Confirm">
              <Check className="w-3 h-3" />
            </button>
            <button onClick={onCancelDelete} className="p-0.5 rounded text-[var(--muted)] hover:bg-[var(--muted)]/20" title="Cancel">
              <X className="w-3 h-3" />
            </button>
          </span>
        ) : (
          <button
            onClick={(e) => onDelete(e, chapter.id, "chapter")}
            className="ml-auto opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--muted)] hover:text-red-500 hover:bg-red-500/20 transition-opacity"
            title="Delete chapter"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        )}
      </div>

      {chapter.isExpanded &&
        chapter.lessons.map((lesson) => (
          <LessonNode
            key={lesson.id}
            lesson={lesson}
            isActive={lesson.id === activeItemId}
            confirmDelete={confirmDelete}
            onSelect={() => onSelectLesson(lesson.id)}
            onDelete={onDelete}
            onCancelDelete={onCancelDelete}
          />
        ))}
    </div>
  );
}

interface LessonNodeProps {
  lesson: Lesson;
  isActive: boolean;
  confirmDelete: string | null;
  onSelect: () => void;
  onDelete: (
    e: React.MouseEvent,
    id: string,
    type: "syllabus" | "chapter" | "lesson"
  ) => void;
  onCancelDelete: (e: React.MouseEvent) => void;
}

function LessonNode({ lesson, isActive, confirmDelete, onSelect, onDelete, onCancelDelete }: LessonNodeProps) {
  const isConfirming = confirmDelete === lesson.id;
  return (
    <div
      onClick={onSelect}
      className={`group flex items-center gap-1.5 pl-9 pr-2 py-1 cursor-pointer rounded-sm mx-1 text-xs select-none ${
        isActive
          ? "bg-[var(--primary)]/15 text-[var(--primary)]"
          : "hover:bg-[var(--muted)]/10 text-[var(--muted)]"
      }`}
    >
      <FileText className="w-3 h-3 shrink-0" />
      <span className="truncate flex-1">{lesson.title}</span>
      <span
        className={`ml-1 mr-1 shrink-0 rounded px-1.5 py-0 text-[10px] tabular-nums leading-4 ${
          (lesson.content?.length ?? 0) === 0
            ? "bg-[var(--muted)]/10 text-[var(--muted)] opacity-60"
            : "bg-[var(--primary)]/10 text-[var(--primary)]"
        }`}
        title={`${lesson.content?.length ?? 0} blocks`}
      >
        {lesson.content?.length ?? 0}
      </span>

      {isConfirming ? (
        <span className="flex items-center gap-0.5 ml-auto" onClick={(e) => e.stopPropagation()}>
          <button onClick={(e) => onDelete(e, lesson.id, "lesson")} className="p-0.5 rounded text-red-500 hover:bg-red-500/20" title="Confirm">
            <Check className="w-3 h-3" />
          </button>
          <button onClick={onCancelDelete} className="p-0.5 rounded text-[var(--muted)] hover:bg-[var(--muted)]/20" title="Cancel">
            <X className="w-3 h-3" />
          </button>
        </span>
      ) : (
        <button
          onClick={(e) => onDelete(e, lesson.id, "lesson")}
          className="ml-auto opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--muted)] hover:text-red-500 hover:bg-red-500/20 transition-opacity"
          title="Delete lesson"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
