"use client";
import * as React from "react";
import { useQueryState } from "nuqs";
import { Gauge, Zap, Sparkles } from "lucide-react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { useThreads, threadVariant } from "@/providers/Thread";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";

function firstUserPreview(t: any): string {
  const msgs = (t?.values as any)?.messages ?? [];
  const first = msgs.find((m: any) => m?.type === "human" || m?.role === "user");
  const c = first?.content;
  if (typeof c === "string") return c.slice(0, 80);
  if (Array.isArray(c)) {
    const t0 = c.find((p: any) => p?.type === "text");
    if (t0?.text) return String(t0.text).slice(0, 80);
  }
  return t?.thread_id?.slice(0, 8) ?? "(no thread)";
}

function fmtTokens(n: number | undefined): string {
  if (!n || n <= 0) return "0";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function HeaderContextMeter({ threadId }: { threadId: string }) {
  const stream = useSyllabusAgent({ threadId });
  const usage = (stream.values as any)?.context_usage as
    | { tokens?: number; budget?: number; fraction?: number }
    | undefined;
  if (!usage) return null;
  const tokens = usage.tokens ?? 0;
  const budget = usage.budget ?? 0;
  const frac =
    typeof usage.fraction === "number"
      ? usage.fraction
      : budget > 0
      ? Math.min(1, tokens / budget)
      : 0;
  const pct = Math.round(frac * 100);
  const danger = pct >= 85;
  const warn = pct >= 70 && !danger;
  const barColor = danger ? "bg-red-500" : warn ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="hidden md:flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
      <Gauge className="h-3.5 w-3.5" />
      <div className="h-1.5 w-24 rounded bg-[var(--muted)] overflow-hidden">
        <div className={`h-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono tabular-nums">
        {fmtTokens(tokens)}/{fmtTokens(budget)} ({pct}%)
      </span>
    </div>
  );
}

export function SiteHeader() {
  const [threadId] = useQueryState("threadId");
  const { threads } = useThreads();
  const thread = React.useMemo(
    () => threads.find((t: any) => t.thread_id === threadId) ?? null,
    [threads, threadId],
  );
  const name = thread ? firstUserPreview(thread) : "No thread selected";
  const variant = thread ? threadVariant(thread) : null;
  const VIcon = variant === "deep" ? Sparkles : Zap;

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-[var(--border)] bg-[var(--background)] px-3">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mx-1 h-5" />
      {variant && (
        <VIcon
          className={`h-3.5 w-3.5 shrink-0 ${variant === "deep" ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"}`}
          aria-label={variant}
        />
      )}
      <div className="min-w-0 flex-1 truncate text-sm font-medium" title={name}>
        {name}
      </div>
      {threadId && <HeaderContextMeter threadId={threadId} />}
    </header>
  );
}
