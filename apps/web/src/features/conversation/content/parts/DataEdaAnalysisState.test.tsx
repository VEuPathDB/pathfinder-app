/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render as renderBare, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { pushMock, route } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  route: { pathname: "/plasmodb/conversation/conv-1" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => route.pathname,
}));

import { edaTabUrl } from "@/lib/routes";
import type { ReactElement, ReactNode } from "react";

import { useEdaStore } from "@/state/eda";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { DataEdaAnalysisState } from "./DataEdaAnalysisState";
import { EDA_ANALYSIS_STATE_FIXTURE } from "./edaPartFixtures";

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;

function ChatWrapper({ children }: { children: ReactNode }) {
  return <ChatHelpersProvider value={STUB_CHAT}>{children}</ChatHelpersProvider>;
}

function render(ui: ReactElement) {
  return renderBare(ui, { wrapper: ChatWrapper });
}

beforeEach(() => {
  useEdaStore.getState().reset();
  pushMock.mockClear();
  route.pathname = "/plasmodb/conversation/conv-1";
});

describe("DataEdaAnalysisState", () => {
  it("titles the figure with the study", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    expect(screen.getByTestId("figure")).toHaveTextContent(
      "Heat shock response in sensitive mutants (LRR5, DHC)",
    );
  });

  it("captions the figure with every entity count, joined and separated", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "6 of 12 Sample, 34,320 of 68,640 pfal3D7 htseq counts",
    );
  });

  it("states each entity count once, in the caption and not again in the body", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    const card = screen.getByTestId("data-eda-analysis-state");
    expect(card.textContent.split("6 of 12 Sample")).toHaveLength(2);
    expect(card.textContent.split("34,320 of 68,640")).toHaveLength(2);
    expect(card.querySelectorAll("ul")).toHaveLength(0);
  });

  it("keeps the caption left-aligned and unnumbered, because it is a status card", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    const caption = screen.getByTestId("figure-caption");
    expect(caption.className).toBe("mt-2 text-xs text-muted-foreground");
    expect(caption.textContent).not.toContain("Figure");
  });

  it("falls back to the dataset id when the study has no display name", () => {
    render(
      <DataEdaAnalysisState
        data={{ ...EDA_ANALYSIS_STATE_FIXTURE, studyDisplayName: "" }}
      />,
    );
    expect(screen.getByText("DS_e973eadd57")).toBeInTheDocument();
  });

  it("draws no divider, no card and no outer margin", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    const figure = screen.getByTestId("figure");
    expect(figure.className).toBe("");
    expect(screen.getByTestId("data-eda-analysis-state").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });

  it("hydrates the store so the tab reflects a chat-driven change", async () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    await waitFor(() => {
      expect(useEdaStore.getState().analysis?.analysisId).toBe("a-1");
    });
    const state = useEdaStore.getState();
    expect(state.analysis?.revision).toBe(3);
    expect(state.analysis?.filterSummaries).toHaveLength(2);
    expect(state.binding).toEqual({
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
      analysisId: "a-1",
    });
  });

  it("hydrates once for one payload, however many times it re-renders", async () => {
    const { rerender } = render(
      <DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />,
    );
    await waitFor(() => {
      expect(useEdaStore.getState().analysis?.revision).toBe(3);
    });
    useEdaStore
      .getState()
      .applyAnalysisState({ ...EDA_ANALYSIS_STATE_FIXTURE, displayName: "Renamed" });
    rerender(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    await Promise.resolve();
    expect(useEdaStore.getState().analysis?.displayName).toBe("Renamed");
  });
});

describe("DataEdaAnalysisState chips and navigation", () => {
  it("names the study and the analysis separately", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    expect(
      screen.getByText("Heat shock response in sensitive mutants (LRR5, DHC)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Febrile samples")).toBeInTheDocument();
  });

  it("renders one chip per backend filter summary, in order", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    const chips = screen.getAllByTestId(/^data-eda-filter-chip-/);
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent("temperature_condition is febrile");
    expect(chips[1]).toHaveTextContent("Temperature is 37 to 42");
  });

  it("keys chips by position, so two identical summaries both render", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const summaries = [
      "temperature_condition is febrile",
      "temperature_condition is febrile",
    ];
    const { rerender } = render(
      <DataEdaAnalysisState
        data={{ ...EDA_ANALYSIS_STATE_FIXTURE, filterSummaries: summaries }}
      />,
    );
    rerender(
      <DataEdaAnalysisState
        data={{
          ...EDA_ANALYSIS_STATE_FIXTURE,
          filterSummaries: [...summaries, "Temperature is 37 to 42"],
        }}
      />,
    );
    expect(screen.getAllByTestId(/^data-eda-filter-chip-/)).toHaveLength(3);
    expect(screen.getByTestId("data-eda-filter-chip-0")).toHaveTextContent(
      "temperature_condition is febrile",
    );
    expect(screen.getByTestId("data-eda-filter-chip-1")).toHaveTextContent(
      "temperature_condition is febrile",
    );
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("counts the analysis's computations under the chips", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    expect(screen.getByText("1 computation")).toBeInTheDocument();
  });

  it("says the subset is unfiltered when there are no summaries", () => {
    render(
      <DataEdaAnalysisState
        data={{
          ...EDA_ANALYSIS_STATE_FIXTURE,
          numFilters: 0,
          filters: [],
          filterSummaries: [],
        }}
      />,
    );
    expect(screen.getByTestId("data-eda-analysis-state")).toHaveTextContent(
      "No filters yet",
    );
    expect(screen.queryByTestId("data-eda-filter-overflow")).toBe(null);
  });

  it("says how many filters the backend counted when it rendered fewer summaries", () => {
    render(
      <DataEdaAnalysisState data={{ ...EDA_ANALYSIS_STATE_FIXTURE, numFilters: 5 }} />,
    );
    expect(screen.getByTestId("data-eda-filter-overflow")).toHaveTextContent(
      "3 more filters",
    );
  });

  it("links the analysis in the site's own explorer", () => {
    render(
      <DataEdaAnalysisState
        data={{
          ...EDA_ANALYSIS_STATE_FIXTURE,
          analysisUrl:
            "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
        }}
      />,
    );
    const link = screen.getByRole("link", { name: "Open in PlasmoDB" });
    expect(link).toHaveAttribute(
      "href",
      "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
    );
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("offers no site link for a state that names no page", () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    expect(screen.queryByRole("link", { name: "Open in PlasmoDB" })).toBe(null);
  });

  it("opens the EDA tab for the conversation in the path", async () => {
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    await userEvent.click(screen.getByRole("button", { name: "Open study" }));
    expect(pushMock).toHaveBeenCalledWith(edaTabUrl("plasmodb", "conv-1"));
  });
});

describe("DataEdaAnalysisState off a conversation route", () => {
  afterEach(() => {
    route.pathname = "/plasmodb/conversation/conv-1";
  });

  it("has no open action when the path names no conversation", () => {
    route.pathname = "/plasmodb/saved";
    render(<DataEdaAnalysisState data={EDA_ANALYSIS_STATE_FIXTURE} />);
    expect(screen.queryByRole("button", { name: "Open study" })).toBe(null);
    expect(screen.getByTestId("data-eda-analysis-state")).toHaveTextContent(
      "Febrile samples",
    );
  });
});
