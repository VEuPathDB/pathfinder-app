/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { UIMessage } from "ai";
import type { QuotaResponse } from "@pathfinder/shared/generated/types/QuotaResponse";

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";

import { server } from "../../../../vitest.msw-setup";
import { ChatHelpersProvider } from "../runtime/chatHelpersContext";
import type { ChatHelpers } from "../runtime/chatHelpersContext";
import { SpendRing, ringTone } from "./SpendRing";

const QUOTA: QuotaResponse = {
  usedUsd: "1.25",
  limitUsd: "10.00",
  totalTokens: 123456,
  percent: 12.5,
  resetsAt: "2026-12-01T12:00:00Z",
  ownKeyUsd: "0",
  ownKeyTokens: 0,
  ownKeyProviders: [],
};

const USAGE: UIMessage[] = [
  {
    id: "m1",
    role: "assistant",
    parts: [
      {
        type: "data-lead-usage",
        data: { tokens: 1000, costUsd: "0.01", modelId: "openai:gpt" },
      },
      {
        type: "data-sub-agent-call",
        id: "c1",
        data: { tokens: 2000, costUsd: "0.02" },
      },
    ],
  },
];

const quotaReads: string[] = [];

beforeEach(() => {
  quotaReads.length = 0;
});

function renderRing({
  quota = {},
  signedIn = true,
  messages = USAGE,
}: {
  quota?: Partial<QuotaResponse>;
  signedIn?: boolean;
  messages?: UIMessage[];
} = {}) {
  server.use(
    http.get("http://localhost:3000/pathfinder/api/v1/me/quota", ({ request }) => {
      quotaReads.push(request.url);
      return HttpResponse.json({ ...QUOTA, ...quota });
    }),
  );
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    authStatusOptions(useSessionStore.getState().selectedSite).queryKey,
    { signedIn },
  );
  const chat: ChatHelpers = {
    id: "test-conversation",
    messages,
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
  return render(
    <ChatHelpersProvider value={chat}>
      <SpendRing />
    </ChatHelpersProvider>,
    { wrapper: Wrapper },
  );
}

async function openFigures(): Promise<HTMLElement> {
  await userEvent.hover(await screen.findByTestId("spend-ring"));
  return await screen.findByRole("tooltip");
}

describe("ringTone", () => {
  it.each([
    [0.5, "text-primary"],
    [0.8, "text-warning"],
    [1, "text-destructive"],
  ])("tones %s as %s", (share, tone) => {
    expect(ringTone(share)).toBe(tone);
  });
});

describe("SpendRing", () => {
  it("fills to the share of the monthly allowance spent", async () => {
    renderRing();
    await waitFor(() =>
      expect(screen.getByTestId("spend-ring")).toHaveAccessibleName(
        "Monthly spend 13% of allowance",
      ),
    );
    expect(screen.getByTestId("spend-ring")).toHaveTextContent("13%");
    expect(screen.getByTestId("spend-ring")).toHaveClass("text-primary");
  });

  it("turns amber at 80 percent of the allowance", async () => {
    renderRing({ quota: { usedUsd: "8.50" } });
    await waitFor(() =>
      expect(screen.getByTestId("spend-ring")).toHaveTextContent("85%"),
    );
    expect(screen.getByTestId("spend-ring")).toHaveClass("text-warning");
  });

  it("turns red and stays full past the allowance", async () => {
    renderRing({ quota: { usedUsd: "12.00" } });
    await waitFor(() =>
      expect(screen.getByTestId("spend-ring")).toHaveTextContent("100%"),
    );
    expect(screen.getByTestId("spend-ring")).toHaveClass("text-destructive");
  });

  it("states this conversation and this month in its tooltip", async () => {
    renderRing();
    await waitFor(() =>
      expect(screen.getByTestId("spend-ring")).toHaveTextContent("13%"),
    );
    const figures = await openFigures();
    expect(within(figures).getByTestId("spend-conversation")).toHaveTextContent(
      "This conversation3K tokens, $0.03",
    );
    expect(within(figures).getByTestId("spend-month")).toHaveTextContent(
      "This month$1.25 of $10.00",
    );
    expect(within(figures).getByTestId("spend-resets")).toHaveTextContent(
      "ResetsDec 1",
    );
    expect(figures).not.toHaveTextContent("On your keys");
  });

  it("adds the spend on the researcher's keys", async () => {
    renderRing({
      quota: {
        ownKeyUsd: "3.40",
        ownKeyTokens: 1_200_000,
        ownKeyProviders: ["openai"],
      },
    });
    await waitFor(() =>
      expect(screen.getByTestId("spend-ring")).toHaveTextContent("13%"),
    );
    const figures = await openFigures();
    expect(within(figures).getByTestId("spend-own-keys")).toHaveTextContent(
      "On your keys$3.40, 1.2M tokens",
    );
  });

  it("opens its figures on a touch tap", async () => {
    renderRing();
    const ring = await screen.findByTestId("spend-ring");

    await userEvent.pointer({ keys: "[TouchA]", target: ring });

    expect(await screen.findByRole("tooltip")).toHaveTextContent("This month");
  });

  it("is a keyboard reachable button", async () => {
    renderRing();
    const ring = await screen.findByTestId("spend-ring");
    expect(ring.tagName).toBe("BUTTON");

    await userEvent.tab();
    expect(ring).toHaveFocus();
  });

  it("shows the conversation total alone while signed out", async () => {
    renderRing({ signedIn: false });
    const figures = await openFigures();
    expect(within(figures).getByTestId("spend-conversation")).toHaveTextContent(
      "3K tokens, $0.03",
    );
    expect(within(figures).queryByTestId("spend-month")).toBeNull();
    expect(screen.getByTestId("spend-ring")).toHaveAccessibleName(
      "This conversation's spend",
    );
    expect(quotaReads).toEqual([]);
  });

  it("renders nothing with no usage and no allowance", () => {
    const { container } = renderRing({ signedIn: false, messages: [] });
    expect(container.childElementCount).toBe(0);
  });
});
