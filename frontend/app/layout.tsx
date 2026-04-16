import type { Metadata } from 'next';
import './globals.css';
import { CopilotKit } from '@copilotkit/react-core';
import '@copilotkit/react-ui/styles.css';

export const metadata: Metadata = {
  title: 'Master PFE — AI Copilot',
  description: 'CopilotKit v2 + LangGraph + NestJS + NVIDIA NIM',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        {/* 
          STRICT RULE — agent name must match across ALL THREE layers:
            1. layout.tsx          → agent="syllabus_agent"  ← here
            2. backend controller  → agents: { syllabus_agent: ... }
            3. agent/main.py       → LangGraphAGUIAgent(name="syllabus_agent")
          See SESSION_NOTES.md for full explanation.
        */}
        <CopilotKit runtimeUrl="https://backend-production-47f8.up.railway.app/copilotkit" agent="syllabus_agent">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
