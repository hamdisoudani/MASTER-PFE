"use client";
import React from "react";
import { Check, Circle, Loader2 } from "lucide-react";
import { usePlanStore, type PlanItem } from "@/stores/plan-store";

function ItemIcon({ status }: { status: PlanItem["status"] }) {
  if (status === "done") return <Check className="h-3.5 w-3.5 text-emerald-500" />;
  if (status === "in_progress") return <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--primary)]" />;
  return <Circle className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />;
}

export function PlanCard() {
  const items = usePlanStore((s) => s.items);
  if (!items || items.length === 0) return null;

  const done = items.filter((i) => i.status === "done").length;
  return (
    <div className="mx-3 my-2 rounded-md border border-[var(--border)] bg-[var(--muted)]/30 px-3 py-2 text-sm">
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
          Plan
        </div>
        <div className="text-[10px] text-[var(--muted-foreground)]">
          {done}/{items.length}
        </div>
      </div>
      <ul className="space-y-1">
        {items.map((it) => (
          <li key={it.id} className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0">
              <ItemIcon status={it.status} />
            </span>
            <span
              className={
                it.status === "done"
                  ? "line-through text-[var(--muted-foreground)]"
                  : "text-[var(--foreground)]"
              }
            >
              {it.title}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
