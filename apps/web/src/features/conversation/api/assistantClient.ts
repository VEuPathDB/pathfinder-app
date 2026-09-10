import { AssistantClient, webStorageCursorStore } from "@veupathdb/assistant-client";

import {
  APIError,
  buildUrl,
  extractErrorMessage,
  getAuthHeaders,
  parseResponseBody,
} from "@/lib/api/http";

/** The status the protocol uses for a thread with no turn in flight. */
const NO_TURN_IN_FLIGHT = 204;

/** Reads the assistant runtime, and raises the app's refusal with the server's sentence. */
async function assistantFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const url = input instanceof Request ? input.url : String(input);
  const response = await fetch(input, { ...init, credentials: "include" });
  if (response.ok || response.status === NO_TURN_IN_FLIGHT) return response;
  const data = await parseResponseBody(response);
  const message =
    extractErrorMessage(data) ?? `HTTP ${response.status} ${response.statusText}`;
  throw new APIError(message, {
    status: response.status,
    statusText: response.statusText,
    url,
    data,
  });
}

/**
 * The resume point of every thread. The snapshot read and the streaming
 * transport share this store, so neither can rewind the other.
 */
export const conversationCursors = webStorageCursorStore();

export const assistantClient = new AssistantClient({
  eventsUrlFor: (conversationId) =>
    buildUrl(`/api/v1/conversations/${conversationId}/events`),
  snapshotUrlFor: (conversationId) =>
    buildUrl(`/api/v1/conversations/${conversationId}/events/snapshot`),
  headers: () => getAuthHeaders(),
  fetch: assistantFetch,
  cursors: conversationCursors,
});
