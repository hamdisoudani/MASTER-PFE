"use client";

import { useCoAgentStateRender } from "@copilotkit/react-core";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

interface PlanTask {
  id: number;
  task: string;
  status: "pending" | "done" | string;
}

interface SearchResult {
  title: string;
  url: string;
  snippet: string;
  position: number;
}

interface AgentState {
  plan?: PlanTask[] | null;
  search_results?: {
    query: string;
    country?: string;
    total: number;
    results: SearchResult[];
    knowledge_panel?: { title: string; description: string };
  } | null;
  scraped_content?: {
    url: string;
    title: string;
    content: string;
  } | null;
  current_activity?: string | null;
}

function PlanPanel({ plan }: { plan: PlanTask[] }) {
  const done = plan.filter((t) => t.status === "done").length;
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-1.5">
            <span>📋</span> Plan
          </CardTitle>
          <Badge variant="muted">
            {done}/{plan.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <ol className="space-y-1.5">
          {plan.map((task) => (
            <li key={task.id} className="flex items-start gap-2 text-xs">
              <span
                className={
                  task.status === "done"
                    ? "mt-0.5 text-green-400 shrink-0"
                    : "mt-0.5 text-muted-foreground shrink-0"
                }
              >
                {task.status === "done" ? "✓" : `${task.id + 1}.`}
              </span>
              <span
                className={
                  task.status === "done"
                    ? "line-through text-muted-foreground"
                    : "text-foreground"
                }
              >
                {task.task}
              </span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function SearchPanel({
  data,
}: {
  data: NonNullable<AgentState["search_results"]>;
}) {
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-1.5">
            <span>🔍</span> Search Results
          </CardTitle>
          <Badge variant="outline">{data.total} results</Badge>
        </div>
        <p className="text-xs text-muted-foreground truncate">&ldquo;{data.query}&rdquo;</p>
      </CardHeader>
      <CardContent>
        {data.knowledge_panel?.title && (
          <>
            <div className="mb-2 rounded-md bg-muted p-2.5">
              <p className="text-xs font-semibold text-secondary mb-0.5">
                {data.knowledge_panel.title}
              </p>
              <p className="text-xs text-muted-foreground line-clamp-2">
                {data.knowledge_panel.description}
              </p>
            </div>
            <Separator className="mb-2" />
          </>
        )}
        <ScrollArea className="max-h-48">
          <div className="space-y-2.5 pr-2">
            {data.results.slice(0, 5).map((r, i) => (
              <div key={i} className="group">
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

function ScrapePanel({
  data,
}: {
  data: NonNullable<AgentState["scraped_content"]>;
}) {
  const preview = data.content
    ? data.content.replace(/#+\s/g, "").slice(0, 300).trim() + "…"
    : "No content";
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1.5">
          <span>📄</span> Scraped Page
        </CardTitle>
        <p className="text-xs text-muted-foreground truncate">{data.title || data.url}</p>
      </CardHeader>
      <CardContent>
        <ScrollArea className="max-h-32">
          <p className="text-xs text-muted-foreground pr-2 leading-relaxed">{preview}</p>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

export function AgentActivityPanel() {
  useCoAgentStateRender<AgentState>({
    name: "syllabus_agent",
    render: ({ state, status }) => {
      const hasPlan = Array.isArray(state?.plan) && (state.plan?.length ?? 0) > 0;
      const hasSearch = state?.search_results && (state.search_results?.results?.length ?? 0) > 0;
      const hasScrape = state?.scraped_content && state.scraped_content?.content;
      const hasActivity = state?.current_activity;

      if (!hasPlan && !hasSearch && !hasScrape && !hasActivity) return null;

      return (
        <div className="p-3 space-y-1">
          {hasActivity && (
            <div className="flex items-center gap-2 mb-3">
              {status === "inProgress" && (
                <span className="inline-block h-2 w-2 rounded-full bg-primary animate-pulse shrink-0" />
              )}
              <p className="text-xs text-muted-foreground truncate">{state.current_activity}</p>
            </div>
          )}
          {hasPlan && <PlanPanel plan={state.plan!} />}
          {hasSearch && <SearchPanel data={state.search_results!} />}
          {hasScrape && <ScrapePanel data={state.scraped_content!} />}
        </div>
      );
    },
  });

  return null;
}
