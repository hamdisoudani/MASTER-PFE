"use client";

import React from "react";
import { useCopilotChat } from "@copilotkit/react-core";
import { PlanStep } from "./SyllabusViewerClient";

interface AgentActivityPanelProps {
  planSteps?: PlanStep[];
  currentStepIndex?: number;
  planStatus?: string;
  currentActivity?: string;
}

const statusIcon = (status: PlanStep["status"]) => {
  if (status === "done") return "✅";
  if (status === "searching") return "🔋";
  if (status === "pending") return "⍷";
  return "💧";
};

const stepTypeLabel = (type: PlanStep["type"]) =>
  type === "search" ? "Search" : "Task";

export function AgentActivityPanel({
  planSteps = [],
  currentStepIndex = 0,
  planStatus = "idle",
  currentActivity = "",
}: AgentActivityPanelProps) {
  const { isLoading } = useCopilotChat();

  return (
    <div className="flex flex-col h-full bg-[var(--background)] text-[var(--foreground)]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center gap-2">
        <span className="text-sm font-semibold tracking-wide uppercase opacity-70">
          Agent Activity
        </span>
        {isLoading && (
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-white/10 animate-pulse">
            thinking…
          </span>
        )}
        {planStatus === "done" && (
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-300">
            done
          </span>
        )}
      </div>

      {/* Current activity */}
      {currentActivity && (
        <div className="px-4 py-2 text-xs text-[var(--muted)] border-b border-[var(--border)] truncate">
          {currentActivity}
        </div>
      )}

      {/* Steps list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {planSteps.length === 0 && (
          <p className="text-xs text-[var(--muted)] text-center mt-8">
            No plan yet. Ask the agent to research a topic.
          </p>
        )}

        {planSteps.map((step, i) => {
          const isActive = i === currentStepIndex && planStatus === "in_progress";
          return (
            <div
              key={i}
              className={[
                "rounded-lg px-3 py-2 border transition-all",
                isActive
                  ? "border-[var(--accent)] bg-white/5"
                  : "border-[var(--border)] bg-white/[0.02]",
              ].join(" ")}
            >
              <div className="flex items-start gap-2">
                <span className="text-base leading-none mt-0.5">
                  {statusIcon(step.status)}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span
                      className={[
                        "text-[10px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider",
                        step.type === "search"
                          ? "bg-blue-500/20 text-blue-300"
                          : "bg-purple-500/20 text-purple-300",
                      ].join(" ")}
                    >
                      {stepTypeLabel(step.type)}
                    </span>
                    <span className="text-[10px] text-[var(--muted)]">
                      #{i + 1}
                    </span>
                  </div>
                  <p className="text-xs leading-snug truncate">
                    {step.description}
                  </p>
                  {step.queries && step.queries.length > 0 && (
                    <div className="mt-1 space-y-0.5">
                      {step.queries.map((q, qi) => (
                        <p
                          key={qi}
                          className="text-[10px] text-[var(--muted)] truncate pl-2 border-l border-white/10"
                        >
                          {q}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer progress */}
      {planSteps.length > 0 && (
        <div className="px-4 py-2 border-t border-[var(--border)] flex items-center gap-2">
          <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full bg-[var(--accent)] transition-all duration-500"
              style={{
                width: `${Math.round(
                  (planSteps.filter((s) => s.status === "done").length /
                    planSteps.length) *
                    100
                )}%`,
              }}
            />
          </div>
          <span className="text-[10px] text-[var(--muted)] shrink-0">
            {planSteps.filter((s) => s.status === "done").length}/
            {planSteps.length}
          </span>
        </div>
      )}
    </div>
  );
}
