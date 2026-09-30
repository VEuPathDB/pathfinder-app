/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";

import { server } from "../../../vitest.msw-setup";
import { recordProductEvent } from "./productEvents";

const ROUTE = "http://localhost:3000/api/v1/product-events";
const CONVERSATION_ID = "5f0c6a8e-2d4b-4c1a-9e7f-3b2a1c0d9e8f";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("recordProductEvent", () => {
  it("posts the event as the request body", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(ROUTE, async ({ request }) => {
        bodies.push(await request.json());
        return new HttpResponse(null, { status: 204 });
      }),
    );

    recordProductEvent({
      event: "site_switched",
      fromSite: "plasmodb",
      toSite: "toxodb",
      conversationId: CONVERSATION_ID,
    });

    await vi.waitFor(() => {
      expect(bodies).toEqual([
        {
          event: "site_switched",
          fromSite: "plasmodb",
          toSite: "toxodb",
          conversationId: CONVERSATION_ID,
        },
      ]);
    });
  });

  it("warns and does not throw when the server answers 500", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    server.use(
      http.post(ROUTE, () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );

    expect(() =>
      recordProductEvent({ event: "turn_undone", messageId: "msg-1" }),
    ).not.toThrow();

    await vi.waitFor(() => {
      expect(warn).toHaveBeenCalledWith(
        "recordProductEvent(turn_undone) failed",
        expect.any(Error),
      );
    });
  });
});
