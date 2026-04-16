'use client';

import { useSyllabusStore } from '@/store/syllabusStore';

const ChevronIcon = ({ expanded }: { expanded: boolean }) => (
  <svg
    className={`w-3 h-3 transition-transform duration-150 flex-shrink-0 ${expanded ? 'rotate-90' : ''}`}
    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
  </svg>
);

const FolderIcon = ({ open }: { open?: boolean }) => (
  <svg className="w-4 h-4 flex-shrink-0 text-[var(--secondary)]" fill="currentColor" viewBox="0 0 20 20">
    {open ? (
      <path fillRule="evenodd" d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v1H2V6zM2 9v7a2 2 0 002 2h12a2 2 0 002-2V9H2z" clipRule="evenodd" />
    ) : (
      <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
    )}
  </svg>
);

const FileIcon = () => (
  <svg className="w-3.5 h-3.5 flex-shrink-0 text-[var(--muted-foreground)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const BookIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0 text-[var(--primary)]" fill="currentColor" viewBox="0 0 20 20">
    <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
  </svg>
);

const DeleteBtn = ({ onClick }: { onClick: (e: React.MouseEvent) => void }) => (
  <button
    onClick={onClick}
    className="opacity-0 group-hover:opacity-100 flex-shrink-0 p-0.5 rounded text-[var(--destructive)] hover:bg-[var(--destructive)]/10 transition-opacity"
    title="Delete"
  >
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  </button>
);

export function FileTree() {
  const {
    syllabi,
    activeSyllabusId,
    activeItemId,
    renderErrors,
    setActiveSyllabus,
    toggleChapter,
    setActiveItem,
    removeChapter,
    removeLesson,
  } = useSyllabusStore();

  if (syllabi.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center gap-3">
        <svg className="w-10 h-10 text-[var(--muted-foreground)] opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
            d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
        <div>
          <p className="text-xs font-medium text-[var(--muted-foreground)]">No courses yet</p>
          <p className="text-xs text-[var(--muted-foreground)] opacity-40 mt-1">Ask the AI to create a course</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-xs font-semibold uppercase tracking-widest text-[var(--muted-foreground)] opacity-50 border-b border-[var(--border)] flex-shrink-0">
        Explorer
      </div>
      <div className="flex-1 overflow-y-auto py-1 select-none">
        {syllabi.map((syllabus) => (
          <div key={syllabus.id}>
            <button
              onClick={() => setActiveSyllabus(syllabus.id)}
              className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs font-semibold hover:bg-[var(--accent)] transition-colors group ${
                activeSyllabusId === syllabus.id ? 'text-[var(--secondary)]' : 'text-[var(--foreground)]'
              }`}
            >
              <BookIcon />
              <span className="truncate flex-1 text-left">{syllabus.title}</span>
              <span className="text-[10px] text-[var(--muted-foreground)] opacity-40 bg-[var(--muted)] px-1.5 py-0.5 rounded-full flex-shrink-0">
                {syllabus.subject}
              </span>
            </button>

            {syllabus.chapters.map((chapter) => (
              <div key={chapter.id}>
                <div
                  className="flex items-center gap-1.5 pl-5 pr-3 py-1 text-xs cursor-pointer hover:bg-[var(--accent)] transition-colors group"
                  onClick={() => toggleChapter(chapter.id)}
                >
                  <ChevronIcon expanded={chapter.isExpanded} />
                  <FolderIcon open={chapter.isExpanded} />
                  <span className="truncate flex-1 text-[var(--foreground)] font-medium">{chapter.title}</span>
                  <span className="text-[10px] text-[var(--muted-foreground)] opacity-30 mr-1">{chapter.lessons.length}</span>
                  <DeleteBtn onClick={(e) => { e.stopPropagation(); removeChapter(chapter.id); }} />
                </div>

                {chapter.isExpanded && chapter.lessons.map((lesson) => (
                  <div
                    key={lesson.id}
                    onClick={() => setActiveItem(lesson.id)}
                    className={`flex items-center gap-2 pl-10 pr-3 py-1 text-xs cursor-pointer hover:bg-[var(--accent)] transition-colors group ${
                      activeItemId === lesson.id
                        ? 'bg-[var(--accent)] text-[var(--primary)]'
                        : 'text-[var(--muted-foreground)]'
                    }`}
                  >
                    <FileIcon />
                    <span className="truncate flex-1">{lesson.title}</span>
                    {renderErrors[lesson.id] && (
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--destructive)] flex-shrink-0" title="Render error" />
                    )}
                    <DeleteBtn onClick={(e) => { e.stopPropagation(); removeLesson(lesson.id); }} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
