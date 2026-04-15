'use client';

import { useState } from 'react';
import { CopilotKit } from '@copilotkit/react-core';
import { Chat } from '../components/Chat';
import { PlanAccordion } from '../components/PlanAccordion';

interface ChatSession {
  id: string;
  userId: string;
  threadId: string;
  title: string;
  createdAt: string;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_COPILOT_URL ?? 'http://localhost:4000/copilot';
const USER_ID = 'user-1';

export default function Home() {
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChat, setActiveChat] = useState<ChatSession | null>(null);
  const [plan, setPlan] = useState<string[]>([]);

  const createChat = async () => {
    const res = await fetch('http://localhost:4000/chats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId: USER_ID, title: 'New Chat' }),
    });
    const chat: ChatSession = await res.json();
    setChats((prev) => [chat, ...prev]);
    setActiveChat(chat);
    setPlan([]);
  };

  const deleteChat = async (id: string) => {
    await fetch(`http://localhost:4000/chats/${id}`, { method: 'DELETE' });
    setChats((prev) => prev.filter((c) => c.id !== id));
    if (activeChat?.id === id) { setActiveChat(null); setPlan([]); }
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-64 flex flex-col border-r border-[var(--border)] bg-[var(--sidebar)]">
        <div className="p-4 border-b border-[var(--border)]">
          <h1 className="text-lg font-bold text-[var(--accent)]">AI Assistant</h1>
        </div>
        <div className="p-3">
          <button onClick={createChat} className="w-full py-2 px-4 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors">
            + New Chat
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-1">
          {chats.map((chat) => (
            <div key={chat.id}
              className={`group flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer text-sm transition-colors ${activeChat?.id === chat.id ? 'bg-[var(--accent)] text-white' : 'text-[var(--muted)] hover:bg-white/5'}`}
              onClick={() => { setActiveChat(chat); setPlan([]); }}>
              <span className="truncate">{chat.title}</span>
              <button onClick={(e) => { e.stopPropagation(); deleteChat(chat.id); }} className="opacity-0 group-hover:opacity-100 text-xs text-red-400 hover:text-red-300 ml-2">✕</button>
            </div>
          ))}
          {chats.length === 0 && <p className="text-xs text-[var(--muted)] text-center py-4">No chats yet. Create one!</p>}
        </nav>
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden">
        {activeChat ? (
          <CopilotKit runtimeUrl={BACKEND_URL} agent="myAgent">
            <div className="flex flex-1 overflow-hidden">
              <div className="flex-1 flex flex-col overflow-hidden">
                <Chat threadId={activeChat.threadId} onPlanUpdate={setPlan} />
              </div>
              {plan.length > 0 && (
                <aside className="w-72 border-l border-[var(--border)] overflow-y-auto scrollbar-thin p-4">
                  <PlanAccordion steps={plan} />
                </aside>
              )}
            </div>
          </CopilotKit>
        ) : (
          <div className="flex-1 flex items-center justify-center text-[var(--muted)]">
            <div className="text-center"><div className="text-5xl mb-4">💬</div><p className="text-lg">Select a chat or create a new one</p></div>
          </div>
        )}
      </main>
    </div>
  );
}
