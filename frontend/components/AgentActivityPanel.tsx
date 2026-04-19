"use client";
import React from "react";
import { useSyllabusAgent } from "@/lib/useSyllabusAgent";
import { Activity, Loader2, CheckCircle2 } from "lucide-react";

export function AgentActivityPanel({ threadId }: { threadId: string }) {
  const stream = useSyllabusAgent({ threadId });
  const plan = (stream.values as any)?.plan ?? [];
  return (
    <div className="rounded border border-neutral-800 p-3 text-sm">
      <div className="flex items-center gap-2 mb-2"><Activity className="h-4 w-4" /> Agent activity</div>
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
