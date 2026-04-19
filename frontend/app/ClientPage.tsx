"use client";

import dynamic from "next/dynamic";
import { ThreadProvider } from "@/providers/Thread";

const SyllabusViewerClient = dynamic(
  () => import("../components/SyllabusViewerClient"),
  { ssr: false }
);

export default function ClientPage() {
  return (
    <ThreadProvider refreshInterval={15000}>
      <main className="h-screen w-screen overflow-hidden bg-background text-foreground">
        <SyllabusViewerClient />
      </main>
    </ThreadProvider>
  );
}
