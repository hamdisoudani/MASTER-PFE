import dynamic from 'next/dynamic';

const SyllabusViewerClient = dynamic(
  () => import('../components/SyllabusViewerClient'),
  { ssr: false }
);

const CopilotTools = dynamic(
  () => import('../components/CopilotTools').then(m => ({ default: m.CopilotTools })),
  { ssr: false }
);

export default function Home() {
  return (
    <main>
      <CopilotTools />
      <SyllabusViewerClient />
    </main>
  );
}
