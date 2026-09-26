import type { APIRequestContext, APIResponse, BrowserContext } from "@playwright/test";
import { request } from "@playwright/test";

/** The header the api's CSRF check requires on every cookie-authenticated write. */
export const CSRF_HEADERS = { "X-Requested-With": "XMLHttpRequest" } as const;

/**
 * A client that asserts server state after UI actions, carrying the context's
 * `pathfinder-auth` and `Authorization` cookies. It never sets anything up.
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

/** The sites `e2e-sites.yaml` serves: the portal and the six component sites. */
export const E2E_SITE_IDS = [
  "veupathdb",
  "plasmodb",
  "toxodb",
  "cryptodb",
  "tritrypdb",
  "fungidb",
  "vectorbase",
] as const;

/** One row of a conversations list. */
export interface ConversationRow {
  id: string;
  siteId: string;
  wdkStrategyId?: number | null;
  isSaved?: boolean;
}

/**
 * The array a list route answers. A problem body fails with its status and
 * detail, so a refused list never reads as an empty or undefined one.
 */
export async function listBody<T>(resp: APIResponse, what: string): Promise<T[]> {
  if (!resp.ok()) {
    throw new Error(`${what} answered ${resp.status()}: ${await resp.text()}`);
  }
  const body: unknown = await resp.json();
  if (!Array.isArray(body)) {
    throw new Error(`${what} answered ${resp.status()}: ${JSON.stringify(body)}`);
  }
  return body as T[];
}

/** The active or dismissed conversations of one site, as its sidebar lists them. */
export async function listConversations(
  api: APIRequestContext,
  siteId: string,
  list: "active" | "dismissed" = "active",
): Promise<ConversationRow[]> {
  const path =
    list === "active" ? "/api/v1/conversations" : "/api/v1/conversations/dismissed";
  const resp = await api.get(`${path}?siteId=${siteId}`);
  return listBody(resp, `${path} on ${siteId}`);
}

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

/** The conversation's messages, rebuilt from its `events/snapshot` chunks. */
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

/** The gene-set list of every site the suite serves, and the unscoped one. */
function geneSetListUrls(baseURL: string): string[] {
  return [
    `${baseURL}/api/v1/gene-sets`,
    ...E2E_SITE_IDS.map((siteId) => `${baseURL}/api/v1/gene-sets?siteId=${siteId}`),
  ];
}

/**
 * Delete every gene set of the calling user, on every site the suite serves.
 * The lists are read one at a time: each holds an api database connection.
 */
async function clearGeneSets(req: APIRequestContext, baseURL: string): Promise<void> {
  for (const url of geneSetListUrls(baseURL)) {
    const geneSets = await listBody<{ id: string }>(await req.get(url), url);
    await Promise.all(
      geneSets.map(async (gs) =>
        deleted(
          await req.delete(`${baseURL}/api/v1/gene-sets/${gs.id}`, {
            headers: CSRF_HEADERS,
          }),
          `gene set ${gs.id}`,
        ),
      ),
    );
  }
}

/**
 * Delete all gene sets for the current user via the API.
 *
 * Uses `page.context().request` so cookies are shared with the browser.
 * Call from `beforeEach` in specs that assert gene-set counts, for test isolation.
 */
export async function clearAllGeneSets(
  context: BrowserContext,
  baseURL: string,
): Promise<void> {
  await clearGeneSets(context.request, baseURL);
}

/** A delete that neither succeeded nor found the row gone fails with its answer. */
async function deleted(resp: APIResponse, what: string): Promise<void> {
  if (resp.ok() || resp.status() === 404) return;
  throw new Error(`deleting ${what} answered ${resp.status()}: ${await resp.text()}`);
}

/**
 * Delete the calling user's gene sets and every conversation, WDK strategies
 * included. A conversation that inserts a saved strategy goes before the saved
 * one, which the api refuses to delete while another conversation uses it.
 */
export async function clearUserData(
  req: APIRequestContext,
  baseURL: string,
): Promise<void> {
  await clearGeneSets(req, baseURL);
  const rows: ConversationRow[] = [];
  for (const path of ["/api/v1/conversations", "/api/v1/conversations/dismissed"]) {
    rows.push(
      ...(await listBody<ConversationRow>(await req.get(`${baseURL}${path}`), path)),
    );
  }
  for (const saved of [false, true]) {
    await Promise.all(
      rows
        .filter((row) => (row.isSaved === true) === saved)
        .map(async (row) =>
          deleted(
            await req.delete(
              `${baseURL}/api/v1/conversations/${row.id}?deleteFromWdk=true`,
              // Each delete also deletes the strategy on the site, which can be slow.
              { headers: CSRF_HEADERS, timeout: 120_000 },
            ),
            `conversation ${row.id}`,
          ),
        ),
    );
  }
}
