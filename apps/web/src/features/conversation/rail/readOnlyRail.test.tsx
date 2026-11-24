// @vitest-environment jsdom
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import type { Strategy } from "@strategist/shared";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UIMessage } from "ai";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { analysisSnapshotOf } from "@/state/eda";

import { server } from "../../../../vitest.msw-setup";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/shared/tok-1",
}));

import { EDA_ANALYSIS_STATE_FIXTURE } from "../content/parts/edaPartFixtures";
import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { EdaPanel } from "./EdaPanel";
import { RailToggle } from "./RailToggle";
import { railSourceFixture } from "./railSourceFixture";
import { makeLedger } from "./review/ledgerFixture";
import { ReviewPanel } from "./review/ReviewPanel";
import { StrategyPanel } from "./StrategyPanel";

const TWO_STEP: Strategy = {
  id: "shared-1",
  name: "kinases",
  siteId: "plasmodb",
  recordType: "transcript",
  rootStepId: "s-both",
  isSaved: false,
  wdkUrl: null,
  createdAt: "2026-11-23T00:00:00.000Z",
  updatedAt: "2026-11-23T00:00:00.000Z",
  steps: [
    {
      id: "s-list",
      kind: "search",
      displayName: "Gene set: 3D7 strain gaps",
      searchName: "GeneByLocusTag",
      recordType: "transcript",
      parameters: {},
      isFiltered: false,
      estimatedSize: 41,
    },
    {
      id: "s-text",
      kind: "search",
      displayName: "Genes by text",
      searchName: "GenesByText",
      recordType: "transcript",
      parameters: { text_expression: { type: "string", value: "kinase" } },
      isFiltered: false,
      estimatedSize: 1204,
    },
    {
      id: "s-both",
      kind: "combine",
      displayName: "Both",
      operator: "INTERSECT",
      recordType: "transcript",
      primaryInputStepId: "s-list",
      secondaryInputStepId: "s-text",
      isFiltered: false,
      estimatedSize: 12,
    },
  ],
};

const DETACHED: Strategy = {
  ...TWO_STEP,
  steps: [...TWO_STEP.steps, { ...TWO_STEP.steps[1]!, id: "s-loose" }],
};

const EMPTY: Strategy = { ...TWO_STEP, steps: [], rootStepId: null };

const STUDY = analysisSnapshotOf(EDA_ANALYSIS_STATE_FIXTURE);

const requests = { notes: 0 };

const FOLD_TOGGLES = ["Memory1 used"];

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

function chat(messages: UIMessage[]): ChatHelpers {
  return {
    id: "shared-tok-1",
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

beforeEach(() => {
  requests.notes = 0;
  server.use(
    http.get("*/conversations/:id/scratchpad/notes", () => {
      requests.notes += 1;
      return HttpResponse.json([]);
    }),
  );
});

afterEach(() => cleanup());

describe("a rail with no owner", () => {
  it("shows the strategy and its counts with no action", () => {
    render(
      <StrategyPanel
        source={railSourceFixture({ owner: null, strategy: TWO_STEP })}
        check={null}
      />,
    );
    expect(screen.getByTestId("strategy-headline")).toHaveTextContent("12");
    expect(screen.getByTestId("compact-step-row-s-list")).toBeVisible();
    expect(screen.queryByTestId("rail-strategy-refresh")).toBeNull();
    expect(screen.queryByTestId("rail-strategy-open")).toBeNull();
    expect(screen.queryByRole("link", { name: /^Open strategy on / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Step actions" })).toBeNull();
  });

  it("offers no removal of disconnected steps", () => {
    render(
      <StrategyPanel
        source={railSourceFixture({ owner: null, strategy: DETACHED })}
        check={null}
      />,
    );
    expect(screen.getByTestId("compact-strategy-orphans")).toHaveTextContent(
      "1 disconnected",
    );
    expect(screen.queryByRole("button", { name: /Remove all/ })).toBeNull();
  });

  it("offers no saved strategy to an empty rail", () => {
    render(
      <StrategyPanel
        source={railSourceFixture({ owner: null, strategy: EMPTY })}
        check={null}
      />,
    );
    expect(screen.getByText("No strategy built yet")).toBeVisible();
    expect(screen.queryByTestId("rail-strategy-insert-saved")).toBeNull();
  });

  it("offers no owner control in the Review panel", async () => {
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
    const memory = {
      key: "k1",
      kind: "knowledge",
      name: "Transporter terms",
      summary: "Use transport*",
      createdAt: "2026-11-01T00:00:00Z",
    };
    render(
      <Runtime>
        <ChatHelpersProvider
          value={chat([
            {
              id: "m1",
              role: "assistant",
              parts: [
                { type: "data-ledger-update", data: ledger },
                { type: "data-memory-retrieved", data: { memories: [memory] } },
              ],
            },
          ])}
        >
          <ReviewPanel source={railSourceFixture({ owner: null })} />
        </ChatHelpersProvider>
      </Runtime>,
    );
    await userEvent.click(screen.getByRole("button", { name: /^Memory/ }));

    const panel = screen.getByTestId("review-panel");
    expect(panel).toHaveTextContent("transport*");
    expect(panel).toHaveTextContent("Transporter terms");
    expect(
      within(panel)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(FOLD_TOGGLES);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(requests.notes).toBe(0);
  });

  it("shows the study with no way to open it", () => {
    render(<EdaPanel source={railSourceFixture({ owner: null, study: STUDY })} />);
    expect(screen.getByText(STUDY.studyDisplayName)).toBeVisible();
    expect(screen.queryByTestId("rail-eda-open")).toBeNull();
  });

  it("offers no share button", () => {
    render(
      <ChatHelpersProvider value={chat([])}>
        <RailToggle source={railSourceFixture({ owner: null })} />
      </ChatHelpersProvider>,
    );
    expect(screen.getByRole("toolbar", { name: "Side panels" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Share" })).toBeNull();
  });
});
