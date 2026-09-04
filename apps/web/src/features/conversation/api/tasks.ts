import type { TaskListResponse } from "@pathfinder/shared";
import { taskListResponseSchema } from "@pathfinder/shared/generated/zod/taskListResponseSchema";
import { queryOptions } from "@tanstack/react-query";

import { requestJson } from "@/lib/api/http";

const ACTIVE_TASK_STATUSES = new Set(["pending", "running", "resuming"]);

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
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? [];
      const hasActive = tasks.some((t) => ACTIVE_TASK_STATUSES.has(t.status));
      return hasActive ? 3_000 : false;
    },
  });
}
