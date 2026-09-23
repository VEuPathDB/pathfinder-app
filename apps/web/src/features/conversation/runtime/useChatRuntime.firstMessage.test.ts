/**
 * @vitest-environment jsdom
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";

import { createTestQueryClient } from "@/lib/query/testing";
import { useFirstMessageStore } from "@/state/useFirstMessageStore";
import { useSessionStore } from "@/state/useSessionStore";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "33333333-4444-4555-8666-777777777777";

/** Answer the begin call and open a turn that does not end; count the turns. */
function stubSendFetch(isNew: boolean): { turns: number } {
  const sent = { turns: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) {
        sent.turns += 1;
        return Promise.resolve(
          // The turn stays open, as a first turn does while it builds.
          new Response(new ReadableStream<Uint8Array>(), {
            status: 200,
            headers: {
              "content-type": "text/event-stream",
              "x-vercel-ai-ui-message-stream": "v1",
            },
          }),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew, name: "" }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
      );
    }),
  );
  return sent;
}

async function sendFirstMessage(isNew: boolean): Promise<string[]> {
  const sent = stubSendFetch(isNew);
  const queryClient = createTestQueryClient();
  const listKey = listStrategiesQueryOptions({ siteId: "plasmodb" }).queryKey;
  queryClient.setQueryData(listKey, []);
  const invalidated: string[] = [];
  queryClient.getQueryCache().subscribe((event) => {
    if (event.type === "updated" && event.action.type === "invalidate") {
      invalidated.push(JSON.stringify(event.query.queryKey));
    }
  });
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const { result } = renderHook(
    () => useChatRuntime({ conversationId: CONVERSATION_ID }),
    { wrapper },
  );
  await act(async () => {
    void result.current.chat.sendMessage({ text: "find kinases in the blood stage" });
  });
  await waitFor(() => {
    expect(sent.turns).toBe(1);
  });
  return invalidated.filter((key) => key === JSON.stringify(listKey));
}

beforeEach(() => {
  sessionStorage.clear();
  useSessionStore.setState({ selectedSite: "plasmodb" });
  useFirstMessageStore.setState({ byConversation: {} });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the first message of a thread", () => {
  it("is recorded when it is sent, so the thread has a name to show", async () => {
    await sendFirstMessage(false);

    expect(useFirstMessageStore.getState().byConversation).toEqual({
      [CONVERSATION_ID]: "find kinases in the blood stage",
    });
  });

  it("puts the row a new thread creates into the list before the turn ends", async () => {
    const listInvalidations = await sendFirstMessage(true);

    expect(listInvalidations).toHaveLength(1);
  });
});
