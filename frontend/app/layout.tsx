import type { Metadata } from 'next';
import './globals.css';
import { CopilotKit } from '@copilotkit/react-core';
import '@copilotkit/react-ui/styles.css';

export const metadata: Metadata = {
  title: 'Master PFE — AI Copilot',
  description: 'CopilotKit v2 + LangGraph + NestJS + NVIDIA NIM',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const runtimeUrl = process.env.NEXT_PUBLIC_COPILOT_URL ?? '/api/copilotkit';
  return (
    <html lang="en">
      <body>
        <CopilotKit runtimeUrl={runtimeUrl} agent="default">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
