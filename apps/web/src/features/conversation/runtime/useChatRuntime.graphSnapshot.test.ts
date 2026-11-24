/**
 * @vitest-environment jsdom
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useLeftSidebarStore,
  useRightRailStore,
  useSideOrderStore,
} from "@/state/useRightRailStore";

import { LeftSidebarDrawn } from "@/state/useDockLayout";

import { useChatRuntime } from "./useChatRuntime";

const CONVERSATION_ID = "88888888-9999-4aaa-8bbb-cccccccccccc";
const TURN_MESSAGE_ID = "99999999-aaaa-4bbb-8ccc-dddddddddddd";

function frame(eventId: number, payload: unknown): string {
  return `id: ${String(eventId)}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function buildTurn(): Response {
  const body = [
    frame(1, { type: "start", messageId: TURN_MESSAGE_ID }),
    frame(2, {
      type: "data-graph-snapshot",
      data: {
        strategyId: "s1",
        geneCount: 797,
        detachedStepCount: 0,
        nodes: [
          { id: "1", searchName: "GroupsByPhyleticPattern", estimatedSize: 797 },
          { id: "2", searchName: "GroupsBySingleCopy", estimatedSize: 4000 },
        ],
        edges: [],
      },
    }),
    frame(3, { type: "finish", finishReason: "stop" }),
    `id: 4\ndata: [DONE]\n\n`,
  ].join("");
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}

beforeEach(() => {
  useRightRailStore.setState({ openPanel: null, lastSeen: {} });
  useLeftSidebarStore.setState({ collapsed: false, width: 360 });
  useSideOrderStore.setState({ lastOpened: "left" });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/v1/chat")) return Promise.resolve(buildTurn());
      return Promise.resolve(
        new Response(
          JSON.stringify({ conversationId: CONVERSATION_ID, isNew: false, name: "" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function inShell({ children }: { children: ReactNode }) {
  return createElement(LeftSidebarDrawn, { value: true }, children);
}

async function sendBuildTurn(): Promise<void> {
  const { result } = renderHook(
    () => useChatRuntime({ conversationId: CONVERSATION_ID }),
    { wrapper: inShell },
  );
  await act(async () => {
    await result.current.chat.sendMessage({ text: "Build it." });
  });
  await waitFor(() => {
    expect(
      result.current.chat.messages.flatMap((m) => m.parts.map((p) => p.type)),
    ).toContain("data-graph-snapshot");
  });
}

describe("useChatRuntime, a graph snapshot", () => {
  it("opens the strategy panel on the steps the snapshot carries", async () => {
    window.innerWidth = 1600;
    await sendBuildTurn();

    await waitFor(() => {
      expect(useRightRailStore.getState().openPanel).toBe("strategy");
    });
    expect(useRightRailStore.getState().lastSeen[CONVERSATION_ID]).toMatchObject({
      strategyStepCount: 2,
    });
  });

  it("leaves the rail closed when the panel would float over the chat", async () => {
    window.innerWidth = 1280;
    await sendBuildTurn();

    expect(useRightRailStore.getState()).toMatchObject({
      openPanel: null,
      lastSeen: {},
    });
  });
});
