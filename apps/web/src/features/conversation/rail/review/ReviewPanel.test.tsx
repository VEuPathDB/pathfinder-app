// @vitest-environment jsdom
import {
  AssistantRuntimeProvider,
  useAuiState,
  useLocalRuntime,
} from "@assistant-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UIMessage } from "ai";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRightRailStore } from "@/state/useRightRailStore";

import { server } from "../../../../../vitest.msw-setup";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { EVIDENCE_CARD } from "../../content/parts/evidenceCardFixture";
import { makeLedger } from "./ledgerFixture";
import { ReviewPanel } from "./ReviewPanel";

const CONVERSATION = "conv-1";
const API = "http://localhost:3000/pathfinder/api/v1/conversations";

function makeChat(messages: UIMessage[]): ChatHelpers {
  return {
    id: CONVERSATION,
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
}

function Runtime({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
  );
}

function ComposerText() {
  const text = useAuiState((s) => s.composer.text);
  return <output data-testid="composer-text">{text}</output>;
}

function assistant(parts: UIMessage["parts"]): UIMessage[] {
  return [{ id: "m1", role: "assistant", parts }];
}

function renderPanel(messages: UIMessage[]): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Runtime>
        <ChatHelpersProvider value={makeChat(messages)}>
          <ReviewPanel conversationId={CONVERSATION} strategy={null} />
          <ComposerText />
          <textarea data-composer-input aria-label="Message" />
        </ChatHelpersProvider>
      </Runtime>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches: true,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as typeof window.matchMedia;
  server.use(
    http.get(`${API}/${CONVERSATION}/tasks`, () => HttpResponse.json({ tasks: [] })),
    http.get(`${API}/${CONVERSATION}/scratchpad/notes`, () => HttpResponse.json([])),
  );
});

afterEach(() => cleanup());

describe("ReviewPanel", () => {
  it("shows the empty state", () => {
    renderPanel([]);
    expect(screen.getByText("Nothing to review yet")).toBeInTheDocument();
  });

  it("shows build problems unfolded", () => {
    const ledger = makeLedger({
      build: {
        ...makeLedger().build,
        succeeded: false,
        nodeResults: [
          {
            nodeId: "s1",
            searchName: "GenesByText",
            status: "failed",
            error: "Cannot INTERSECT steps with different organism scopes.",
          },
        ],
      },
    });
    renderPanel(assistant([{ type: "data-ledger-update", data: ledger }]));

    expect(screen.getByRole("heading", { name: "Build problems" })).toBeInTheDocument();
    expect(
      screen.getAllByText("Cannot INTERSECT steps with different organism scopes."),
    ).toHaveLength(2);
  });

  it("shows the question in the researcher's words", () => {
    renderPanel(assistant([{ type: "data-ledger-update", data: makeLedger() }]));
    expect(
      screen.getByText("Identify transporter genes across Apicomplexa"),
    ).toBeInTheDocument();
  });

  it("Change fills the composer", async () => {
    const ledger = makeLedger({
      verification: {
        complete: true,
        successful: true,
        caveats: [
          {
            kind: "chosen_among",
            criterionId: "s1",
            paramDisplayName: "Text term",
            value: "transport*",
            source: "chosen",
            unchosenCount: 0,
            sentence: "Text term transport* was chosen for you.",
          },
        ],
      },
    });
    renderPanel(assistant([{ type: "data-ledger-update", data: ledger }]));

    await userEvent.click(screen.getByRole("button", { name: "Change Text term" }));

    expect(screen.getByTestId("composer-text").textContent).toBe(
      "Change Text term (now transport*) to ",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("textbox", { name: "Message" }),
    );
  });

  it("Change closes the rail in a narrow window", async () => {
    window.innerWidth = 744;
    useRightRailStore.setState({ openPanel: "review" });
    const ledger = makeLedger({
      verification: {
        complete: true,
        successful: true,
        caveats: [
          {
            kind: "chosen_among",
            criterionId: "s1",
            paramDisplayName: "Text term",
            value: "transport*",
            source: "chosen",
            unchosenCount: 0,
            sentence: "Text term transport* was chosen for you.",
          },
        ],
      },
    });
    renderPanel(assistant([{ type: "data-ledger-update", data: ledger }]));

    await userEvent.click(screen.getByRole("button", { name: "Change Text term" }));

    expect(useRightRailStore.getState().openPanel).toBe(null);
    window.innerWidth = 1440;
  });

  it("lists recalled memories once", async () => {
    const memory = {
      key: "k1",
      kind: "knowledge",
      name: "Transporter terms",
      summary: "Use transport*",
      createdAt: "2026-11-01T00:00:00Z",
    };
    renderPanel(
      assistant([
        { type: "data-memory-retrieved", data: { memories: [memory] } },
        { type: "data-memory-retrieved", data: { memories: [memory] } },
      ]),
    );

    await userEvent.click(screen.getByRole("button", { name: /Memory/ }));

    expect(screen.getAllByText("Transporter terms")).toHaveLength(1);
  });

  it("shows a sampled gene's reason on expand", async () => {
    renderPanel(
      assistant([
        { type: "data-ledger-update", data: makeLedger() },
        {
          type: "data-evidence-card",
          data: {
            ...EVIDENCE_CARD,
            review: {
              sampledGenes: [
                { geneId: "PKNH_0902400", fits: "yes", why: "A drug transporter." },
              ],
            },
          },
        },
      ]),
    );
    await userEvent.click(screen.getByRole("button", { name: /Show the 1 genes/ }));
    expect(screen.queryByText("A drug transporter.")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /PKNH_0902400/ }));

    expect(screen.getByText("A drug transporter.")).toBeVisible();
  });

  it("shows no percent for a task that reports no progress", async () => {
    server.use(
      http.get(`${API}/${CONVERSATION}/tasks`, () =>
        HttpResponse.json({
          tasks: [
            {
              taskId: "11111111-2222-4333-8444-555555555555",
              toolName: "run_control_tests_on_step",
              status: "running",
              estimatedDurationSeconds: 120,
              createdAt: "2026-11-09T00:00:00Z",
              error: null,
              latestPercent: null,
              latestMessage: "Testing the controls",
            },
          ],
        }),
      ),
    );
    renderPanel([]);

    expect(await screen.findByText("Testing the controls")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Working now" }).closest("section"),
    ).not.toHaveTextContent("%");
  });

  it("hides Working now when idle", () => {
    renderPanel(assistant([{ type: "data-ledger-update", data: makeLedger() }]));
    expect(
      screen.getAllByRole("heading").map((heading) => heading.textContent),
    ).not.toContain("Working now");
    expect(screen.getByTestId("review-verdict")).toHaveTextContent("Not built yet");
  });

  it("shows Working now while a phase runs", () => {
    renderPanel(
      assistant([
        {
          type: "data-sub-agent-call",
          data: { toolCallId: "k1", phase: "verification", state: "started" },
        },
      ]),
    );
    expect(screen.getByRole("heading", { name: "Working now" })).toBeInTheDocument();
  });
});
