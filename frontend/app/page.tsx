'use client';
import { CopilotChat } from '@copilotkit/react-ui';
import '@copilotkit/react-ui/styles.css';

export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8">
      {/* Subtle gradient orb background */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute top-[-20%] left-[-10%] w-[60vw] h-[60vw] rounded-full bg-[#f66e60]/[0.06] blur-[120px]" />
        <div className="absolute bottom-[-15%] right-[-10%] w-[50vw] h-[50vw] rounded-full bg-[#fcaf41]/[0.05] blur-[120px]" />
      </div>

      {/* Header */}
      <div className="text-center mb-6 md:mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 mb-4 rounded-full border border-[var(--border)] bg-[var(--muted)]/50 text-xs font-medium text-[var(--muted-foreground)] tracking-wide uppercase">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--primary)] animate-pulse" />
          Powered by Mistral × NVIDIA NIM
        </div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-[var(--foreground)]">
          Master PFE
        </h1>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          Your AI-powered research &amp; planning assistant
        </p>
      </div>

      {/* Chat container */}
      <div className="w-full max-w-2xl flex-1 min-h-0" style={{ maxHeight: 'calc(100vh - 200px)' }}>
        <CopilotChat
          labels={{
            title: 'AI Copilot',
            initial: "\ud83d\udc4b Hello! I'm your AI assistant powered by Mistral via NVIDIA NIM. How can I help you today?",
          }}
          className="h-full"
        />
      </div>

      {/* Footer */}
      <div className="mt-4 text-xs text-[var(--muted-foreground)]/60">
        Built with CopilotKit · LangGraph · NestJS
      </div>
    </main>
  );
}