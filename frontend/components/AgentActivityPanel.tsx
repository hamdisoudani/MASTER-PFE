"use client";
import React from "react";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { Activity, Loader2, CheckCircle2, Gauge } from "lucide-react";

type ContextUsage = { tokens?: number; budget?: number; fraction?: number };

function fmtTokens(n: number | undefined): string {
  if (!n || n <= 0) return "0";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function ContextMeter({ usage }: { usage: ContextUsage | null | undefined }) {
  if (!usage) return null;
  const tokens = usage.tokens ?? 0;
  const budget = usage.budget ?? 0;
  const frac = typeof usage.fraction === "number"
    ? usage.fraction
    : (budget > 0 ? Math.min(1, tokens / budget) : 0);
  const pct = Math.round(frac * 100);
  const danger = pct >= 85;
  const warn = pct >= 70 && !danger;
  const barColor = danger ? "bg-red-500" : warn ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="mb-3">
      <div className="flex items-center gap-2 mb-1 text-xs text-neutral-400">
        <Gauge className="h-3.5 w-3.5" />
        <span>Context window</span>
        <span className="ml-auto font-mono">
          {fmtTokens(tokens)} / {fmtTokens(budget)} tok ({pct}%)
        </span>
      </div>
      <div className="h-1.5 rounded bg-neutral-800 overflow-hidden">
        <div className={`h-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function AgentActivityPanel({ threadId }: { threadId: string }) {
  const stream = useSyllabusAgent({ threadId });
  const values = (stream.values as any) ?? {};
  const plan = values.plan ?? [];
  const ctx: ContextUsage | undefined = values.context_usage;
  return (
    <div className="rounded border border-neutral-800 p-3 text-sm">
      <div className="flex items-center gap-2 mb-2"><Activity className="h-4 w-4" /> Agent activity</div>
      <ContextMeter usage={ctx} />
      {plan.length === 0 && <div className="text-neutral-500">No active plan.</div>}
      <ul className="space-y-1">
        {plan.map((s: any) => (
          <li key={s.id} className="flex items-center gap-2">
            {s.status === "done" ? <CheckCircle2 className="h-3 w-3 text-green-500" /> : <Loader2 className="h-3 w-3 animate-spin" />}
            <span>{s.title}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
