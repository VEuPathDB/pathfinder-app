// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { reduceSnapshot } from "@veupathdb/assistant-client";

const messagesRef: { current: unknown[] } = { current: [] };
vi.mock("../runtime/chatHelpersContext", () => ({
  useChatHelpers: () => ({ messages: messagesRef.current }),
}));

import { useRightRailStore } from "@/state/useRightRailStore";

import { EVIDENCE_CARD } from "../content/parts/evidenceCardFixture";
import { LedgerPanel, ledgerTabSignatures } from "./LedgerPanel";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

const LEDGER = {
  userIntent: null,
  frame: {
    present: true,
    diff: null,
    criteriaCount: 1,
    boundCount: 1,
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
    wdkStrategyId: 300125410,
    wdkUrl: null,
  },
  verification: { complete: true, successful: true },
  constraints: { grounded: [], unmetCount: 0, blocking: false },
};

/** The logged chunks of one checked turn, as the snapshot route serves them. */
function snapshot(revision: string | null): unknown[] {
  return [
    {
      type: "user-message",
      message: {
        id: "11111111-1111-4111-8111-111111111111",
        role: "user",
        parts: [{ type: "text", text: "Find small proteins and test my controls" }],
      },
    },
    { type: "start", messageId: "22222222-2222-4222-8222-222222222222" },
    { type: "data-ledger-update", data: LEDGER },
    { type: "data-evidence-card", data: EVIDENCE_CARD },
    ...(revision === null
      ? []
      : [{ type: "data-strategy-revision", data: { revision } }]),
    { type: "finish", finishReason: "stop" },
  ];
}

function openVerification(chunks: unknown[]): void {
  messagesRef.current = reduceSnapshot(chunks);
  render(<LedgerPanel conversationId="c1" />);
  fireEvent.click(screen.getByRole("button", { name: /^Checking/ }));
}

beforeEach(() => {
  useRightRailStore.setState({ ledgerSeen: {} });
});

afterEach(() => {
  cleanup();
  messagesRef.current = [];
});

describe("the Verification tab draws the check's evidence card", () => {
  it("shows every control id, both counts of each step, the citations and the links", () => {
    openVerification(snapshot("rev-1"));

    expect(screen.getByTestId("evidence-verdict").textContent).toBe("Supported");
    expect(screen.getByTestId("evidence-ids-positive-returned").textContent).toBe(
      "PF3D7_0102600, PF3D7_0709000",
    );
    expect(screen.getByTestId("evidence-ids-negative-not-returned").textContent).toBe(
      "TGME49_205250, PF3D7_1222600",
    );
    expect(screen.getByTestId("evidence-step-changed").textContent).toBe(
      "1,851 (changed on the site)",
    );
    expect(
      screen.getByText("https://doi.org/10.1038/nature12970").getAttribute("href"),
    ).toBe("https://doi.org/10.1038/nature12970");
    expect(screen.getByTestId("evidence-strategy-link").getAttribute("href")).toBe(
      EVIDENCE_CARD.strategyUrl,
    );
    expect(screen.queryByTestId("evidence-superseded")).toBeNull();
  });

  it("marks the card superseded once the strategy changed after the check", () => {
    openVerification(snapshot("rev-2"));

    expect(screen.getByTestId("evidence-superseded").textContent).toBe(
      "Superseded: the strategy changed after this check.",
    );
  });

  it("reads the control counts into the summary", () => {
    messagesRef.current = reduceSnapshot(snapshot("rev-1"));
    render(<LedgerPanel conversationId="c1" />);

    expect(screen.getByText("2/3 positives, 0/2 negatives")).toBeInTheDocument();
  });
});

describe("the Checking dot", () => {
  it("rises for a new check's card and for no other tab", () => {
    const ledger = LEDGER as unknown as InvestigationLedger;
    const none = ledgerTabSignatures(ledger, null);
    const first = ledgerTabSignatures(ledger, EVIDENCE_CARD);
    const second = ledgerTabSignatures(ledger, {
      ...EVIDENCE_CARD,
      checkId: "call_verify_2",
    });

    expect([
      first.verification === none.verification,
      second.verification === first.verification,
    ]).toEqual([false, false]);
    expect([first.frame, first.build]).toEqual([none.frame, none.build]);
  });
});
