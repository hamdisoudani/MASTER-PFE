"use client";

import { useState, useRef, useEffect } from "react";
import { useCopilotChat } from "@copilotkit/react-core";
import { Role, TextMessage } from "@copilotkit/runtime-client-gql";
import { useAgentState } from "@copilotkit/react-core";
import { Send, Loader2, BotMessageSquare, CheckCircle2, Circle, ArrowRight } from "lucide-react";

interface PlanTask {
  id: number;
  task: string;
  status: "pending" | "in_progress" | "done";
}

interface AgentState {
  plan?: PlanTask[];
  current_activity?: string;
}

const EMPTY_STATE: AgentState = {};

export function CustomChat() {
  const { visibleMessages, appendMessage, isLoading } = useCopilotChat();
  const [agentState] = useAgentState<AgentState>("syllabus-agent", EMPTY_STATE);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const plan: PlanTask[] = agentState?.plan ?? [];
  const currentActivity: string = agentState?.current_activity ?? "";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleMessages, plan]);

  function handleSend() {
    const text = input.trim();
    if (!text || isLoading) return;
    appendMessage(new TextMessage({ content: text, role: Role.User }));
    setInput("");
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col h-full bg-[var(--card)] text-[var(--text)]">

      {/* Header */}
      <div className="shrink-0 flex items-center gap-2 px-3 py-2 border-b border-[var(--border)] bg-[var(--card)]">
        <BotMessageSquare className="w-4 h-4 text-[var(--primary)]" />
        <span className="text-xs font-semibold flex-1 truncate">
          {currentActivity || "AI Assistant"}
        </span>
        {isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--muted)]" />}
      </div>

      {/* Plan strip */}
      {plan.length > 0 && (
        <div className="shrink-0 border-b border-[var(--border)] px-2 py-1.5 space-y-0.5 bg-[var(--bg)] max-h-40 overflow-y-auto">
          {plan.map((task) => (
            <div key={task.id} className="flex items-start gap-1.5 text-xs">
              <PlanIcon status={task.status} />
              <span
                className={`flex-1 leading-snug ${
                  task.status === "done"
                    ? "text-[var(--muted)] line-through"
                    : task.status === "in_progress"
                    ? "text-[var(--primary)] font-medium"
                    : "text-[var(--muted)]"
                }`}
              >
                {task.task}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {visibleMessages.length === 0 && (
          <p className="text-xs text-center text-[var(--muted)] mt-8 opacity-70">
            Ask me to create a syllabus, add chapters, or search topics.
          </p>
        )}
        {visibleMessages.map((msg, i) => {
          const isUser = msg.role === Role.User;
          const text =
            msg instanceof TextMessage
              ? msg.content
              : "[non-text message]";
          return (
            <div key={i} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap break-words ${
                  isUser
                    ? "bg-[var(--primary)] text-white rounded-br-none"
                    : "bg-[var(--muted)]/15 text-[var(--text)] rounded-bl-none"
                }`}
              >
                {text}
              </div>
            </div>
          );
        })}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[var(--muted)]/15 rounded-xl rounded-bl-none px-3 py-2">
              <span className="flex gap-1">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="w-1.5 h-1.5 rounded-full bg-[var(--muted)] animate-bounce"
                    style={{ animationDelay: `${d * 150}ms` }}
                  />
                ))}
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-[var(--border)] p-2">
        <div className="flex items-end gap-2 bg-[var(--bg)] rounded-xl border border-[var(--border)] px-3 py-2 focus-within:border-[var(--primary)] transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask the AI…"
            rows={1}
            className="flex-1 resize-none bg-transparent text-xs text-[var(--text)] placeholder:text-[var(--muted)] outline-none max-h-28 overflow-y-auto"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="shrink-0 p-1.5 rounded-lg bg-[var(--primary)] text-white disabled:opacity-40 hover:opacity-90 transition-opacity"
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function PlanIcon({ status }: { status: PlanTask["status"] }) {
  if (status === "done")
    return <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-green-500 mt-px" />;
  if (status === "in_progress")
    return <ArrowRight className="w-3.5 h-3.5 shrink-0 text-[var(--primary)] mt-px" />;
  return <Circle className="w-3.5 h-3.5 shrink-0 text-[var(--muted)] mt-px" />;
}
