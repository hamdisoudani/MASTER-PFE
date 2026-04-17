/**
 * page.tsx — root shell
 *
 * SyllabusViewerClient owns the full 3-panel resizable layout:
 *   [FileTree] | [BlockNote editor] | [Chat]
 *
 * CopilotTools is mounted invisibly here to register all
 * useCopilotAction hooks and useAgentContext with CopilotKit.
 */
'use client';

import { CopilotTools } from '@/components/CopilotTools';
import SyllabusViewerClient from '@/components/SyllabusViewerClient';

export default function SyllabusPage() {
  return (
    <div className="h-screen w-screen overflow-hidden bg-[var(--bg)] text-[var(--text)]">
      <SyllabusViewerClient />
      <CopilotTools />
    </div>
  );
}
