"use client";

import React, { useState, useMemo } from "react";
import { useCoAgent } from "@copilotkit/react-core";
import { ChevronDown, Activity, Sparkles, Search, CheckCircle2, Loader2, FileText } from "lucide-react";

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
      {isSearch ? <Search className="w-2.5 h-2.5 inline -mt-0.5 mr-0.5" /> : <Sparkles className="w-2.5 h-2.5 inline -mt-0.5 mr-0.5" />}
      {type}
    </span>
  );
}

export function AgentActivityPanel() {
  const { state, running } = useCoAgent<AgentState>({ name: "syllabus_agent" });
  const [collapsed, setCollapsed] = useState(false);

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
      className="pointer-events-auto absolute left-3 right-3 bottom-[88px] z-20"
      style={{ fontFamily: "var(--font-sans)" }}
    >
      <div
        className="rounded-[var(--radius)] overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.45)] backdrop-blur-md transition-all duration-300"
        style={{
          background: "color-mix(in srgb, var(--card) 92%, transparent)",
          border: "1px solid var(--border)",
        }}
      >
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
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
              <span className="text-[11px] font-semibold tracking-[0.12em] uppercase" style={{ color: "var(--foreground)" }}>Agent Activity</span>
              <span className="text-[9px] font-[var(--font-mono)] uppercase tracking-[0.1em] px-1.5 py-[1px] rounded-[3px]" style={{ color: statusColor, background: "color-mix(in srgb, currentColor 10%, transparent)", border: "1px solid color-mix(in srgb, currentColor 30%, transparent)" }}>{statusLabel}</span>
            </div>
            {collapsed && activeStep && (<p className="mt-0.5 text-[11px] truncate" style={{ color: "var(--muted-foreground)" }}>{activeStep.title}</p>)}
            {collapsed && !activeStep && activity && (<p className="mt-0.5 text-[11px] truncate" style={{ color: "var(--muted-foreground)" }}>{activity}</p>)}
          </div>
          {plan.length > 0 && (<span className="text-[10px] font-[var(--font-mono)] tabular-nums shrink-0" style={{ color: "var(--muted-foreground)" }}>{doneCount}/{plan.length}</span>)}
          <ChevronDown className="w-4 h-4 shrink-0 transition-transform duration-300" style={{ color: "var(--muted-foreground)", transform: collapsed ? "rotate(0deg)" : "rotate(180deg)" }} />
        </button>
        {plan.length > 0 && (
          <div className="h-[2px] w-full" style={{ background: "color-mix(in srgb, var(--border) 70%, transparent)" }}>
            <div className="h-full transition-all duration-500" style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%)", boxShadow: "0 0 8px color-mix(in srgb, var(--primary) 60%, transparent)" }} />
          </div>
        )}
        <div className="grid transition-[grid-template-rows] duration-300 ease-out" style={{ gridTemplateRows: collapsed ? "0fr" : "1fr" }}>
          <div className="min-h-0 overflow-hidden">
            <div className="max-h-[46vh] overflow-y-auto px-3 py-2.5 space-y-3">
              {activity && (<div className="text-[11px] leading-relaxed italic" style={{ color: "var(--muted-foreground)" }}>{activity}</div>)}
              {plan.length > 0 && (
                <ol className="space-y-1.5">
                  {plan.map((step, i) => {
                    const isActive = i === currentIdx && planStatus === "in_progress";
                    return (
                      <li key={step.id ?? i} className="rounded-md px-2 py-1.5 transition-colors" style={{ background: isActive ? "color-mix(in srgb, var(--primary) 8%, transparent)" : "transparent", border: isActive ? "1px solid color-mix(in srgb, var(--primary) 35%, transparent)" : "1px solid transparent" }}>
                        <div className="flex items-start gap-2">
                          <div className="mt-0.5"><StepIcon status={step.status} /></div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-0.5">
                              <TypeBadge type={step.type} />
                              <span className="text-[9px] font-[var(--font-mono)]" style={{ color: "var(--muted-foreground)" }}>#{String(i + 1).padStart(2, "0")}</span>
                            </div>
                            <p className="text-[11.5px] leading-snug" style={{ color: "var(--foreground)" }}>{step.title}</p>
                            {step.queries && step.queries.length > 0 && (
                              <ul className="mt-1 space-y-0.5">
                                {step.queries.map((q, qi) => (<li key={qi} className="text-[10px] truncate pl-2 border-l" style={{ color: "var(--muted-foreground)", borderColor: "color-mix(in srgb, var(--border) 80%, transparent)" }}>{q}</li>))}
                              </ul>
                            )}
                            {step.search_data && step.search_data.length > 0 && (
                              <ul className="mt-1 space-y-0.5">
                                {step.search_data.map((sd, sdi) => (
                                  <li key={sdi} className="text-[10px] pl-2 border-l" style={{ borderColor: "color-mix(in srgb, var(--secondary) 40%, transparent)", color: "var(--muted-foreground)" }}>
                                    <span style={{ color: "var(--secondary)" }}>{sd.query}</span>
                                    {sd.result_urls && sd.result_urls.length > 0 && (<span className="opacity-70"> · {sd.result_urls.length} results</span>)}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
              {scraped.length > 0 && (
                <div className="pt-2 border-t" style={{ borderColor: "var(--border)" }}>
                  <div className="flex items-center gap-1.5 mb-1 text-[9px] uppercase tracking-[0.12em]" style={{ color: "var(--muted-foreground)" }}>
                    <FileText className="w-3 h-3" />
                    Scraped pages · {scraped.length}
                  </div>
                  <ul className="space-y-0.5">
                    {scraped.slice(-4).map((p, i) => (<li key={i} className="text-[10.5px] truncate" style={{ color: "var(--muted-foreground)" }} title={p.url}>→ {p.title || p.url}</li>))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
