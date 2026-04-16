import { CopilotKit } from '@copilotkit/react-core';
import { CopilotSidebar } from '@copilotkit/react-ui';
import '@copilotkit/react-ui/styles.css';
import { CopilotTools } from '@/components/CopilotTools';
import SyllabusViewerClient from '@/components/SyllabusViewerClient';

/**
 * runtimeUrl always points to the local Next.js proxy route
 * (app/api/copilotkit/[...path]/route.ts) which forwards to the
 * NestJS backend server-side using the BACKEND_URL env var.
 * This avoids any CORS issues and keeps the backend URL private.
 */
export default function SyllabusPage() {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit" agent="syllabus_agent">
      <SyllabusViewerClient />
      <CopilotTools />
      <CopilotSidebar
        defaultOpen
        labels={{
          title: 'Syllabus AI',
          initial:
            "Hello! I can build a complete course syllabus for you.\n\nJust tell me:\n- What subject you want to teach\n- The target audience (beginner / intermediate / advanced)\n- How many chapters/lessons you need\n\nI'll create the full structure with rich lesson content automatically.",
        }}
      />
    </CopilotKit>
  );
}
