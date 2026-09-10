"use client";

import { useQuery } from "@tanstack/react-query";
import {
  orderedLanes,
  taskLifecycle,
  type TaskCompletion,
  type TaskProgress,
} from "@veupathdb/assistant-client";
import { z } from "zod";
import type { BackgroundTaskStarted } from "@pathfinder/shared";

import { THREAD_BLOCK_GAP } from "@/components/ai-elements/rhythm";
import { TaskRow, type TaskOutcome } from "@/features/conversation/thread/TaskRow";
import { useConversationId } from "@/features/conversation/useConversationId";
import { humanizeToolName } from "@/features/conversation/toolNames";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { taskResult } from "../../thread/taskExhibit";

const laneSchema = z.object({ variantId: z.string() });

/** The lane a progress payload names, or null when the task runs one sequence. */
function laneOf(progress: TaskProgress): string | null {
  return laneSchema.safeParse(progress.toolSpecific).data?.variantId ?? null;
}

export function DataBackgroundTaskStarted({ data }: { data: BackgroundTaskStarted }) {
  const conversationId = useConversationId();
  const chat = useChatHelpers();
  const { lanes, completed } = taskLifecycle(chat.messages, data.taskId, { laneOf });

  // A suspended turn closes its own stream, so the task's progress, its outcome
  // and the continuation reach this page only on a fresh tail of the thread.
  useQuery({
    queryKey: ["conversations", conversationId, "tasks", data.taskId, "reattach"],
    queryFn: async () => {
      await chat.resumeStream();
      return data.taskId;
    },
    enabled: completed === null && chat.status === "ready",
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  });

  const tool = humanizeToolName(data.toolName);
  const result =
    completed?.status === "success" ? taskResult(chat.messages, data.taskId) : null;
  const rows = orderedLanes(lanes).map(([lane, progress], index) => (
    <TaskRow
      key={lane ?? "task"}
      label={lane === null ? tool : `${tool} - ${lane}`}
      percent={completed === null ? (progress?.percent ?? null) : 1}
      message={progress?.message ?? null}
      estimatedSeconds={lane === null ? data.estimatedDurationSeconds : null}
      outcome={outcomeOf(completed)}
      error={index === 0 ? (completed?.error ?? null) : null}
      summary={index === 0 ? (result?.summary ?? null) : null}
    />
  ));
  return (
    <div
      data-testid="data-background-task-started"
      className={`flex flex-col ${THREAD_BLOCK_GAP}`}
    >
      {completed === null ? (
        rows
      ) : (
        <div
          data-testid="data-task-completed"
          className={`flex flex-col ${THREAD_BLOCK_GAP}`}
        >
          {rows}
        </div>
      )}
    </div>
  );
}

function outcomeOf(completed: TaskCompletion | null): TaskOutcome {
  if (completed === null) return "running";
  return completed.status === "success" ? "success" : "failure";
}
