/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { UIMessage } from "ai";

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { useEdaStore } from "@/state/eda";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { DataEdaSubsetPreview } from "./DataEdaSubsetPreview";
import { DataEdaViz } from "./DataEdaViz";
import { figureNumberFor } from "./figureNumbers";
import {
  EDA_ANALYSIS_STATE_FIXTURE,
  EDA_SUBSET_PREVIEW_FIXTURE,
  EDA_VOLCANO_VIZ_FIXTURE,
} from "./edaPartFixtures";

const STUDY = "Heat shock response in sensitive mutants (LRR5, DHC)";
const PREVIEW = EDA_SUBSET_PREVIEW_FIXTURE;
const VOLCANO = { ...EDA_VOLCANO_VIZ_FIXTURE, totalPoints: 5511, retainedPoints: 1543 };
const FLAT_PREVIEW = { ...PREVIEW, distribution: null };

type Part = UIMessage["parts"][number];

function statePart(): Part {
  return { type: "data-eda.analysis-state", data: EDA_ANALYSIS_STATE_FIXTURE } as Part;
}

function previewPart(data: object): Part {
  return { type: "data-eda.subset-preview", data } as Part;
}

function vizPart(data: object): Part {
  return { type: "data-eda.viz", data } as Part;
}

function messagesOf(parts: Part[]): UIMessage[] {
  return [{ id: "m1", role: "assistant", parts }];
}

function chatOf(parts: Part[]): ChatHelpers {
  return {
    id: "conv-1",
    messages: messagesOf(parts),
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    resumeStream: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}

function inThread(parts: Part[], children: ReactNode) {
  return render(
    <ChatHelpersProvider value={chatOf(parts)}>{children}</ChatHelpersProvider>,
  );
}

function classesOf(node: HTMLElement): string[] {
  return node.className.split(/\s+/).filter((token) => token !== "");
}

beforeEach(() => {
  useEdaStore.getState().reset();
  useEdaStore.getState().applyAnalysisState(EDA_ANALYSIS_STATE_FIXTURE);
});

describe("figureNumberFor", () => {
  it("numbers the thread's plots in emission order across both kinds", () => {
    const messages = messagesOf([statePart(), previewPart(PREVIEW), vizPart(VOLCANO)]);
    expect(figureNumberFor(messages, PREVIEW)).toBe(1);
    expect(figureNumberFor(messages, VOLCANO)).toBe(2);
  });

  it("numbers a plot that follows a second plot of the same kind", () => {
    const second = { ...VOLCANO, effectSizeLabel: "log2(Fold Change), day 3" };
    const messages = messagesOf([
      previewPart(PREVIEW),
      vizPart(VOLCANO),
      vizPart(second),
    ]);
    expect(figureNumberFor(messages, second)).toBe(3);
  });

  it("gives no number to a subset preview that carries no distribution", () => {
    const messages = messagesOf([previewPart(FLAT_PREVIEW), vizPart(VOLCANO)]);
    expect(figureNumberFor(messages, FLAT_PREVIEW)).toBe(null);
    expect(figureNumberFor(messages, VOLCANO)).toBe(1);
  });

  it("answers null when the thread does not carry the payload", () => {
    expect(figureNumberFor(messagesOf([previewPart(PREVIEW)]), VOLCANO)).toBe(null);
  });

  it("ties two identical payloads on the first match", () => {
    const messages = messagesOf([vizPart(VOLCANO), vizPart({ ...VOLCANO })]);
    expect(figureNumberFor(messages, VOLCANO)).toBe(1);
    expect(figureNumberFor(messages, { ...VOLCANO })).toBe(1);
  });
});

describe("the thread's numbered figure captions", () => {
  it("captions the two plots Figure 1 and Figure 2, study first", () => {
    inThread(
      [statePart(), previewPart(PREVIEW), vizPart(VOLCANO)],
      [
        <DataEdaSubsetPreview key="p" data={PREVIEW} />,
        <DataEdaViz key="v" data={VOLCANO} />,
      ],
    );
    expect(
      screen.getAllByTestId("figure-caption").map((node) => node.textContent),
    ).toEqual([
      `Figure 1. ${STUDY} - 6 of 12 Sample, 6 values.`,
      `Figure 2. ${STUDY} - 1,543 of 5,511 genes retained.`,
    ]);
  });

  it("centers and italicizes a numbered caption", () => {
    inThread([statePart(), vizPart(VOLCANO)], <DataEdaViz key="v" data={VOLCANO} />);
    expect(classesOf(screen.getByTestId("figure-caption"))).toEqual([
      "mt-2",
      "text-xs",
      "text-muted-foreground",
      "text-center",
      "italic",
    ]);
  });

  it("leaves a plot the thread does not carry unnumbered and left-aligned", () => {
    inThread([statePart()], <DataEdaViz key="v" data={VOLCANO} />);
    const caption = screen.getByTestId("figure-caption");
    expect(caption.textContent).toBe(`${STUDY} - 1,543 of 5,511 genes retained.`);
    expect(classesOf(caption)).toEqual(["mt-2", "text-xs", "text-muted-foreground"]);
  });

  it("leaves the caption unnumbered when the thread carries no parts", () => {
    inThread([], <DataEdaViz data={VOLCANO} />);
    const caption = screen.getByTestId("figure-caption");
    expect(caption.textContent).toBe("1,543 of 5,511 genes retained.");
    expect(classesOf(caption)).toEqual(["mt-2", "text-xs", "text-muted-foreground"]);
  });

  it("leaves a subset preview with no distribution unnumbered", () => {
    inThread(
      [statePart(), previewPart(FLAT_PREVIEW)],
      <DataEdaSubsetPreview key="p" data={FLAT_PREVIEW} />,
    );
    const caption = screen.getByTestId("figure-caption");
    expect(caption.textContent).toBe(`${STUDY} - 6 of 12 Sample.`);
    expect(classesOf(caption)).toEqual(["mt-2", "text-xs", "text-muted-foreground"]);
  });
});
