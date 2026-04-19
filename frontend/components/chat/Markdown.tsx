"use client";
import React, { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";

const components: Components = {
  p: ({ children }) => <p className="leading-relaxed mb-2 last:mb-0">{children}</p>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-[var(--primary)] underline underline-offset-2 hover:opacity-80">
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 my-2">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 my-2">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => <h1 className="text-lg font-semibold mt-3 mb-1">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-semibold mt-3 mb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-[var(--border)] pl-3 text-[var(--muted-foreground)] my-2">{children}</blockquote>
  ),
  code: ({ className, children, ...props }: any) => {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock) {
      return (
        <code className={`${className ?? ""} block overflow-x-auto rounded-md bg-[var(--muted)] p-2 text-xs`} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-[var(--muted)] px-1 py-0.5 text-[0.85em] font-mono">{children}</code>
    );
  },
  pre: ({ children }) => <pre className="my-2 overflow-x-auto rounded-md">{children}</pre>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full border-collapse border border-[var(--border)] text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-[var(--border)] px-2 py-1 bg-[var(--muted)] text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-[var(--border)] px-2 py-1">{children}</td>,
  hr: () => <hr className="my-3 border-[var(--border)]" />,
};

function MarkdownImpl({ source }: { source: string }) {
  return (
    <div className="prose-custom break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
}

export const Markdown = memo(MarkdownImpl, (a, b) => a.source === b.source);
Markdown.displayName = "Markdown";
