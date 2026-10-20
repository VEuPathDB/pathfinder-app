/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => "/conversation/conv-1",
}));

import { useEdaStore } from "@/state/eda";
import { EdaPanel } from "./EdaPanel";
import { EDA_ANALYSIS_STATE_FIXTURE } from "../content/parts/edaPartFixtures";

beforeEach(() => {
  useEdaStore.getState().reset();
  pushMock.mockClear();
});

describe("EdaPanel", () => {
  it("invites the researcher to ask for a study when nothing is bound", () => {
    render(<EdaPanel conversationId="conv-1" />);
    expect(screen.getByTestId("rail-eda-panel")).toHaveTextContent("No study is open");
  });

  it("names the bound study, the analysis and its filter count", () => {
    useEdaStore.getState().applyAnalysisState(EDA_ANALYSIS_STATE_FIXTURE);
    render(<EdaPanel conversationId="conv-1" />);
    const panel = screen.getByTestId("rail-eda-panel");
    expect(panel).toHaveTextContent(
      "Heat shock response in sensitive mutants (LRR5, DHC)",
    );
    expect(panel).toHaveTextContent("Febrile samples");
    expect(panel).toHaveTextContent("2 filters");
    expect(panel).toHaveTextContent("1 computation");
  });

  it("uses the singular on a single filter and no computation", () => {
    useEdaStore.getState().applyAnalysisState({
      ...EDA_ANALYSIS_STATE_FIXTURE,
      numFilters: 1,
      numComputations: 0,
    });
    render(<EdaPanel conversationId="conv-1" />);
    const panel = screen.getByTestId("rail-eda-panel");
    expect(panel).toHaveTextContent("1 filter");
    expect(panel).toHaveTextContent("0 computations");
  });

  it("opens the tab from the header action", async () => {
    useEdaStore.getState().applyAnalysisState(EDA_ANALYSIS_STATE_FIXTURE);
    render(<EdaPanel conversationId="conv-1" />);
    await userEvent.click(screen.getByTestId("rail-eda-open"));
    expect(pushMock).toHaveBeenCalledWith("/conversation/conv-1/eda");
  });

  it("has no open action when nothing is bound", () => {
    render(<EdaPanel conversationId="conv-1" />);
    expect(screen.queryByTestId("rail-eda-open")).toBe(null);
  });
});
