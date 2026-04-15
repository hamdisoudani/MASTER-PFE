'use client';

import { useRef, useEffect } from 'react';
import { useCopilotChat } from '@copilotkit/react-core';
import { Role, TextMessage } from '@copilotkit/runtime-client-gql';

interface ChatProps {
  threadId: string;
  onPlanUpdate: (steps: string[]) => void;
}

export function Chat({ threadId, onPlanUpdate }: ChatProps) {
  const { visibleMessages, appendMessage, isLoading, stopGeneration } = useCopilotChat();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [visibleMessages]);

  const handleSend = async () => {
    const text = inputRef.current?.value.trim();
    if (!text || isLoading) return;
    if (inputRef.current) inputRef.current.value = '';
    await appendMessage(new TextMessage({ content: text, role: Role.User }));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-4">
        {visibleMessages.length === 0 && (
          <div className="text-center text-[var(--muted)] mt-16">
            <p className="text-2xl mb-2">🤖</p>
            <p>Ask me anything. I'll create a plan and execute it.</p>
          </div>
        )}
        {visibleMessages.map((msg, i) => {
          const isUser = msg.role === Role.User;
          const content = msg instanceof TextMessage ? msg.content : '';
          return (
            <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${isUser ? 'bg-[var(--accent)] text-white rounded-br-sm' : 'bg-white/5 text-[var(--text)] rounded-bl-sm border border-[var(--border)]'}`}>
                {content}
              </div>
            </div>
          );
        })}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white/5 border border-[var(--border)] rounded-2xl rounded-bl-sm px-4 py-3">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => <span key={i} className="w-2 h-2 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />)}
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-[var(--border)] p-4">
        <div className="flex gap-2 items-end">
          <textarea ref={inputRef} rows={1} placeholder="Type a message… (Enter to send, Shift+Enter for newline)" onKeyDown={handleKeyDown}
            className="flex-1 resize-none rounded-xl bg-white/5 border border-[var(--border)] text-[var(--text)] placeholder-[var(--muted)] px-4 py-3 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors" />
          {isLoading
            ? <button onClick={stopGeneration} className="px-4 py-3 rounded-xl bg-red-500/20 hover:bg-red-500/40 text-red-400 text-sm font-medium transition-colors">Stop</button>
            : <button onClick={handleSend} className="px-4 py-3 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors">Send</button>
          }
        </div>
      </div>
    </div>
  );
}
