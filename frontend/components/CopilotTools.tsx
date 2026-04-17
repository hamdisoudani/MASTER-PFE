"use client";

import { useCopilotAction } from "@copilotkit/react-core";
import { useCopilotReadable } from "@copilotkit/react-core";
import { useSyllabusStore, Block } from "@/store/syllabusStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";

// ─── Status indicator ─────────────────────────────────────────────────────────
function StatusDot({ status }: { status: "pending" | "in_progress" | "done" }) {
  const colors = {
    pending: "bg-gray-400",
    in_progress: "bg-yellow-400 animate-pulse",
    done: "bg-green-400",
  };
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${colors[status]}`}
    />
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function CopilotTools() {
  const {
    blocks,
    setBlocks,
    addBlock,
    updateBlock,
    removeBlock,
    tasks,
    setTasks,
    updateTask,
    syllabus,
    setSyllabus,
    agentActivity,
    setAgentActivity,
  } = useSyllabusStore();

  // ── Readable context ────────────────────────────────────────────────────────
  useCopilotReadable({
    description: "The current syllabus blocks that the user is building",
    value: blocks,
  });

  useCopilotReadable({
    description: "The current agent task plan and their statuses",
    value: tasks,
  });

  useCopilotReadable({
    description: "The current full syllabus markdown text",
    value: syllabus,
  });

  // ── Actions ─────────────────────────────────────────────────────────────────

  useCopilotAction({
    name: "plan_tasks",
    description: "Create a plan with a list of task descriptions",
    parameters: [
      {
        name: "tasks",
        type: "object[]",
        description: "List of task objects with id, description, and status",
        attributes: [
          { name: "id", type: "number", description: "Task id" },
          { name: "description", type: "string", description: "Task description" },
          { name: "status", type: "string", description: "pending | in_progress | done" },
        ],
      },
    ],
    handler: ({ tasks: newTasks }) => {
      setTasks(newTasks as any);
    },
  });

  useCopilotAction({
    name: "update_plan_task",
    description: "Update the status of a plan task",
    parameters: [
      { name: "task_id", type: "number", description: "Task id to update" },
      { name: "status", type: "string", description: "New status: pending | in_progress | done" },
    ],
    handler: ({ task_id, status }) => {
      updateTask(task_id as number, status as "pending" | "in_progress" | "done");
    },
  });

  useCopilotAction({
    name: "set_syllabus_blocks",
    description: "Replace the entire list of syllabus blocks shown to the user",
    parameters: [
      {
        name: "blocks",
        type: "object[]",
        description: "Array of syllabus block objects",
        attributes: [
          { name: "id", type: "string", description: "Unique block id" },
          { name: "type", type: "string", description: "Block type: week | module | objective | resource | assessment" },
          { name: "title", type: "string", description: "Block title" },
          { name: "content", type: "string", description: "Block content or description" },
          { name: "order", type: "number", description: "Display order" },
        ],
      },
    ],
    handler: ({ blocks: newBlocks }) => {
      setBlocks(newBlocks as Block[]);
    },
  });

  useCopilotAction({
    name: "add_syllabus_block",
    description: "Add a single new block to the syllabus",
    parameters: [
      { name: "id", type: "string", description: "Unique block id" },
      { name: "type", type: "string", description: "Block type" },
      { name: "title", type: "string", description: "Block title" },
      { name: "content", type: "string", description: "Block content" },
      { name: "order", type: "number", description: "Display order" },
    ],
    handler: (block) => {
      addBlock(block as Block);
    },
  });

  useCopilotAction({
    name: "update_syllabus_block",
    description: "Update fields on an existing syllabus block",
    parameters: [
      { name: "id", type: "string", description: "Block id to update" },
      { name: "title", type: "string", description: "New title", required: false },
      { name: "content", type: "string", description: "New content", required: false },
      { name: "type", type: "string", description: "New type", required: false },
    ],
    handler: ({ id, ...updates }) => {
      updateBlock(id as string, updates as Partial<Block>);
    },
  });

  useCopilotAction({
    name: "remove_syllabus_block",
    description: "Remove a syllabus block by id",
    parameters: [
      { name: "id", type: "string", description: "Block id to remove" },
    ],
    handler: ({ id }) => {
      removeBlock(id as string);
    },
  });

  useCopilotAction({
    name: "set_syllabus_text",
    description: "Set the full rendered syllabus markdown text",
    parameters: [
      { name: "text", type: "string", description: "Full syllabus markdown" },
    ],
    handler: ({ text }) => {
      setSyllabus(text as string);
    },
  });

  useCopilotAction({
    name: "set_agent_activity",
    description: "Update the agent activity log shown in the UI",
    parameters: [
      { name: "activity", type: "string", description: "Current agent activity description" },
    ],
    handler: ({ activity }) => {
      setAgentActivity(activity as string);
    },
  });

  // ── Render: task panel only (blocks shown in SyllabusViewer) ────────────────
  if (tasks.length === 0 && !agentActivity) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-80 space-y-2">
      {agentActivity && (
        <AgentActivityPanel activity={agentActivity} />
      )}

      {tasks.length > 0 && (
        <Card className="bg-[#111] border border-white/10 shadow-xl">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-semibold text-white/50 uppercase tracking-wider">
              Agent Plan
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-1.5">
            {tasks.map((task) => (
              <div key={task.id} className="flex items-center gap-2 text-sm">
                <StatusDot status={task.status} />
                <span
                  className={`flex-1 ${
                    task.status === "done" ? "line-through text-white/30" : "text-white/80"
                  }`}
                >
                  {task.description}
                </span>
                <Badge
                  variant="outline"
                  className="text-[10px] px-1.5 py-0 border-white/10 text-white/40"
                >
                  {task.status}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
