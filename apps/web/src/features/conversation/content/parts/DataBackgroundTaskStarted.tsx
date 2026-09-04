"use client";

import { useQuery } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import { z } from "zod";
import type {
  BackgroundTaskStarted,
  TaskCompleted,
  TaskProgressChunk,
} from "@pathfinder/shared";
import { taskCompletedSchema } from "@pathfinder/shared/generated/zod/taskCompletedSchema";
import { taskProgressSchema } from "@pathfinder/shared/generated/zod/taskProgressSchema";

import { THREAD_BLOCK_GAP } from "@/components/ai-elements/rhythm";
import { TaskRow, type TaskOutcome } from "@/features/conversation/thread/TaskRow";
import { useConversationId } from "@/features/conversation/useConversationId";
import { humanizeToolName } from "@/features/conversation/toolNames";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { taskResultHref } from "../../thread/taskResult";
import { traceRenderingKinds } from "../../thread/traceRenderingKinds";

const laneSchema = z.object({ variantId: z.string() });

type Lane = readonly [string | null, TaskProgressChunk | null];

interface TaskLifecycle {
  lanes: Map<string | null, TaskProgressChunk>;
  completed: TaskCompleted | null;
}

/** The lane a progress payload names, or null when the task runs one sequence. */
function laneOf(progress: TaskProgressChunk): string | null {
  return laneSchema.safeParse(progress.toolSpecific).data?.variantId ?? null;
}

/**
 * Read one task's progress and outcome from the thread's own parts. The log
 * carries both on the message that started the task, so the card survives a
 * reload with no subscription. A fan-out reports one lane per variant, and
 * each lane keeps its own newest update.
 */
function collectTaskLifecycle(
  messages: readonly UIMessage[],
  taskId: string,
): TaskLifecycle {
  const lifecycle: TaskLifecycle = { lanes: new Map(), completed: null };
  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type === "data-task-progress") {
        const parsed = taskProgressSchema.safeParse(part.data);
        if (parsed.success && parsed.data.taskId === taskId) {
          lifecycle.lanes.set(laneOf(parsed.data), parsed.data);
        }
      } else if (part.type === "data-task-completed") {
        const parsed = taskCompletedSchema.safeParse(part.data);
        if (parsed.success && parsed.data.taskId === taskId) {
          lifecycle.completed = parsed.data;
        }
      }
    }
  }
  return lifecycle;
}

function orderedLanes(lanes: Map<string | null, TaskProgressChunk>): readonly Lane[] {
  const ordered: Lane[] = [...lanes.entries()].sort(([left], [right]) =>
    (left ?? "").localeCompare(right ?? ""),
  );
  return ordered.length > 0 ? ordered : [[null, null]];
}

export function DataBackgroundTaskStarted({ data }: { data: BackgroundTaskStarted }) {
  const conversationId = useConversationId();
  const chat = useChatHelpers();
  const { lanes, completed } = collectTaskLifecycle(chat.messages, data.taskId);

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
  const resultHref =
    completed?.status === "success"
      ? taskResultHref(chat.messages, data.taskId, traceRenderingKinds())
      : null;
  const rows = orderedLanes(lanes).map(([lane, progress], index) => (
    <TaskRow
      key={lane ?? "task"}
      label={lane === null ? tool : `${tool} - ${lane}`}
      percent={completed === null ? (progress?.percent ?? null) : 1}
      message={progress?.message ?? null}
      estimatedSeconds={lane === null ? data.estimatedDurationSeconds : null}
      outcome={outcomeOf(completed)}
      error={index === 0 ? (completed?.error ?? null) : null}
      resultHref={index === 0 ? resultHref : null}
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

function outcomeOf(completed: TaskCompleted | null): TaskOutcome {
  if (completed === null) return "running";
  return completed.status === "success" ? "success" : "failure";
}
