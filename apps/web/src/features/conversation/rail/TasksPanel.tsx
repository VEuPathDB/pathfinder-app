"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, Timer } from "lucide-react";
import type { TaskListItem } from "@pathfinder/shared";

import { tasksListOptions } from "@/features/conversation/api/tasks";
import { humanizeToolName } from "@/features/conversation/toolNames";

import { useChatHelpers } from "../runtime/chatHelpersContext";
import { taskResultHref } from "../thread/taskResult";
import { traceRenderingKinds } from "../thread/traceRenderingKinds";
import { RailEmptyState, RailPanelShell } from "./RailPanelShell";

interface TasksPanelProps {
  conversationId: string;
}

const ACTIVE = new Set(["pending", "running", "resuming"]);

export function TasksPanel({ conversationId }: TasksPanelProps) {
  const { data, isLoading } = useQuery(tasksListOptions(conversationId));
  const chat = useChatHelpers();
  const messages = chat.messages;
  const tasks = data?.tasks ?? [];

  return (
    <RailPanelShell title="Tasks">
      {isLoading && tasks.length === 0 ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : tasks.length === 0 ? (
        <RailEmptyState
          icon={<Timer className="h-8 w-8" aria-hidden />}
          heading="No background tasks yet"
          description="Long-running verification jobs (controls, enrichment, parameter optimization) show up here with live progress."
        />
      ) : (
        <ul className="divide-y divide-border">
          {tasks.map((task) => (
            <TaskRow
              key={task.taskId}
              task={task}
              resultHref={taskResultHref(messages, task.taskId, traceRenderingKinds())}
            />
          ))}
        </ul>
      )}
    </RailPanelShell>
  );
}

function TaskRow({
  task,
  resultHref,
}: {
  task: TaskListItem;
  resultHref: string | null;
}) {
  const isActive = ACTIVE.has(task.status);
  const isFailed = task.status === "failed";
  const percent =
    task.latestPercent != null ? Math.round(task.latestPercent * 100) : null;
  return (
    <li className="px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {isActive ? (
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
          ) : isFailed ? (
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />
          )}
          {resultHref === null ? (
            <span className="truncate text-xs font-medium">
              {humanizeToolName(task.toolName)}
            </span>
          ) : (
            <a
              href={resultHref}
              className="truncate text-xs font-medium text-primary underline-offset-2 hover:underline"
            >
              {humanizeToolName(task.toolName)}
            </a>
          )}
        </div>
        <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
          {task.status}
        </span>
      </div>
      {isActive && (
        <div className="mt-2">
          <div className="h-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-500"
              style={{ width: `${percent ?? 0}%` }}
            />
          </div>
          {task.latestMessage != null && task.latestMessage.length > 0 && (
            <p className="mt-1 truncate text-[11px] text-muted-foreground">
              {task.latestMessage}
            </p>
          )}
        </div>
      )}
      {isFailed && task.error != null && task.error.length > 0 && (
        <p className="mt-1 truncate text-[11px] text-destructive">{task.error}</p>
      )}
    </li>
  );
}
