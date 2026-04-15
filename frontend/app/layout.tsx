import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AI Planning Assistant',
  description: 'CopilotKit + LangGraph powered chat',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
