'use client';

import { useState } from 'react';

interface PlanAccordionProps { steps: string[]; }

export function PlanAccordion({ steps }: PlanAccordionProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  return (
    <div>
      <h2 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">Execution Plan</h2>
      <div className="space-y-2">
        {steps.map((step, i) => {
          const isOpen = openIdx === i;
          const label = step.split(':')[0] ?? `Step ${i + 1}`;
          const detail = step.split(':').slice(1).join(':').trim() || step;
          return (
            <div key={i} className="rounded-lg border border-[var(--border)] overflow-hidden">
              <button onClick={() => setOpenIdx(isOpen ? null : i)}
                className="w-full flex items-center justify-between px-3 py-2 bg-white/5 hover:bg-white/10 text-sm font-medium text-left transition-colors">
                <span className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-[var(--accent)] text-white text-xs flex items-center justify-center flex-shrink-0">{i + 1}</span>
                  <span className="truncate">{label}</span>
                </span>
                <span className="text-[var(--muted)] text-xs">{isOpen ? '▲' : '▼'}</span>
              </button>
              {isOpen && <div className="px-3 py-2 text-xs text-[var(--muted)] bg-white/[0.02] border-t border-[var(--border)]">{detail}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
