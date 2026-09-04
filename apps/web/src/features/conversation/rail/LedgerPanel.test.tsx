// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

const messagesRef: { current: unknown[] } = { current: [] };
vi.mock("../runtime/chatHelpersContext", () => ({
  useChatHelpers: () => ({ messages: messagesRef.current }),
}));

import { LedgerPanel, ledgerTabSignatures } from "./LedgerPanel";
import { useRightRailStore } from "@/state/useRightRailStore";

const EMPTY_BUILD = {
  pushedCount: 0,
  failedCount: 0,
  skippedCount: 0,
  zeroResultSteps: [],
  needsRecovery: false,
  recoveryKind: "none" as const,
  succeeded: false,
  nodeResults: [],
  wdkStrategyId: null,
  wdkUrl: null,
};

function makeLedger(overrides: Partial<InvestigationLedger> = {}): InvestigationLedger {
  return {
    userIntent: {
      rawText: "find genes",
      classification: "new_strategy",
      inferredGoal: "find genes",
      isDifferential: false,
      differentialSides: [],
    },
    frame: {
      present: true,
      diff: null,
      criteriaCount: 2,
      boundCount: 2,
      openSlotCount: 0,
      droppedCount: 0,
      readyToBuild: true,
      needsUser: false,
      contrasts: [],
      structureRender: null,
      spec: null,
    },
    build: {
      pushedCount: 1,
      failedCount: 0,
      skippedCount: 0,
      zeroResultSteps: [],
      needsRecovery: false,
      recoveryKind: "none",
      succeeded: true,
      nodeResults: [],
      wdkStrategyId: null,
      wdkUrl: null,
    },
    verification: { complete: false, successful: false },
    constraints: { grounded: [], unmetCount: 0, blocking: false },
    ...overrides,
  };
}

function setLedger(ledger: InvestigationLedger): void {
  messagesRef.current = [
    { role: "assistant", parts: [{ type: "data-ledger-update", data: ledger }] },
  ];
}

beforeEach(() => {
  useRightRailStore.setState({ ledgerSeen: {} });
  messagesRef.current = [];
});

afterEach(() => {
  cleanup();
});

describe("ledgerTabSignatures", () => {
  it("isolates a change to the tab whose section changed", () => {
    const base = ledgerTabSignatures(makeLedger());
    const buildChanged = ledgerTabSignatures(
      makeLedger({ build: { ...EMPTY_BUILD, pushedCount: 5, succeeded: true } }),
    );
    expect(buildChanged.build).not.toBe(base.build);
    expect(buildChanged.frame).toBe(base.frame);
    expect(buildChanged.verification).toBe(base.verification);
  });
});

describe("LedgerPanel tab indicators", () => {
  it("flags unseen detail tabs and not the summary tab", () => {
    setLedger(makeLedger());
    render(<LedgerPanel conversationId="c1" />);

    expect(screen.getByLabelText("Planning has updates")).toBeInTheDocument();
    expect(screen.getByLabelText("Building has updates")).toBeInTheDocument();
    expect(screen.queryByLabelText("Summary has updates")).toBeNull();
  });

  it("clears a tab's dot once viewed, leaving other tabs flagged", () => {
    setLedger(makeLedger());
    render(<LedgerPanel conversationId="c1" />);

    fireEvent.click(screen.getByRole("button", { name: /Planning/ }));
    fireEvent.click(screen.getByRole("button", { name: /Summary/ }));

    expect(screen.queryByLabelText("Planning has updates")).toBeNull();
    expect(screen.getByLabelText("Building has updates")).toBeInTheDocument();
  });
});

describe("LedgerPanel summary", () => {
  it("shows no sub-agent call count", () => {
    setLedger(makeLedger());
    render(<LedgerPanel conversationId="c1" />);

    expect(screen.queryAllByText("Sub-agent calls")).toHaveLength(0);
    expect(screen.queryAllByText("this turn")).toHaveLength(0);
  });

  it("shows the context fill of a running dispatch", () => {
    messagesRef.current = [
      {
        role: "assistant",
        parts: [
          { type: "data-ledger-update", data: makeLedger() },
          {
            type: "data-sub-agent-call",
            data: {
              toolCallId: "sa_1",
              subAgent: "frame",
              phase: "frame",
              state: "started",
              contextTokens: 210_000,
              contextWindow: 1_050_000,
            },
          },
        ],
      },
    ];
    render(<LedgerPanel conversationId="c1" />);

    expect(screen.getByText("Context")).toBeInTheDocument();
    expect(screen.getByText("210K / 1.1M")).toBeInTheDocument();
  });

  it("shows no context section when nothing reported a request size", () => {
    setLedger(makeLedger());
    render(<LedgerPanel conversationId="c1" />);

    const headings = screen
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(headings).toEqual([
      "Intent",
      "Planning",
      "Build",
      "Verification",
      "Constraints",
    ]);
  });
});

describe("LedgerPanel keyboard access", () => {
  it("gives the scrolling detail body a named tab stop", () => {
    setLedger(makeLedger());
    render(<LedgerPanel conversationId="c1" />);

    const body = screen.getByRole("region", { name: "Progress detail" });
    expect(body).toHaveAttribute("tabindex", "0");
  });
});

describe("LedgerPanel raises no dot over an empty section", () => {
  it("leaves Building and Checking unflagged while only Planning has content", () => {
    setLedger(
      makeLedger({
        build: EMPTY_BUILD,
        verification: { complete: false, successful: false },
      }),
    );
    render(<LedgerPanel conversationId="c1" />);

    expect(screen.getByLabelText("Planning has updates")).toBeInTheDocument();
    expect(screen.queryByLabelText("Building has updates")).toBeNull();
    expect(screen.queryByLabelText("Checking has updates")).toBeNull();
  });

  it("flags Building once it pushed a step", () => {
    setLedger(makeLedger());
    render(<LedgerPanel conversationId="c1" />);
    expect(screen.getByLabelText("Building has updates")).toBeInTheDocument();
  });

  it("leaves Planning unflagged before a plan exists", () => {
    setLedger(
      makeLedger({
        userIntent: null,
        frame: {
          present: false,
          diff: null,
          criteriaCount: 0,
          boundCount: 0,
          openSlotCount: 0,
          droppedCount: 0,
          readyToBuild: false,
          needsUser: false,
          contrasts: [],
          structureRender: null,
          spec: null,
        },
        build: EMPTY_BUILD,
      }),
    );
    render(<LedgerPanel conversationId="c1" />);
    expect(screen.queryAllByLabelText(/has updates/)).toHaveLength(0);
  });
});

describe("LedgerPanel says which stage is running", () => {
  it("names the running stage before any stage reported", () => {
    messagesRef.current = [
      {
        role: "assistant",
        parts: [
          {
            type: "data-sub-agent-call",
            data: { toolCallId: "c1", phase: "frame", state: "started" },
          },
        ],
      },
    ];
    render(<LedgerPanel conversationId="c1" />);
    expect(screen.getByText("Planning is running...")).toBeInTheDocument();
    expect(screen.queryByText(/Waiting for the first stage/)).toBeNull();
  });

  it("waits only when nothing is running", () => {
    messagesRef.current = [];
    render(<LedgerPanel conversationId="c1" />);
    expect(screen.getByText(/Waiting for the first stage/)).toBeInTheDocument();
  });
});
