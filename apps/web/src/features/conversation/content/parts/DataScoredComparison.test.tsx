/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";

import type { ScoredComparison } from "@pathfinder/shared";

import { DataScoredComparison } from "./DataScoredComparison";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const SCORED: ScoredComparison = {
  objective: "mcc",
  winnerLabel: "strict",
  variants: [
    {
      label: "lenient",
      searchName: "SA",
      mcc: 0.6,
      f1: 0.8,
      precision: 0.8,
      sensitivity: 0.8,
      balancedAccuracy: 0.8,
      experimentId: "exp_a",
      error: null,
    },
    {
      label: "strict",
      searchName: "SB",
      mcc: 0.82,
      f1: 0.9,
      precision: 0.9,
      sensitivity: 0.9,
      balancedAccuracy: 0.95,
      experimentId: "exp_b",
      error: null,
    },
  ],
};

function inThread(ui: ReactElement<{ data: object }>) {
  const messages = threadOf([threadPart("data-scored-comparison", ui.props.data)]);
  return render(
    <ChatHelpersProvider value={chatHelpersFor(messages)}>{ui}</ChatHelpersProvider>,
  );
}

describe("DataScoredComparison figure", () => {
  it("captions the figure with the variant count and the winning score", () => {
    inThread(<DataScoredComparison data={SCORED} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. 2 variants, winner strict at 0.82",
    );
  });

  it("captions a wholly failed scoring as a failure, not as a missing winner", () => {
    inThread(
      <DataScoredComparison
        data={{
          ...SCORED,
          winnerLabel: null,
          variants: SCORED.variants.map((v) => ({ ...v, error: "boom", mcc: null })),
        }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. scoring failed for 2 of 2 variants",
    );
  });

  it("says so in the caption when nothing scored", () => {
    inThread(<DataScoredComparison data={{ ...SCORED, winnerLabel: null }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. 2 variants, no winner",
    );
  });

  it("titles the figure Scored variants", () => {
    inThread(<DataScoredComparison data={SCORED} />);
    expect(screen.getByText("Scored variants").parentElement?.tagName).toBe(
      "FIGCAPTION",
    );
  });

  it("draws no divider, no card and no outer margin", () => {
    inThread(<DataScoredComparison data={SCORED} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-scored-comparison").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});

describe("DataScoredComparison", () => {
  it("ranks variants, flags the winner, and shows metrics", () => {
    inThread(
      <DataScoredComparison
        data={{
          objective: "mcc",
          winnerLabel: "strict",
          variants: [
            {
              label: "lenient",
              searchName: "SA",
              mcc: 0.6,
              f1: 0.8,
              precision: 0.8,
              sensitivity: 0.8,
              balancedAccuracy: 0.8,
              experimentId: "exp_a",
              error: null,
            },
            {
              label: "strict",
              searchName: "SB",
              mcc: 1.0,
              f1: 0.9,
              precision: 0.9,
              sensitivity: 0.9,
              balancedAccuracy: 0.95,
              experimentId: "exp_b",
              error: null,
            },
          ],
        }}
      />,
    );
    expect(screen.getByTestId("data-scored-comparison")).toBeInTheDocument();
    expect(screen.getByText(/ranked by mcc/i)).toBeInTheDocument();
    // winner badge appears exactly once, on the strict row
    const winner = screen.getByText("winner");
    expect(winner).toBeInTheDocument();
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual([
      "Variant",
      "MCC",
      "F1",
      "Precision",
      "Sensitivity",
      "Balanced accuracy",
    ]);
    const rows = screen.getAllByRole("row").map((r) => r.textContent);
    expect(rows[1]).toBe("lenient0.600.800.800.800.80");
    expect(rows[2]).toBe("strictwinner1.000.900.900.900.95");
  });

  it("names the failure as a failed scoring, not as a bare failure", () => {
    inThread(
      <DataScoredComparison
        data={{
          objective: "mcc",
          winnerLabel: null,
          variants: [
            {
              label: "top 20%",
              searchName: "SA",
              mcc: null,
              f1: null,
              precision: null,
              sensitivity: null,
              balancedAccuracy: null,
              experimentId: null,
              error: "parameters.channel: Input should be a valid string",
              controlHits: ["PF3D7_1116700"],
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByText(
        "scoring failed: parameters.channel: Input should be a valid string",
      ),
    ).toBeInTheDocument();
  });

  it("lists the control ids a variant contains", () => {
    inThread(
      <DataScoredComparison
        data={{
          objective: "mcc",
          winnerLabel: null,
          variants: [
            {
              label: "top 20%",
              searchName: "SA",
              mcc: null,
              f1: null,
              precision: null,
              sensitivity: null,
              balancedAccuracy: null,
              experimentId: null,
              error: "scoring blew up",
              controlHits: ["PF3D7_1116700", "PF3D7_0507500"],
            },
            {
              label: "top 5%",
              searchName: "SB",
              mcc: null,
              f1: null,
              precision: null,
              sensitivity: null,
              balancedAccuracy: null,
              experimentId: null,
              error: "scoring blew up",
              controlHits: [],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("PF3D7_1116700, PF3D7_0507500")).toBeInTheDocument();
    expect(screen.getByText("contains none of the control genes")).toBeInTheDocument();
  });

  it("shows a failed variant's error and no metrics", () => {
    inThread(
      <DataScoredComparison
        data={{
          objective: "mcc",
          winnerLabel: "ok",
          variants: [
            {
              label: "ok",
              searchName: "SA",
              mcc: 0.5,
              f1: 0.5,
              precision: 0.5,
              sensitivity: 0.5,
              balancedAccuracy: 0.5,
              experimentId: "exp_a",
              error: null,
            },
            {
              label: "broken",
              searchName: "SB",
              mcc: null,
              f1: null,
              precision: null,
              sensitivity: null,
              balancedAccuracy: null,
              experimentId: null,
              error: "WDK exploded",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/failed: WDK exploded/i)).toBeInTheDocument();
  });

  it("does not render a winner badge when no variant scored", () => {
    inThread(
      <DataScoredComparison
        data={{
          objective: "mcc",
          winnerLabel: null,
          variants: [
            {
              label: "broken",
              searchName: "SB",
              mcc: null,
              f1: null,
              precision: null,
              sensitivity: null,
              balancedAccuracy: null,
              experimentId: null,
              error: "boom",
            },
          ],
        }}
      />,
    );
    const card = screen.getByTestId("data-scored-comparison");
    expect(within(card).queryByText("winner")).not.toBeInTheDocument();
  });
});
