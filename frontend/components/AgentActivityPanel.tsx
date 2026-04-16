"use client";

import { useCoAgentStateRender } from "@copilotkit/react-core";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";

type TaskStatus = "pending" | "in_progress" | "done";

interface PlanTask {
  id: number;
  task: string;
  status: TaskStatus;
}

interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

interface AgentState {
  plan?: PlanTask[] | null;
  search_results?: {
    query: string;
    total: number;
    results: SearchResult[];
    knowledge_panel?: { title: string; description: string };
  } | null;
  scraped_content?: { url: string; title: string; content: string } | null;
  current_activity?: string | null;
}

// ─── Task status icons / styles ───────────────────────────────────────────────

function TaskIcon({ status }: { status: TaskStatus }) {
  if (status === "done") {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-green-500/20 text-green-400 text-[10px] font-bold">
        ✓
      </span>
    );
  }
  if (status === "in_progress") {
    return (
      <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/40" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-primary" />
      </span>
    );
  }
  // pending
  return (
    <span className="h-4 w-4 shrink-0 rounded-full border border-border" />
  );
}

function taskLabelClass(status: TaskStatus): string {
  if (status === "done") return "line-through text-muted-foreground";
  if (status === "in_progress") return "text-foreground font-medium";
  return "text-muted-foreground";
}

// ─── Plan panel ───────────────────────────────────────────────────────────────

function PlanPanel({ plan }: { plan: PlanTask[] }) {
  const doneCount = plan.filter((t) => t.status === "done").length;
  const inProgressCount = plan.filter((t) => t.status === "in_progress").length;
  const pct = plan.length > 0 ? Math.round((doneCount / plan.length) * 100) : 0;

  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-1.5 text-xs">
            <span>📋</span> Plan
            {inProgressCount > 0 && (
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
            )}
          </CardTitle>
          <Badge variant="muted" className="tabular-nums">
            {doneCount}/{plan.length}
          </Badge>
        </div>
        {plan.length > 0 && (
          <Progress value={pct} className="mt-1.5 h-1" />
        )}
      </CardHeader>

      <CardContent className="pt-0">
        <ol className="space-y-2">
          {plan.map((task) => (
            <li key={task.id} className="flex items-start gap-2.5">
              <TaskIcon status={task.status} />
              <span className={`text-xs leading-relaxed ${taskLabelClass(task.status)}`}>
                {task.task}
              </span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

// ─── Search panel ─────────────────────────────────────────────────────────────

function SearchPanel({ data }: { data: NonNullable<AgentState["search_results"]> }) {
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-1.5 text-xs">
            <span>🔍</span> Search Results
          </CardTitle>
          <Badge variant="outline">{data.total}</Badge>
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          &ldquo;{data.query}&rdquo;
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        {data.knowledge_panel?.title && (
          <>
            <div className="mb-2 rounded-md bg-muted p-2.5">
              <p className="text-xs font-semibold mb-0.5">{data.knowledge_panel.title}</p>
              <p className="text-xs text-muted-foreground line-clamp-2">
                {data.knowledge_panel.description}
              </p>
            </div>
            <Separator className="mb-2" />
          </>
        )}
        <ScrollArea className="max-h-40">
          <div className="space-y-2.5 pr-2">
            {data.results.slice(0, 5).map((r, i) => (
              <div key={i}>
                <a
                  href={r.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block text-xs font-medium text-primary hover:underline truncate"
                >
                  {r.title}
                </a>
                <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                  {r.snippet}
                </p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

// ─── Scrape panel ─────────────────────────────────────────────────────────────

function ScrapePanel({ data }: { data: NonNullable<AgentState["scraped_content"]> }) {
  const preview = data.content
    ? data.content.replace(/#+\s/g, "").slice(0, 280).trim() + "…"
    : "No content";
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1.5 text-xs">
          <span>📄</span> Scraped Page
        </CardTitle>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          {data.title || data.url}
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea className="max-h-28">
          <p className="text-xs text-muted-foreground pr-2 leading-relaxed">{preview}</p>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

// ─── Root export ──────────────────────────────────────────────────────────────

export function AgentActivityPanel() {
  useCoAgentStateRender<AgentState>({
    name: "syllabus_agent",
    render: ({ state, status }) => {
      const hasPlan =
        Array.isArray(state?.plan) && (state.plan?.length ?? 0) > 0;
      const hasSearch =
        state?.search_results && (state.search_results?.results?.length ?? 0) > 0;
      const hasScrape = state?.scraped_content?.content;
      const hasActivity = state?.current_activity;

      if (!hasPlan && !hasSearch && !hasScrape && !hasActivity) return null;

      return (
        <div className="p-3 space-y-1">
          {/* Activity line */}
          {hasActivity && (
            <div className="flex items-center gap-2 mb-3">
              {status === "inProgress" && (
                <span className="h-2 w-2 rounded-full bg-primary animate-pulse shrink-0" />
              )}
              <p className="text-xs text-muted-foreground truncate">
                {state.current_activity}
              </p>
            </div>
          )}

          {/* Todo plan */}
          {hasPlan && <PlanPanel plan={state.plan!} />}

          {/* Search results */}
          {hasSearch && <SearchPanel data={state.search_results!} />}

          {/* Scraped content */}
          {hasScrape && <ScrapePanel data={state.scraped_content!} />}
        </div>
      );
    },
  });

  return null;
}
