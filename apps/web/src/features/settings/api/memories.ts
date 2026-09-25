import type {
  MemoryEditRequest,
  MemoryItem,
  MemoryKind,
  MemoryListResponse,
  MemorySearchResponse,
} from "@pathfinder/shared";
import { memoryItemSchema } from "@pathfinder/shared/generated/zod/memoryItemSchema";
import { memoryListResponseSchema } from "@pathfinder/shared/generated/zod/memoryListResponseSchema";
import { memorySearchResponseSchema } from "@pathfinder/shared/generated/zod/memorySearchResponseSchema";

import { requestJson, requestVoid } from "@/lib/api/http";

const BASE = "/api/v1/memories";

// A memory key is the writer's own string, so it is encoded into the path.
function memoryPath(key: string): string {
  return `${BASE}/${encodeURIComponent(key)}`;
}

export async function listMemories(opts?: {
  limit?: number;
  offset?: number;
}): Promise<MemoryListResponse> {
  return await requestJson(memoryListResponseSchema, BASE, {
    query: { limit: opts?.limit, offset: opts?.offset },
  });
}

export async function searchMemories(query: string): Promise<MemorySearchResponse> {
  return await requestJson(memorySearchResponseSchema, `${BASE}/search`, {
    query: { q: query },
  });
}

export async function editMemory(
  key: string,
  kind: MemoryKind,
  body: MemoryEditRequest,
): Promise<MemoryItem> {
  return await requestJson(memoryItemSchema, memoryPath(key), {
    method: "PATCH",
    query: { kind },
    body,
  });
}

export async function deleteMemory(key: string, kind: MemoryKind): Promise<void> {
  await requestVoid(memoryPath(key), { method: "DELETE", query: { kind } });
}
