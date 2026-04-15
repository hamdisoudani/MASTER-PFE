'use client';
import { CopilotChat } from '@copilotkit/react-ui';

export default function Home() {
  return (
    <main style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: '100vh', padding: '1rem', background: '#0f172a' }}>
      <h1 style={{ color: '#f1f5f9', marginBottom: '1rem', fontFamily: 'sans-serif', fontSize: '1.5rem' }}>
        Master PFE — AI Copilot
      </h1>
      <div style={{ width: '100%', maxWidth: 720, flex: 1 }}>
        <CopilotChat
          labels={{
            title: 'AI Copilot',
            initial: 'Hi! I\'m your AI assistant powered by Mistral via NVIDIA NIM. How can I help?',
          }}
        />
      </div>
    </main>
  );
}
