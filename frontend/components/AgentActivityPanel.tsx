"use client";

import React from "react";
import { useCoAgentStateRender } from "@copilotkit/react-core";

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
  markdown: string;
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

const statusIcon = (status: StepStatus) => {
  if (status === "done") return "✅";
  if (status === "in_progress") return "⏳";
  if (status === "searching") return "🔎";
  return "◻️";
};

const typeBadge = (type: StepType) =>
  type === "search"
    ? "bg-blue-500/15 text-blue-300 border border-blue-500/30"
    : "bg-purple-500/15 text-purple-300 border border-purple-500/30";

export function AgentActivityPanel() {
  useCoAgentStateRender<AgentState>({
    name: "syllabus_agent",
    render: ({ state, nodeName, status }) => {
      const plan = state?.plan ?? [];
      const planStatus = state?.planStatus ?? "idle";
      const currentIdx = state?.currentStepIndex ?? 0;
      const activity = state?.current_activity ?? "";
      const scraped = state?.scraped_pages ?? [];

      if (
        plan.length === 0 &&
        !activity &&
        scraped.length === 0 &&
        status !== "inProgress"
      ) {
        return null;
      }

      const doneCount = plan.filter((s) => s.status === "done").length;
      const pct = plan.length
        ? Math.round((doneCount / plan.length) * 100)
        : 0;

      return (
        <div className="my-2 rounded-xl border border-white/10 bg-white/[0.03] text-xs overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10 bg-white/[0.02]">
            <span className="font-semibold tracking-wide uppercase opacity-70">Agent Activity</span>
            {nodeName && (<span className="font-mono text-[10px] opacity-50">· {nodeName}</span>)}
            {planStatus === "in_progress" && (<span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-300 border border-yellow-500/25 animate-pulse">running</span>)}
            {planStatus === "done" && (<span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-green-500/15 text-green-300 border border-green-500/25">done</span>)}
          </div>
          {activity && (<div className="px-3 py-1.5 text-[11px] text-white/70 border-b border-white/10 truncate">{activity}</div>)}
          {plan.length > 0 && (
            <ul className="px-2 py-2 space-y-1">
              {plan.map((step, i) => {
                const isActive = i === currentIdx && planStatus === "in_progress";
                return (
                  <li key={step.id ?? i} className={["rounded-md px-2 py-1.5 border transition-colors", isActive ? "border-indigo-500/40 bg-indigo-500/5" : "border-white/5 bg-transparent"].join(" ")}>
                    <div className="flex items-start gap-2">
                      <span className="text-sm leading-none mt-0.5">{statusIcon(step.status)}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className={["text-[9px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider", typeBadge(step.type)].join(" ")}>{step.type}</span>
                          <span className="text-[9px] text-white/40">#{i + 1}</span>
                        </div>
                        <p className="text-[11px] leading-snug text-white/85">{step.title}</p>
                        {step.queries && step.queries.length > 0 && (
                          <ul className="mt-1 space-y-0.5">
                            {step.queries.map((q, qi) => (<li key={qi} className="text-[10px] text-white/50 truncate pl-2 border-l border-white/10">{q}</li>))}
                          </ul>
                        )}
                        {step.search_data && step.search_data.length > 0 && (
                          <ul className="mt-1 space-y-0.5">
                            {step.search_data.map((sd, sdi) => (
                              <li key={sdi} className="text-[10px] text-white/60 pl-2 border-l border-blue-500/20">
                                <span className="text-blue-300/80">{sd.query}</span>
                                {sd.result_urls && sd.result_urls.length > 0 && (<span className="opacity-60"> · {sd.result_urls.length} results</span>)}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {scraped.length > 0 && (
            <div className="px-3 py-2 border-t border-white/10">
              <p className="text-[10px] uppercase tracking-wide text-white/50 mb-1">Scraped pages · {scraped.length}</p>
              <ul className="space-y-0.5">
                {scraped.slice(-3).map((p, i) => (<li key={i} className="text-[10px] text-white/60 truncate" title={p.url}>📄 {p.title || p.url}</li>))}
              </ul>
            </div>
          )}
          {plan.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-2 border-t border-white/10">
              <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                <div className="h-full bg-indigo-400 transition-all duration-500" style={{ width: `${pct}%` }} />
              </div>
              <span className="text-[10px] text-white/50 shrink-0 tabular-nums">{doneCount}/{plan.length}</span>
            </div>
          )}
        </div>
      );
    },
  });
  return null;
}
