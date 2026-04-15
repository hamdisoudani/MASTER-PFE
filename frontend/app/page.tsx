'use client';

import { useState, useCallback } from 'react';
import { CopilotSidebar } from '@copilotkit/react-ui';
import { useCoAgent, useCoAgentStateRender, useCopilotAction } from '@copilotkit/react-core';
import type { AgentState } from '@/types';
import { PlanView } from '@/components/chat/PlanView';
import styles from './page.module.css';

export default function HomePage(): React.JSX.Element {
  const [notification, setNotification] = useState<string | null>(null);

  const { state: agentState } = useCoAgent<AgentState>({
    name: 'default',
    initialState: { plan: null, mode: 'chat', finished: false },
  });

  useCoAgentStateRender<AgentState>({
    name: 'default',
    render: ({ state }) => {
      if (!state.plan?.length) return null;
      return <PlanView steps={state.plan} />;
    },
  });

  useCopilotAction({
    name: 'show_notification',
    description: 'Show an in-app notification to the user',
    parameters: [{ name: 'message', type: 'string', description: 'The message to display', required: true }],
    handler: async ({ message }: { message: string }) => {
      setNotification(message);
      setTimeout(() => setNotification(null), 4000);
    },
  });

  const dismissNotification = useCallback(() => setNotification(null), []);

  return (
    <div className={styles.container}>
      {notification !== null && (
        <div className={styles.notification} onClick={dismissNotification}>{notification}</div>
      )}
      <main className={styles.main}>
        <section className={styles.hero}>
          <h1 className={styles.title}>Master PFE — AI Assistant</h1>
          <p className={styles.subtitle}>Powered by LangGraph + CopilotKit.</p>
        </section>
        <aside className={styles.statePanel}>
          <h2 className={styles.statePanelTitle}>Agent State</h2>
          <dl className={styles.dl}>
            <dt>Mode</dt><dd>{agentState.mode}</dd>
            <dt>Finished</dt><dd>{agentState.finished ? 'Yes' : 'No'}</dd>
          </dl>
          {agentState.plan !== null && agentState.plan.length > 0 && (
            <><h3 className={styles.planTitle}>Current Plan</h3><PlanView steps={agentState.plan} /></>
          )}
        </aside>
      </main>
      <CopilotSidebar
        defaultOpen
        labels={{ title: 'AI Assistant', initial: 'Hi! How can I help you today?' }}
      />
    </div>
  );
}
