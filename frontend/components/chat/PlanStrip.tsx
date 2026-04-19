"use client";
import React, { useState } from "react";
import { ChevronDown, ChevronRight, ListChecks, Check, Circle, Loader2 } from "lucide-react";
import { usePlanStore, type PlanItem } from "@/stores/plan-store";

function ItemIcon({ status }: { status: PlanItem["status"] }) {
  if (status === "done") return <Check className="h-3.5 w-3.5 text-emerald-500" />;
  if (status === "in_progress") return <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--primary)]" />;
  return <Circle className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />;
}

/**
 * Collapsible plan strip rendered pinned just above the chat input so the
 * current execution plan is always visible while the user types / the agent
 * streams. Defaults to expanded while a step is in_progress, collapsed when
 * the plan is fully done, and remembers the user's manual toggle otherwise.
 */
export function PlanStrip() {
  const items = usePlanStore((s) => s.items);
  const inProgress = items.some((i) => i.status === "in_progress");
  const done = items.filter((i) => i.status === "done").length;
  const total = items.length;
  const allDone = total > 0 && done === total;

  const [userToggled, setUserToggled] = useState(false);
  const [open, setOpen] = useState<boolean>(true);

  React.useEffect(() => {
    if (userToggled) return;
    if (inProgress) setOpen(true);
    else if (allDone) setOpen(false);
  }, [inProgress, allDone, userToggled]);

  if (!items || total === 0) return null;

  return (
    <div className="mx-2 mt-2 rounded-md border border-[var(--border)] bg-[var(--muted)]/20 text-sm overflow-hidden">
      <button
        type="button"
        onClick={() => {
          setUserToggled(true);
          setOpen((o) => !o);
        }}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 hover:bg-[var(--muted)]/30 transition-colors text-left"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />
        )}
        <ListChecks className="h-3.5 w-3.5 text-[var(--primary)]" />
        <span className="text-[11px] uppercase tracking-wider text-[var(--muted-foreground)] font-semibold">
          Plan
        </span>
        <span className="ml-auto flex items-center gap-2">
          <span className="h-1.5 w-16 rounded-full bg-[var(--muted)]/40 overflow-hidden">
            <span
              className="block h-full bg-[var(--primary)] transition-[width] duration-300"
              style={{ width: `${total === 0 ? 0 : (done / total) * 100}%` }}
            />
          </span>
          <span className="text-[10px] tabular-nums text-[var(--muted-foreground)]">
            {done}/{total}
          </span>
          {inProgress && (
            <Loader2 className="h-3 w-3 animate-spin text-[var(--primary)]" />
          )}
        </span>
      </button>
      {open && (
        <ul className="max-h-40 overflow-y-auto px-3 py-2 space-y-1 border-t border-[var(--border)]">
          {items.map((it) => (
            <li key={it.id} className="flex items-start gap-2">
              <span className="mt-0.5 shrink-0">
                <ItemIcon status={it.status} />
              </span>
              <span
                className={
                  it.status === "done"
                    ? "line-through text-[var(--muted-foreground)] text-xs"
                    : it.status === "in_progress"
                    ? "text-[var(--foreground)] text-xs font-medium"
                    : "text-[var(--foreground)]/80 text-xs"
                }
              >
                {it.title}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
