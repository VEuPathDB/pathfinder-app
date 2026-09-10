/**
 * Fetch and auth for the typed-event SSE dialect used by the experiment,
 * sweep and seed routes. The frame reading is the client package's legacy
 * reader; a conversation and its durable tasks use the wire protocol instead.
 */

import { readTypedEvents } from "@veupathdb/assistant-client/legacy";

import {
  APIError,
  extractErrorMessage,
  getAuthHeaders,
  parseResponseBody,
} from "@/lib/api/http";

export interface TypedEventStreamOptions {
  /** Abort signal forwarded to `fetch` and the body reader. */
  signal?: AbortSignal;
  /** HTTP method. Defaults to `"GET"`. */
  method?: "GET" | "POST";
  /**
   * Optional request body. When set, it is JSON-stringified and the
   * `Content-Type: application/json` header is added automatically.
   */
  body?: unknown;
}

export async function* streamTypedEvents<T>(
  url: string,
  options: TypedEventStreamOptions = {},
): AsyncGenerator<T> {
  const { signal, method = "GET", body } = options;
  const hasBody = body !== undefined;

  const init: RequestInit = {
    method,
    credentials: "include",
    headers: getAuthHeaders({
      accept: "text/event-stream",
      ...(hasBody ? { contentType: "application/json" } : {}),
    }),
  };
  if (hasBody) init.body = JSON.stringify(body);
  if (signal !== undefined) init.signal = signal;

  const resp = await fetch(url, init);

  if (!resp.ok) {
    const data = await parseResponseBody(resp);
    const message =
      extractErrorMessage(data) ?? `HTTP ${resp.status} ${resp.statusText}`;
    throw new APIError(message, {
      status: resp.status,
      statusText: resp.statusText,
      url,
      data,
    });
  }
  const respBody = resp.body;
  if (respBody === null) throw new Error("no response body");

  yield* readTypedEvents<T>(respBody);
}
