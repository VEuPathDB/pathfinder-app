import {
  taskListItemStatusEnum,
  type TaskListItemStatusEnumKey,
} from "@pathfinder/shared/generated/types/TaskListItem";
import { taskListResponseSchema } from "@pathfinder/shared/generated/zod/taskListResponseSchema";
import type { TaskListResponse } from "@pathfinder/shared/generated/types/TaskListResponse";
import { queryOptions } from "@tanstack/react-query";

import { requestJson } from "@/lib/api/http";

/** Every status the runtime writes on a durable task row, as the api publishes it. */
export const TASK_STATUSES = Object.values(taskListItemStatusEnum);

/** A task the worker or its completion turn has not finished with. */
const ACTIVE: Record<TaskListItemStatusEnumKey, boolean> = {
  pending: true,
  running: true,
  result_ready: true,
  resuming: true,
  complete: false,
  failed: false,
};

export function isActiveTask(status: TaskListItemStatusEnumKey): boolean {
  return ACTIVE[status];
}

/** How often the panel reads the list again, or false when nothing is left to wait for. */
export function taskPollInterval(list: TaskListResponse | undefined): number | false {
  const tasks = list?.tasks ?? [];
  return tasks.some((task) => isActiveTask(task.status)) ? 3_000 : false;
}

async function listTasks(conversationId: string): Promise<TaskListResponse> {
  return await requestJson(
    taskListResponseSchema,
    `/api/v1/conversations/${conversationId}/tasks`,
  );
}

export function tasksListOptions(conversationId: string) {
  return queryOptions({
    queryKey: ["conversations", conversationId, "tasks"] as const,
    queryFn: () => listTasks(conversationId),
    refetchInterval: (query) => taskPollInterval(query.state.data),
  });
}
