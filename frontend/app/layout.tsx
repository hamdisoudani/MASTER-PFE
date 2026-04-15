import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { CopilotKit } from '@copilotkit/react-core';
import '@copilotkit/react-ui/styles.css';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Master PFE — AI Assistant',
  description: 'LangGraph-powered AI assistant built with CopilotKit',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>): React.JSX.Element {
  return (
    <html lang="en">
      <body className={inter.className}>
        <CopilotKit
          runtimeUrl="/api/copilotkit"
          agent="default"
          showDevConsole={process.env.NODE_ENV === 'development'}
        >
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
