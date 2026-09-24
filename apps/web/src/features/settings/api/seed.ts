import { buildUrl } from "@/lib/api/http";
import { streamTypedEvents } from "@/lib/sse/typedEventStream";

/**
 * Shape of each decoded event from the `/api/v1/seed` SSE stream.
 *
 * The backend emits typed Pydantic models (``SeedProgress`` / ``SeedStrategyComplete``
 * / ``SeedItemError`` / ``SeedComplete``) - every variant includes a ``message``
 * field, which is all this UI surface needs.
 */
interface SeedStreamEvent {
  type: string;
  message: string;
}

/**
 * Seed demo strategies and control sets via SSE. Calls `onMessage` for each progress event
 * and resolves when the stream emits `[DONE]`.
 */
export async function seedDemoData(
  onMessage: (message: string) => void,
  siteId?: string,
): Promise<void> {
  const params = siteId != null && siteId !== "" ? `?siteId=${siteId}` : "";
  const url = buildUrl(`/api/v1/seed${params}`);

  for await (const event of streamTypedEvents<SeedStreamEvent>(url, {
    method: "POST",
  })) {
    onMessage(event.message);
  }
}
