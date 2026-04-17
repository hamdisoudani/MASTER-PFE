"use client";

import { useState, useRef, useEffect } from "react";
import { useCopilotChat } from "@copilotkit/react-core";
import { Role, TextMessage } from "@copilotkit/runtime-client-gql";
import { useCoAgent } from "@copilotkit/react-core";
import { Send, Loader2, BotMessageSquare, CheckCircle2, Circle, Clock } from "lucide-react";

type TaskStatus = "pending" | "in_progress" | "done";

interface Task {
  id: number;
  description: string;
  status: TaskStatus;
}

interface AgentState {
  tasks?: Task[];
  syllabus?: string;
  messages?: Array<{ role: string; content: string }>;
}

const EMPTY_STATE: AgentState = {};

function TaskStatusIcon({ status }: { status: TaskStatus }) {
  if (status === "done") return <CheckCircle2 className="w-4 h-4 text-green-400" />;
  if (status === "in_progress") return <Clock className="w-4 h-4 text-yellow-400 animate-spin" />;
  return <Circle className="w-4 h-4 text-gray-400" />;
}

export function Chat() {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // visibleMessages is the correct property on UseCopilotChatReturn (not `messages`)
  const { appendMessage, visibleMessages, isLoading } = useCopilotChat();
  const { state: agentState } = useCoAgent<AgentState>({
    name: "syllabus_agent",
    initialState: EMPTY_STATE,
  });

  const tasks: Task[] = agentState?.tasks ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleMessages]);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    appendMessage(new TextMessage({ content: input, role: Role.User }));
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0d0d0d] text-white">
      {/* Task progress panel */}
      {tasks.length > 0 && (
        <div className="border-b border-white/10 px-4 py-3 bg-white/5">
          <p className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-2">Agent Plan</p>
          <ul className="space-y-1">
            {tasks.map((t) => (
              <li key={t.id} className="flex items-center gap-2 text-sm">
                <TaskStatusIcon status={t.status} />
                <span className={t.status === "done" ? "line-through text-white/40" : ""}>
                  {t.description}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {visibleMessages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center text-white/30 gap-3">
            <BotMessageSquare className="w-12 h-12" />
            <p className="text-sm">Ask the syllabus AI anything.<br />It can search the web and build full course outlines.</p>
          </div>
        )}

        {visibleMessages.map((msg, i) => {
          const isUser = msg instanceof TextMessage && msg.role === Role.User;
          const content = msg instanceof TextMessage ? msg.content : null;
          if (!content) return null;

          return (
            <div key={i} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                  isUser
                    ? "bg-indigo-600 text-white"
                    : "bg-white/10 text-white/90"
                }`}
              >
                {content}
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white/10 rounded-2xl px-4 py-2">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/10 p-4">
        <div className="flex gap-2 items-end">
          <textarea
            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:border-indigo-500 placeholder:text-white/30"
            rows={2}
            placeholder="Describe the course you want to plan..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="p-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// Alias used by SyllabusViewerClient
export { Chat as CustomChat };
