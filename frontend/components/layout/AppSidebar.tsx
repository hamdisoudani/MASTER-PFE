"use client";
import * as React from "react";
import { Sidebar, SidebarContent, SidebarHeader, SidebarFooter } from "@/components/ui/sidebar";
import { ThreadHistory } from "@/components/chat/ThreadHistory";

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="border-b border-[var(--sidebar-border)] px-3 py-2 group-data-[collapsible=icon]:hidden">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <span className="text-[var(--primary)]">Master PFE</span>
          <span className="text-xs text-[var(--muted-foreground)]">· Syllabus Agent</span>
        </div>
      </SidebarHeader>
      <SidebarContent className="p-0 group-data-[collapsible=icon]:hidden">
        <ThreadHistory />
      </SidebarContent>
      <SidebarFooter className="border-t border-[var(--sidebar-border)] px-3 py-2 text-[10px] text-[var(--muted-foreground)] group-data-[collapsible=icon]:hidden">
        Press <kbd className="rounded border border-[var(--border)] px-1">⌘/Ctrl + B</kbd> to toggle
      </SidebarFooter>
    </Sidebar>
  );
}
