'use client';
import { CopilotChat } from '@copilotkit/react-ui';
import '@copilotkit/react-ui/styles.css';

export default function Home() {
  return (
    <div className="flex flex-col h-screen">
      {/* Subtle gradient orb background */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute top-[-20%] left-[-10%] w-[60vw] h-[60vw] rounded-full bg-[#f66e60]/[0.04] blur-[120px]" />
        <div className="absolute bottom-[-15%] right-[-10%] w-[50vw] h-[50vw] rounded-full bg-[#fcaf41]/[0.03] blur-[120px]" />
      </div>

      {/* Top bar */}
      <header className="flex items-center justify-between px-4 md:px-6 h-14 border-b border-[var(--border)] bg-[var(--background)]/80 backdrop-blur-sm shrink-0 z-10">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-semibold text-[var(--foreground)] tracking-tight">
            Master PFE
          </h1>
          <div className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border border-[var(--border)] bg-[var(--muted)]/40 text-[10px] font-medium text-[var(--muted-foreground)] tracking-wide uppercase">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--primary)] animate-pulse" />
            Mistral × NVIDIA NIM
          </div>
        </div>
        <span className="text-xs text-[var(--muted-foreground)]/40">
          CopilotKit · LangGraph · NestJS
        </span>
      </header>

      {/* Chat fills remaining space */}
      <main className="flex-1 min-h-0">
        <CopilotChat
          labels={{
            title: 'AI Copilot',
            initial: "👋 Hello! I'm your AI assistant powered by Mistral via NVIDIA NIM. How can I help you today?",
          }}
          className="h-full"
        />
      </main>
    </div>
  );
}