/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

const DRAFT_PATH = "/plasmodb/conversation";

let pathname = DRAFT_PATH;

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

import { server } from "../../../vitest.msw-setup";
import { createTestWrapper } from "@/lib/query/testing";
import { DEFAULT_ASSISTANT_ID } from "@/lib/assistants";
import { useSessionStore } from "@/state/useSessionStore";

import { useActiveAssistantId } from "./useActiveAssistantId";

const CONVERSATION_ID = "44444444-4444-4444-8444-444444444444";
const BASE = `http://localhost:3000/api/v1/conversations/${CONVERSATION_ID}`;

function recordReads(): string[] {
  const seen: string[] = [];
  server.use(
    http.get("http://localhost:3000/api/v1/conversations/", () => {
      seen.push("collection");
      return HttpResponse.json([]);
    }),
    http.get(BASE, () => {
      seen.push("detail");
      return HttpResponse.json({
        id: CONVERSATION_ID,
        name: "strategy",
        siteId: "plasmodb",
        assistantId: "site_help",
        steps: [],
        rootStepId: null,
        recordType: null,
        isSaved: false,
        createdAt: "2026-09-12T00:00:00Z",
        updatedAt: "2026-09-12T00:00:00Z",
      });
    }),
  );
  return seen;
}

afterEach(() => {
  useSessionStore.setState({ createdConversationId: null });
  pathname = DRAFT_PATH;
});

describe("useActiveAssistantId", () => {
  it("reads no conversation while the route names one that has no row", async () => {
    const seen = recordReads();
    const { Wrapper } = createTestWrapper();

    const { rerender, result } = renderHook(() => useActiveAssistantId(), {
      wrapper: Wrapper,
    });
    pathname = `/plasmodb/conversation/${CONVERSATION_ID}`;
    rerender();

    await waitFor(() => {
      expect(result.current).toBe(DEFAULT_ASSISTANT_ID);
    });
    expect(seen).toEqual([]);
  });

  it("reads nothing after the route leaves the conversation it opened on", async () => {
    pathname = `/plasmodb/conversation/${CONVERSATION_ID}`;
    const seen = recordReads();
    const { Wrapper } = createTestWrapper();

    const { rerender, result } = renderHook(() => useActiveAssistantId(), {
      wrapper: Wrapper,
    });
    await waitFor(() => {
      expect(result.current).toBe("site_help");
    });
    pathname = DRAFT_PATH;
    rerender();

    await waitFor(() => {
      expect(result.current).toBe(DEFAULT_ASSISTANT_ID);
    });
    expect(seen).toEqual(["detail"]);
  });

  it("reads the conversation the route opened on", async () => {
    pathname = `/plasmodb/conversation/${CONVERSATION_ID}`;
    const seen = recordReads();
    const { Wrapper } = createTestWrapper();

    const { result } = renderHook(() => useActiveAssistantId(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current).toBe("site_help");
    });
    expect(seen).toEqual(["detail"]);
  });
});
