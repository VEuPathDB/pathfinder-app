/**
 * @vitest-environment jsdom
 */
import { listModelsQueryOptions } from "@strategist/shared/generated/hooks/useListModels";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ModelListResponse } from "@strategist/shared/generated/types/ModelListResponse";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ANTHROPIC_SMALL,
  DEFAULT_MODEL,
  OPENAI_FLAGSHIP,
  OPENAI_SMALL,
} from "@/lib/models/__fixtures__/models";
import { useSettingsStore } from "@/state/useSettingsStore";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "44444444-5555-4666-8777-888888888888";

function readBody(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

const TERRA = "openai:gpt-6.1-terra";

const BALANCED = {
  roles: {
    lead: { modelId: DEFAULT_MODEL.id, reasoningEffort: "medium" },
    frame: { modelId: DEFAULT_MODEL.id, reasoningEffort: "medium" },
    execution: { modelId: OPENAI_SMALL.id, reasoningEffort: "medium" },
    verification: { modelId: OPENAI_SMALL.id, reasoningEffort: "high" },
    explore: { modelId: TERRA, reasoningEffort: "medium" },
  },
};

const TIERS = {
  presets: { pathfinder: { openai: { balanced: BALANCED } } },
  ownKeyPresets: { pathfinder: { openai: { balanced: BALANCED } } },
};

const RETIRED = "openai:gpt-6-sol";

const CATALOG: ModelListResponse = {
  models: [OPENAI_SMALL, DEFAULT_MODEL, OPENAI_FLAGSHIP].map((model) => ({
    id: model.id,
    name: model.name,
    modelName: model.modelName,
    provider: "openai",
    rank: "standard",
  })),
  defaultProvider: "openai",
  defaultTier: "balanced",
  phaseDefaults: {},
};

/** Answer the calls a send makes, and record the chat bodies. */
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
      if (url.includes("/api/v1/tiers")) {
        return Promise.resolve(
          new Response(JSON.stringify(TIERS), {
            status: 200,
            headers: { "content-type": "application/json" },
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
  it("sends no stored pick of a model the catalog no longer lists", async () => {
    window.localStorage.setItem(
      "strategist-settings-20260625",
      JSON.stringify({
        state: {
          phaseModels: { lead: RETIRED, frame: DEFAULT_MODEL.id },
          phaseReasoning: { lead: "high", frame: "medium" },
        },
        version: 0,
      }),
    );
    await useSettingsStore.persist.rehydrate();
    const chat = stubSendFetch();

    const client = new QueryClient();
    client.setQueryData(listModelsQueryOptions().queryKey, CATALOG);
    const { result } = renderHook(
      () => useChatRuntime({ conversationId: CONVERSATION_ID }),
      {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    await act(async () => {
      void result.current.chat.sendMessage({ text: "kinases in P. falciparum" });
    });
    await waitFor(() => {
      expect(result.current.chat.status).not.toBe("submitted");
    });

    expect([chat[0]?.["phaseModels"], chat[0]?.["phaseReasoning"]]).toEqual([
      { frame: DEFAULT_MODEL.id },
      { frame: "medium" },
    ]);
    expect(useSettingsStore.getState().phaseModels).toEqual({
      frame: DEFAULT_MODEL.id,
    });
  });

  it("sends no stored pick for the repair role", async () => {
    window.localStorage.setItem(
      "strategist-settings-20260625",
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

  it("gives a tier saved before the explore pick existed that tier's explore model", async () => {
    window.localStorage.setItem(
      "strategist-settings-20260625",
      JSON.stringify({
        state: {
          phaseModels: {
            lead: DEFAULT_MODEL.id,
            frame: DEFAULT_MODEL.id,
            verification: OPENAI_SMALL.id,
          },
          phaseReasoning: { lead: "medium", frame: "medium", verification: "high" },
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

    expect(chat[0]?.["phaseModels"]).toEqual({
      lead: DEFAULT_MODEL.id,
      frame: DEFAULT_MODEL.id,
      verification: OPENAI_SMALL.id,
      explore: TERRA,
    });
    expect(useSettingsStore.getState().phaseModels.explore).toBe(TERRA);
  });
});
