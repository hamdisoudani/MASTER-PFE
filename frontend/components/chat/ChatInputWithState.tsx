"use client";

import React, { useMemo, useRef, useState } from "react";
import { useCoAgent } from "@copilotkit/react-core";
import {
  ChevronDown,
  Activity,
  Sparkles,
  Search,
  CheckCircle2,
  Loader2,
  FileText,
  ListChecks,
} from "lucide-react";

type StepStatus = "pending" | "in_progress" | "searching" | "done" | string;
type StepType = "task" | "search" | string;

interface SearchQuery {
  query: string;
  result_urls?: string[];
  selected_urls?: string[];
}

interface PlanStep {
  id: number;
  type: StepType;
  title: string;
  status: StepStatus;
  queries?: string[];
  search_data?: SearchQuery[];
}

interface ScrapedPage {
  url: string;
  title: string;
  markdown?: string;
}

interface AgentState {
  plan?: PlanStep[];
  currentStepIndex?: number;
  planStatus?: "idle" | "in_progress" | "done" | string;
  search_results?: SearchQuery[];
  scraped_pages?: ScrapedPage[];
  current_activity?: string | null;
  finished?: boolean;
}

interface InputProps {
  inProgress: boolean;
  onSend: (text: string) => Promise<unknown> | unknown;
  isVisible?: boolean;
  onStop?: () => void;
  onUpload?: () => void;
  hideStopButton?: boolean;
  chatReady?: boolean;
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "done")
    return <CheckCircle2 className="w-3.5 h-3.5 text-[var(--secondary)] shrink-0" />;
  if (status === "in_progress")
    return <Loader2 className="w-3.5 h-3.5 text-[var(--primary)] animate-spin shrink-0" />;
  if (status === "searching")
    return <Search className="w-3.5 h-3.5 text-[var(--primary)] animate-pulse shrink-0" />;
  return <div className="w-3.5 h-3.5 rounded-full border border-[var(--border)] shrink-0" />;
}

function TypeBadge({ type }: { type: StepType }) {
  const isSearch = type === "search";
  return (
    <span
      className="text-[9px] font-[var(--font-mono)] uppercase tracking-[0.08em] px-1.5 py-[1px] rounded-[3px] border"
      style={{
        color: isSearch ? "var(--secondary)" : "var(--primary)",
        borderColor: isSearch
          ? "color-mix(in srgb, var(--secondary) 35%, transparent)"
          : "color-mix(in srgb, var(--primary) 35%, transparent)",
        background: isSearch
          ? "color-mix(in srgb, var(--secondary) 10%, transparent)"
          : "color-mix(in srgb, var(--primary) 10%, transparent)",
      }}
    >
      {isSearch ? (
        <Search className="w-2.5 h-2.5 inline -mt-0.5 mr-0.5" />
      ) : (
        <Sparkles className="w-2.5 h-2.5 inline -mt-0.5 mr-0.5" />
      )}
      {type}
    </span>
  );
}

/**
 * Collapsible agent state panel rendered INSIDE the custom chat Input
 * (above the textarea). When collapsed it shows a one-line status strip;
 * when expanded it shows the full plan + activity + scraped pages.
 */
function AgentStateStrip() {
  const { state, running } = useCoAgent<AgentState>({ name: "syllabus_agent" });
  const [open, setOpen] = useState(false);

  const plan = state?.plan ?? [];
  const planStatus = state?.planStatus ?? "idle";
  const currentIdx = state?.currentStepIndex ?? 0;
  const activity = state?.current_activity ?? "";
  const scraped = state?.scraped_pages ?? [];

  const hasContent = plan.length > 0 || !!activity || scraped.length > 0 || running;
  const { doneCount, pct, activeStep } = useMemo(() => {
    const done = plan.filter((s) => s.status === "done").length;
    return {
      doneCount: done,
      pct: plan.length ? Math.round((done / plan.length) * 100) : 0,
      activeStep: plan[currentIdx],
    };
  }, [plan, currentIdx]);

  if (!hasContent) return null;

  const statusLabel =
    planStatus === "in_progress" || running
      ? "running"
      : planStatus === "done"
      ? "complete"
      : "idle";
  const statusColor =
    statusLabel === "running"
      ? "var(--primary)"
      : statusLabel === "complete"
      ? "var(--secondary)"
      : "var(--muted-foreground)";

  return (
    <div
      className="mb-2 rounded-[var(--radius)] overflow-hidden transition-all duration-300"
      style={{
        fontFamily: "var(--font-sans)",
        background: "color-mix(in srgb, var(--card) 92%, transparent)",
        border: "1px solid var(--border)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="group w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--accent)] transition-colors"
      >
        <span
          className="relative flex items-center justify-center w-6 h-6 rounded-md"
          style={{
            background: "color-mix(in srgb, var(--primary) 14%, transparent)",
            border: "1px solid color-mix(in srgb, var(--primary) 30%, transparent)",
          }}
        >
          <Activity className="w-3.5 h-3.5" style={{ color: "var(--primary)" }} />
          {statusLabel === "running" && (
            <span
              className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full animate-pulse"
              style={{ background: "var(--primary)" }}
            />
          )}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="text-[11px] font-medium uppercase tracking-[0.08em]"
              style={{ fontFamily: "var(--font-mono)", color: "var(--foreground)" }}
            >
              Agent
            </span>
            <span
              className="text-[9px] uppercase tracking-[0.1em] px-1.5 py-[1px] rounded-[3px]"
              style={{
                fontFamily: "var(--font-mono)",
                color: statusColor,
                background: "color-mix(in srgb, currentColor 12%, transparent)",
                border: "1px solid color-mix(in srgb, currentColor 30%, transparent)",
              }}
            >
              {statusLabel}
            </span>
            {plan.length > 0 && (
              <span
                className="text-[10px]"
                style={{
                  fontFamily: "var(--font-mono)",
                  color: "var(--muted-foreground)",
                }}
              >
                {doneCount}/{plan.length} · {pct}%
              </span>
            )}
          </div>
          <div
            className="text-[11px] truncate mt-0.5"
            style={{ color: "var(--muted-foreground)" }}
          >
            {open
              ? "Plan, activity & research"
              : activity ||
                (activeStep
                  ? `Step ${activeStep.id + 1}: ${activeStep.title}`
                  : "Idle")}
          </div>
        </div>

        <ChevronDown
          className="w-4 h-4 transition-transform duration-200 shrink-0"
          style={{
            color: "var(--muted-foreground)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
        />
      </button>

      {plan.length > 0 && (
        <div
          className="h-[2px]"
          style={{
            background: "color-mix(in srgb, var(--border) 60%, transparent)",
          }}
        >
          <div
            className="h-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              background:
                "linear-gradient(90deg, var(--primary), var(--secondary))",
            }}
          />
        </div>
      )}

      {open && (
        <div className="max-h-[38vh] overflow-y-auto px-3 py-2 space-y-3 text-[11px]">
          {activity && (
            <div
              className="flex items-start gap-2 p-2 rounded-[6px]"
              style={{
                background: "color-mix(in srgb, var(--primary) 6%, transparent)",
                border:
                  "1px solid color-mix(in srgb, var(--primary) 20%, transparent)",
              }}
            >
              <Loader2
                className="w-3 h-3 mt-0.5 animate-spin shrink-0"
                style={{ color: "var(--primary)" }}
              />
              <span style={{ color: "var(--foreground)" }}>{activity}</span>
            </div>
          )}

          {plan.length > 0 && (
            <div>
              <div
                className="flex items-center gap-1.5 mb-1.5 text-[10px] uppercase tracking-[0.1em]"
                style={{
                  fontFamily: "var(--font-mono)",
                  color: "var(--muted-foreground)",
                }}
              >
                <ListChecks className="w-3 h-3" />
                Plan
              </div>
              <ol className="space-y-1.5">
                {plan.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-start gap-2 p-1.5 rounded-[4px]"
                    style={{
                      background:
                        s.status === "in_progress" || s.status === "searching"
                          ? "color-mix(in srgb, var(--primary) 8%, transparent)"
                          : "transparent",
                    }}
                  >
                    <StepIcon status={s.status} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className="text-[10px]"
                          style={{
                            fontFamily: "var(--font-mono)",
                            color: "var(--muted-foreground)",
                          }}
                        >
                          {String(s.id + 1).padStart(2, "0")}
                        </span>
                        <TypeBadge type={s.type} />
                      </div>
                      <div
                        className="mt-0.5 leading-snug"
                        style={{
                          color:
                            s.status === "done"
                              ? "var(--muted-foreground)"
                              : "var(--foreground)",
                          textDecoration:
                            s.status === "done" ? "line-through" : "none",
                        }}
                      >
                        {s.title}
                      </div>
                      {s.queries && s.queries.length > 0 && (
                        <ul
                          className="mt-1 space-y-0.5 pl-2"
                          style={{
                            borderLeft:
                              "1px solid color-mix(in srgb, var(--secondary) 35%, transparent)",
                          }}
                        >
                          {s.queries.map((q, qi) => (
                            <li
                              key={qi}
                              className="text-[10px]"
                              style={{
                                fontFamily: "var(--font-mono)",
                                color: "var(--muted-foreground)",
                              }}
                            >
                              ⌕ {q}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {scraped.length > 0 && (
            <div>
              <div
                className="flex items-center gap-1.5 mb-1.5 text-[10px] uppercase tracking-[0.1em]"
                style={{
                  fontFamily: "var(--font-mono)",
                  color: "var(--muted-foreground)",
                }}
              >
                <FileText className="w-3 h-3" />
                Scraped ({scraped.length})
              </div>
              <ul className="space-y-1">
                {scraped.slice(-8).map((p, i) => (
                  <li
                    key={i}
                    className="truncate text-[10px]"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                      style={{ color: "var(--secondary)" }}
                    >
                      {p.title || p.url}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Custom CopilotChat Input:
 *   [ Collapsible agent-state panel ]
 *   [ Textarea + send/stop button   ]
 *
 * Reuses CopilotKit's default `copilotKitInput*` CSS classes so styling
 * stays consistent with the rest of the chat UI.
 */
export function ChatInputWithState({
  inProgress,
  onSend,
  onStop,
  chatReady = true,
  hideStopButton = false,
}: InputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || inProgress) return;
    onSend(trimmed);
    setText("");
    textareaRef.current?.focus();
  };

  const canSend = !inProgress && text.trim().length > 0 && chatReady;
  const canStop = inProgress && !hideStopButton;
  const sendDisabled = !canSend && !canStop;

  return (
    <div className="copilotKitInputContainer">
      <AgentStateStrip />
      <div
        className="copilotKitInput"
        onClick={(e) => {
          const target = e.target as HTMLElement;
          if (target.closest("button") || target.tagName === "TEXTAREA") return;
          textareaRef.current?.focus();
        }}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Describe the course you want to plan..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) send();
            }
          }}
          style={{
            resize: "none",
            width: "100%",
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--foreground)",
            fontFamily: "var(--font-sans)",
            fontSize: "14px",
            lineHeight: "1.4",
            maxHeight: "160px",
          }}
        />
        <div className="copilotKitInputControls">
          <div style={{ flexGrow: 1 }} />
          <button
            type="button"
            disabled={sendDisabled}
            onClick={inProgress && !hideStopButton ? onStop : send}
            className="copilotKitInputControlButton"
            aria-label={inProgress ? "Stop" : "Send"}
            data-copilotkit-in-progress={inProgress}
          >
            {inProgress && !hideStopButton ? (
              <span aria-hidden>■</span>
            ) : (
              <span aria-hidden>➤</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatInputWithState;
