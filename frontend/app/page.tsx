import { CopilotSidebar } from '@copilotkit/react-ui';
import '@copilotkit/react-ui/styles.css';
import { CopilotTools } from '@/components/CopilotTools';
import SyllabusViewerClient from '@/components/SyllabusViewerClient';

export default function SyllabusPage() {
  return (
    <>
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
    </>
  );
}
