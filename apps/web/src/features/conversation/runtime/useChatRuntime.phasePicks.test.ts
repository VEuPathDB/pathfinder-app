/**
 * @vitest-environment jsdom
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ANTHROPIC_SMALL, OPENAI_FLAGSHIP } from "@/lib/models/__fixtures__/models";
import { useSettingsStore } from "@/state/useSettingsStore";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "44444444-5555-4666-8777-888888888888";

function readBody(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

/** Answer both calls a send makes, and record the chat bodies. */
function stubSendFetch(): Record<string, unknown>[] {
  const chat: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) {
        chat.push(readBody(init));
        return Promise.resolve(
          new Response(new ReadableStream<Uint8Array>({ start: (c) => c.close() }), {
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
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew: false, name: "" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
  return chat;
}

beforeEach(() => {
  sessionStorage.clear();
  useSettingsStore.getState().resetToDefaults();
});

describe("the phase picks a turn carries", () => {
  it("sends no stored pick for the repair role", async () => {
    window.localStorage.setItem(
      "pathfinder-settings-20260625",
      JSON.stringify({
        state: {
          phaseModels: { lead: OPENAI_FLAGSHIP.id, execution: ANTHROPIC_SMALL.id },
          phaseReasoning: { lead: "high", execution: "low" },
        },
        version: 0,
      }),
    );
    await useSettingsStore.persist.rehydrate();
    const chat = stubSendFetch();

    const { result } = renderHook(() =>
      useChatRuntime({ conversationId: CONVERSATION_ID }),
    );
    await act(async () => {
      void result.current.chat.sendMessage({ text: "kinases in P. falciparum" });
    });
    await waitFor(() => {
      expect(result.current.chat.status).not.toBe("submitted");
    });

    expect(chat[0]?.["phaseModels"]).toEqual({ lead: OPENAI_FLAGSHIP.id });
    expect(chat[0]?.["phaseReasoning"]).toEqual({ lead: "high" });
  });
});
