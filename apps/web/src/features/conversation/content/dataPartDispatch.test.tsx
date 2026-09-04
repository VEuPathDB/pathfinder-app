/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import type { ThreadMessageLike } from "@assistant-ui/react";
import { reduceSnapshot } from "@pathfinder/assistant-client";
import type { DataPart, TextPart } from "@pathfinder/assistant-client";
import type { DataPartKind } from "@pathfinder/shared";

import { useSettingsStore } from "@/state/useSettingsStore";

import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";

import { AssistantMessage, UserMessage } from "./MessageRenderer";
import { coreDataPartComponents } from "./coreDataParts";
import { edaDataPartComponents } from "./edaDataParts";
import { strategyDataPartComponents } from "./strategyDataParts";
import { dataPartComponents } from "./contentComponents";

const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({
  toast: { error: toastError, success: vi.fn(), message: vi.fn() },
  Toaster: () => null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/plasmodb/conversation/conv-1",
}));

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

// A kind this app never registers, in the shape a second assistant would use.
const FOREIGN_KIND = "data-other.gene-view";

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;

function Thread({ content }: { content: ThreadMessageLike["content"] }) {
  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages: [{ role: "assistant", content }],
    convertMessage: (message) => message,
    onNew: async () => undefined,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={STUB_CHAT}>
        <ThreadPrimitive.Messages components={{ AssistantMessage, UserMessage }} />
      </ChatHelpersProvider>
    </AssistantRuntimeProvider>
  );
}

describe("dataPartComponents merge", () => {
  it("contains every core renderer", () => {
    for (const kind of Object.keys(coreDataPartComponents)) {
      expect(Object.hasOwn(dataPartComponents, kind)).toBe(true);
    }
  });

  it("contains every strategy renderer", () => {
    for (const kind of Object.keys(strategyDataPartComponents)) {
      expect(Object.hasOwn(dataPartComponents, kind)).toBe(true);
    }
  });

  it("contains every eda renderer", () => {
    for (const kind of Object.keys(edaDataPartComponents)) {
      expect(Object.hasOwn(dataPartComponents, kind)).toBe(true);
    }
  });

  it("keeps the three sources disjoint", () => {
    const kinds = [
      ...Object.keys(coreDataPartComponents),
      ...Object.keys(strategyDataPartComponents),
      ...Object.keys(edaDataPartComponents),
    ];
    expect(kinds).toHaveLength(new Set(kinds).size);
  });

  it("adds nothing beyond the three sources", () => {
    const sources = new Set([
      ...Object.keys(coreDataPartComponents),
      ...Object.keys(strategyDataPartComponents),
      ...Object.keys(edaDataPartComponents),
    ]);
    expect(new Set(Object.keys(dataPartComponents))).toEqual(sources);
  });

  it("has no renderer for a kind another assistant registers", () => {
    const kind: DataPartKind = FOREIGN_KIND;
    expect(Object.hasOwn(dataPartComponents, kind)).toBe(false);
  });
});

describe("message dispatch", () => {
  it("renders a core part through the merged map", () => {
    render(
      <Thread
        content={[
          {
            type: "data-memory-retrieved",
            data: {
              memories: [{ key: "k1", kind: "gene_set", name: "Kinases", score: 1 }],
            },
          },
        ]}
      />,
    );
    expect(screen.getByTestId("data-memory-retrieved")).toBeInTheDocument();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("renders no standalone card for the task parts the started card owns", () => {
    render(
      <Thread
        content={[
          {
            type: "data-task-progress",
            data: { taskId: "t1", percent: 0.5, message: "Halfway" },
          },
          {
            type: "data-task-completed",
            data: { taskId: "t1", status: "success" },
          },
        ]}
      />,
    );
    expect(screen.queryByTestId("data-task-progress")).toBeNull();
    expect(screen.queryByTestId("data-task-completed")).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("renders no card for the tool summary the trace reads", () => {
    render(
      <Thread
        content={[
          {
            type: "data-tool-summary",
            data: { toolCallId: "call_1", summary: "6 of 12 Sample", status: "ok" },
          },
        ]}
      />,
    );
    expect(screen.queryByText("6 of 12 Sample")).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("renders a strategy part through the merged map", () => {
    render(
      <Thread
        content={[
          {
            type: "data-strategy-link",
            data: { strategyId: "s1", url: "https://plasmodb.org/s1", title: "Test" },
          },
        ]}
      />,
    );
    expect(screen.getByTestId("data-strategy-link")).toBeInTheDocument();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("renders the eda analysis-state card through the merged map", () => {
    render(
      <Thread
        content={[
          {
            type: "data-eda.analysis-state",
            data: {
              siteId: "plasmodb",
              datasetId: "DS_53f554ec6a",
              studyId: "STUDY_53f554ec6a",
              analysisId: "t4fszEJ",
              revision: 1,
              studyDisplayName: "Rodent malaria phenotypes",
              displayName: "berghei subset",
              numFilters: 1,
              numComputations: 2,
              filters: [],
              filterSummaries: ["Species is one of P. berghei"],
              entityCounts: [],
              canExportRows: false,
            },
          },
        ]}
      />,
    );
    const card = screen.getByTestId("data-eda-analysis-state");
    // The study name titles the figure, outside the part's own body.
    expect(
      screen.getByText("Rodent malaria phenotypes").closest("figcaption"),
    ).not.toBeNull();
    expect(card).toHaveTextContent("berghei subset");
    expect(card).toHaveTextContent("2 computations");
    expect(screen.getByTestId("data-eda-filter-chip-0")).toHaveTextContent(
      "Species is one of P. berghei",
    );
    expect(toastError).not.toHaveBeenCalled();
  });

  it("renders the eda subset preview with each count against its total", () => {
    render(
      <Thread
        content={[
          {
            type: "data-eda.subset-preview",
            data: {
              datasetId: "DS_e973eadd57",
              analysisId: "t4fszEJ",
              entityCounts: [
                {
                  entityId: "GENE_PHENOTYPE_DATA_ENTITY",
                  entityDisplayName: "Gene phenotype",
                  count: 4011,
                  unfilteredCount: 4279,
                },
              ],
              distribution: {
                variableId: "VAR_035294d0",
                variableDisplayName: "Species",
                labels: ["P. berghei", "P. falciparum", "P. yoelii"],
                values: [4011, 4130, 268],
                subsetSize: 4279,
                numVarValues: 8409,
                numMissingCases: 0,
                isMultiValued: true,
              },
              distributionNote: null,
            },
          },
        ]}
      />,
    );
    const card = screen.getByTestId("data-eda-subset-preview");
    expect(card).toHaveTextContent("4,011 of 4,279 Gene phenotype");
    expect(screen.getByTestId("data-eda-subset-bin-1")).toHaveTextContent(
      "P. falciparum 4,130",
    );
    expect(screen.getByTestId("data-eda-subset-coverage")).toHaveTextContent(
      "8409 of 4279 records have a value",
    );
    expect(screen.getByTestId("data-eda-subset-multivalued")).toHaveTextContent(
      "one record can carry several values",
    );
    expect(toastError).not.toHaveBeenCalled();
  });

  it("renders the eda viz card with the compute's retained count", () => {
    render(
      <Thread
        content={[
          {
            type: "data-eda.viz",
            data: {
              datasetId: "DS_e973eadd57",
              analysisId: "t4fszEJ",
              chart: "volcano",
              effectSizeLabel: "log2(Fold Change)",
              effectSizeThreshold: 1,
              significanceThreshold: 0.05,
              totalPoints: 5511,
              retainedPoints: 1543,
              points: [
                {
                  pointId: "PF3D7_MIT04200",
                  effectSize: -1.49447459261845,
                  pValue: null,
                  adjustedPValue: null,
                  retained: false,
                },
              ],
            },
          },
        ]}
      />,
    );
    expect(screen.getByTestId("data-eda-viz")).toBeInTheDocument();
    expect(screen.getByText("log2(Fold Change)").tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("eda-viz-volcano-selection")).toHaveTextContent(
      "0 genes selected at these thresholds - 1,543 of 5,511 retained by the compute",
    );
    expect(screen.getByTestId("eda-viz-volcano-dropped")).toHaveTextContent(
      "1 point without a p-value was not plotted",
    );
    expect(toastError).not.toHaveBeenCalled();
  });

  it("shows the failure of a dead turn rebuilt from the log", () => {
    const errorText = "The worker running this turn stopped before it finished.";
    const messages = reduceSnapshot([
      { type: "user-message", message: { id: "u1", role: "user", parts: [] } },
      { type: "start", messageId: "a1" },
      { type: "text-start", id: "t" },
      { type: "text-delta", id: "t", delta: "Looking at PlasmoDB kinases" },
      { type: "text-end", id: "t" },
      { type: "error", errorText },
      { type: "data-turn-failed", data: { errorText } },
      { type: "finish", finishReason: "error" },
      { type: "done" },
    ]);

    const rebuilt = (messages[1]?.parts ?? []).filter(
      (part): part is TextPart | DataPart =>
        part.type === "text" || part.type.startsWith("data-"),
    );

    render(<Thread content={rebuilt} />);

    expect(screen.getByTestId("failure-notice")).toBeInTheDocument();
    expect(screen.getByText(errorText)).toBeInTheDocument();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("puts no model, token or cost pill above the message", () => {
    const usage = [
      {
        type: "data-lead-usage" as const,
        data: { modelId: "openai:gpt-5.6-luna", tokens: 41800, costUsd: "0.0131" },
      },
    ];
    useSettingsStore.setState({ showTokenUsage: true });
    const view = render(<Thread content={usage} />);
    expect(view.queryAllByTestId("model-badge")).toHaveLength(0);
    expect(view.container.textContent).not.toContain("gpt-5.6-luna");
    expect(view.container.textContent).not.toContain("41.8K");
  });

  it("falls back and reports when the kind has no renderer", () => {
    render(<Thread content={[{ type: FOREIGN_KIND, data: { count: 1 } }]} />);
    expect(toastError).toHaveBeenCalledWith(
      `Unknown data part: ${FOREIGN_KIND}`,
      expect.anything(),
    );
  });
});
