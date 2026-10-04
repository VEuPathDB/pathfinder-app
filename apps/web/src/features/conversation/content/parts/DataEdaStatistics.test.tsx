/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render as renderBare, screen, within } from "@testing-library/react";

const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));
vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption,
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import type { ReactNode } from "react";
import type { EdaStatisticsPart } from "@pathfinder/shared";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataEdaStatistics } from "./DataEdaStatistics";
import {
  EDA_ANALYSIS_STATE_FIXTURE,
  EDA_BOXPLOT_FIXTURE,
  EDA_CONTINGENCY_FIXTURE,
  EDA_TREND_FIXTURE,
  EDA_TWO_BY_TWO_FIXTURE,
} from "./edaPartFixtures";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

function render(data: EdaStatisticsPart) {
  const chat = chatHelpersFor(
    threadOf([
      threadPart("data-eda.analysis-state", EDA_ANALYSIS_STATE_FIXTURE),
      threadPart("data-eda.statistics", data),
    ]),
  );
  function Wrapper({ children }: { children: ReactNode }) {
    return <ChatHelpersProvider value={chat}>{children}</ChatHelpersProvider>;
  }
  return renderBare(<DataEdaStatistics data={data} />, { wrapper: Wrapper });
}

function cellsOf(testId: string): (string | null)[] {
  return within(screen.getByTestId(testId))
    .getAllByRole("cell")
    .map((cell) => cell.textContent);
}

const STUDY = "Heat shock response in sensitive mutants (LRR5, DHC)";

describe("DataEdaStatistics contingency", () => {
  it("titles the table with the test and both variables", () => {
    render(EDA_CONTINGENCY_FIXTURE);
    expect(
      screen
        .getByText("Contingency table of genotype by temperature_condition")
        .closest("figcaption")?.tagName,
    ).toBe("FIGCAPTION");
  });

  it("reads each x label as a row and each y label as a column", () => {
    render(EDA_CONTINGENCY_FIXTURE);
    const heads = within(screen.getByTestId("eda-statistics-counts"))
      .getAllByRole("columnheader")
      .map((head) => head.textContent);
    expect(heads).toEqual(["", "febrile", "normal"]);
    expect(cellsOf("eda-statistics-count-0")).toEqual(["delta-DHC mutant", "2", "2"]);
    expect(cellsOf("eda-statistics-count-2")).toEqual(["wildtype", "2", "2"]);
  });

  it("lists the chi-squared test with the interval it does not report", () => {
    render(EDA_CONTINGENCY_FIXTURE);
    expect(cellsOf("eda-statistics-row-0")).toEqual([
      "chi-squared",
      "0",
      "1",
      "not reported",
    ]);
    expect(cellsOf("eda-statistics-row-1")).toEqual([
      "degrees of freedom",
      "2",
      "not reported",
      "not reported",
    ]);
  });

  it("numbers it among the thread's tables and counts the records it rests on", () => {
    render(EDA_CONTINGENCY_FIXTURE);
    expect(screen.getByTestId("figure")).toHaveAttribute("id", "table-1");
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      `Table 1. Each genotype was sampled in both conditions (${STUDY} - 12 records).`,
    );
  });
});

describe("DataEdaStatistics two-by-two", () => {
  it("writes not reported for a statistic the service gave only a p-value", () => {
    render({
      ...EDA_TWO_BY_TWO_FIXTURE,
      rows: EDA_TWO_BY_TWO_FIXTURE.rows.map((row) =>
        row.name === "Fisher's exact" ? { ...row, value: null } : row,
      ),
    });
    expect(cellsOf("eda-statistics-row-1")).toEqual([
      "Fisher's exact",
      "not reported",
      "0.4857",
      "0.3 - 271.9",
    ]);
  });

  it("keeps the text the service wrote for an interval", () => {
    render(EDA_TWO_BY_TWO_FIXTURE);
    expect(cellsOf("eda-statistics-row-0")).toEqual([
      "chi-squared",
      "0.5",
      "0.4795",
      "NA",
    ]);
    expect(cellsOf("eda-statistics-count-0")).toEqual(["febrile", "3", "1"]);
  });
});

describe("DataEdaStatistics boxplot", () => {
  it("draws the box chart with every group's label and no statistics table", () => {
    render(EDA_BOXPLOT_FIXTURE);
    expect(screen.getByTestId("eda-statistics-boxplot")).toHaveAttribute(
      "aria-label",
      "Box plot of 3 groups: delta-DHC mutant, delta-LRR5 mutant, wildtype",
    );
    expect(screen.queryByTestId("eda-statistics-rows")).toBe(null);
    expect(screen.queryByTestId("eda-statistics-counts")).toBe(null);
  });

  it("numbers it among the thread's figures and counts its groups", () => {
    render(EDA_BOXPLOT_FIXTURE);
    expect(screen.getByTestId("figure")).toHaveAttribute("id", "figure-1");
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      `Figure 1. ${STUDY} - 3 groups.`,
    );
  });
});

describe("DataEdaStatistics trend", () => {
  it("draws the points and the line the service fit through them", async () => {
    setOption.mockClear();
    render(EDA_TREND_FIXTURE);
    await flush();
    expect(screen.getByTestId("eda-statistics-trend")).toHaveAttribute(
      "aria-label",
      "Scatter plot of Antisense Count against Sense Count, 36 points",
    );
    const option = setOption.mock.calls[0]?.[0] as {
      series: { type: string; name: string; data: unknown[] }[];
    };
    expect(option.series.map((s) => [s.type, s.name, s.data.length])).toEqual([
      ["scatter", "Points", 36],
      ["line", "Best-fit line", 20],
    ]);
  });

  it("lists the r-squared beside the plot", () => {
    render(EDA_TREND_FIXTURE);
    expect(cellsOf("eda-statistics-row-0")).toEqual([
      "r-squared",
      "0.106",
      "not reported",
      "not reported",
    ]);
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      `Figure 1. ${STUDY} - 36 points.`,
    );
  });
});

describe("DataEdaStatistics on a part an earlier version wrote", () => {
  it("shows the stale-part notice and draws nothing", () => {
    const { title, ...untitled } = EDA_CONTINGENCY_FIXTURE;
    expect(title).toBe("Contingency table of genotype by temperature_condition");
    renderBare(<DataEdaStatistics data={untitled} />);
    expect(screen.getByTestId("stale-part-notice")).toHaveTextContent(
      "A statistic from an earlier version of PathFinder can't be shown.",
    );
    expect(screen.queryByTestId("data-eda-statistics")).toBe(null);
  });
});
