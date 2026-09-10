import type { APIRequestContext, BrowserContext } from "@playwright/test";
import { request } from "@playwright/test";

/**
 * `csrf_middleware` rejects a cookie-authenticated request that is not GET,
 * HEAD or OPTIONS and carries no `X-Requested-With`. Every mutating call made
 * outside the app's own fetch layer must send this.
 */
export const CSRF_HEADERS = { "X-Requested-With": "XMLHttpRequest" } as const;

/**
 * Create an authenticated API client for postcondition verification.
 *
 * Takes the browser context's whole storage state, so the client carries both
 * `pathfinder-auth` (PathFinder identity) and `Authorization` (the registered
 * VEuPathDB token every WDK-backed route needs). This client is for ASSERTING
 * server-side state after UI actions, never for setup.
 */
export async function createApiClient(
  context: BrowserContext,
  baseURL: string,
): Promise<APIRequestContext> {
  return request.newContext({
    baseURL,
    storageState: await context.storageState(),
    extraHTTPHeaders: { ...CSRF_HEADERS },
  });
}

export type ApiClient = APIRequestContext;

interface PersistedMessage {
  role: "user" | "assistant";
  content: string;
}

interface SnapshotChunk {
  type: string;
  delta?: string;
  data?: { totalTokens?: number; costUsd?: string };
  message?: { id?: string; role: string; parts?: { type: string; text?: string }[] };
}

/** A turn's whole-turn totals, as the durable event log recorded them. */
export interface TurnUsage {
  totalTokens: number;
  costUsd: string;
}

/**
 * The last turn total the event log holds for a conversation.
 *
 * The API counts every model run of the turn, so this is the number the quota
 * row and the thread's own chip must both read.
 */
export async function fetchLastTurnUsage(
  api: APIRequestContext,
  conversationId: string | null,
): Promise<TurnUsage> {
  if (conversationId == null) throw new Error("no conversation to read usage for");
  const resp = await api.get(`/api/v1/conversations/${conversationId}/events/snapshot`);
  if (!resp.ok()) {
    throw new Error(`events snapshot failed: ${resp.status()}`);
  }
  const { chunks } = (await resp.json()) as { chunks: SnapshotChunk[] };
  const last = chunks.filter((chunk) => chunk.type === "data-turn-usage").at(-1);
  const tokens = last?.data?.totalTokens;
  const cost = last?.data?.costUsd;
  if (tokens === undefined || cost === undefined) {
    throw new Error("the event log carries no turn usage");
  }
  return { totalTokens: tokens, costUsd: cost };
}

/**
 * How many turns of a conversation the worker closed as stopped.
 *
 * The worker writes this chunk only after it reads the turn's cancellation
 * row, so the count is what the row did rather than what Stop asked for.
 */
export async function fetchStoppedTurnCount(
  api: APIRequestContext,
  conversationId: string | null,
): Promise<number> {
  if (conversationId == null) throw new Error("no conversation to read stops for");
  const resp = await api.get(`/api/v1/conversations/${conversationId}/events/snapshot`);
  if (!resp.ok()) {
    throw new Error(`events snapshot failed: ${resp.status()}`);
  }
  const { chunks } = (await resp.json()) as { chunks: SnapshotChunk[] };
  return chunks.filter((chunk) => chunk.type === "data-turn-stopped").length;
}

/**
 * The ids of a conversation's persisted user messages, in order.
 *
 * Revert names a user message, and a fork remints every id it copies, so a
 * spec that reverts inside a branch must read the branch's own ids.
 */
export async function fetchUserMessageIds(
  api: APIRequestContext,
  conversationId: string,
): Promise<string[]> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/events/snapshot`);
  if (!resp.ok()) {
    throw new Error(`events snapshot failed: ${resp.status()}`);
  }
  const { chunks } = (await resp.json()) as { chunks: SnapshotChunk[] };
  return chunks
    .filter((chunk) => chunk.type === "user-message")
    .map((chunk) => chunk.message?.id ?? "")
    .filter((id) => id !== "");
}

/**
 * Reduce a conversation's persisted event snapshot into role-tagged
 * messages. The conversation detail endpoint no longer embeds messages;
 * chat history is reconstructed from the `events/snapshot` chunk stream
 * (user-message chunks + per-turn assistant text-delta chunks).
 */
export async function fetchConversationMessages(
  api: APIRequestContext,
  conversationId: string | null,
): Promise<PersistedMessage[]> {
  if (conversationId == null) return [];
  const resp = await api.get(`/api/v1/conversations/${conversationId}/events/snapshot`);
  if (!resp.ok()) return [];
  const { chunks } = (await resp.json()) as { chunks: SnapshotChunk[] };
  const messages: PersistedMessage[] = [];
  let assistant = "";
  const flush = () => {
    if (assistant !== "") {
      messages.push({ role: "assistant", content: assistant });
      assistant = "";
    }
  };
  for (const chunk of chunks) {
    if (chunk.type === "user-message") {
      flush();
      const text = (chunk.message?.parts ?? [])
        .filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join("");
      messages.push({ role: "user", content: text });
    } else if (chunk.type === "text-delta") {
      assistant += chunk.delta ?? "";
    } else if (chunk.type === "finish") {
      flush();
    }
  }
  flush();
  return messages;
}

/**
 * Delete all gene sets for the current user via the API.
 *
 * Cleans gene sets across all VEuPathDB sites (default + site-specific)
 * to prevent cross-site pollution between tests.
 *
 * Uses `page.context().request` so cookies are shared with the browser.
 * Call from `beforeEach` in workbench/gene-set specs for test isolation.
 */
export async function clearAllGeneSets(
  context: BrowserContext,
  baseURL: string,
): Promise<void> {
  const req = context.request;
  const siteIds = [undefined, "plasmodb", "toxodb", "cryptodb", "fungidb", "tritrypdb"];
  await Promise.all(
    siteIds.map(async (siteId) => {
      const url =
        siteId != null && siteId !== ""
          ? `${baseURL}/api/v1/gene-sets?siteId=${siteId}`
          : `${baseURL}/api/v1/gene-sets`;
      const listResp = await req.get(url);
      if (!listResp.ok()) return;
      const geneSets = (await listResp.json()) as { id: string }[];
      await Promise.all(
        geneSets.map((gs) =>
          req.delete(`${baseURL}/api/v1/gene-sets/${gs.id}`, {
            headers: CSRF_HEADERS,
          }),
        ),
      );
    }),
  );
}
