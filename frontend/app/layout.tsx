import type { Metadata } from 'next';
import './globals.css';
import { CopilotKit } from '@copilotkit/react-core';
import '@copilotkit/react-ui/styles.css';

export const metadata: Metadata = {
  title: 'Master PFE \u2014 AI Copilot',
  description: 'CopilotKit v2 + LangGraph + NestJS + NVIDIA NIM',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <CopilotKit runtimeUrl="https://backend-production-47f8.up.railway.app/copilotkit" agent="default">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
