/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { ControlTestResults } from "@pathfinder/shared";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataControlTestResults } from "./DataControlTestResults";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const BOTH_SETS: ControlTestResults = {
  taskId: "3d221443-0074-47d8-8300-addadd147989",
  toolCallId: "call_sLwqd6ToSyX9TDfOm62FTIT6",
  targetStepId: 440299573,
  targetLabel: "Genes by Molecular Weight",
  targetEstimatedSize: 132,
  targetParameters: [
    { label: "Organism", value: "Plasmodium falciparum 3D7" },
    { label: "Molecular weight", value: "40000 to 60000" },
  ],
  positive: {
    controlsCount: 3,
    intersectionCount: 2,
    recall: 2 / 3,
    hitIds: ["PF3D7_1222600", "PF3D7_1031000"],
    missedIds: ["PF3D7_0102000"],
  },
  negative: {
    controlsCount: 4,
    intersectionCount: 1,
    falsePositiveRate: 0.25,
    hitIds: ["PF3D7_1133400"],
    missedIds: ["PF3D7_0709000", "PF3D7_0523000", "PF3D7_1343700"],
  },
};

const POSITIVES_ONLY: ControlTestResults = {
  taskId: "b63e66d3-f66f-475c-8b0d-71654ca0baf9",
  toolCallId: "call_leMSWPqGjaZAYzUFYrJvANmc",
  targetStepId: 440299493,
  targetLabel: "Genes by Taxon",
  targetEstimatedSize: 16784,
  positive: { controlsCount: 1, intersectionCount: 0, recall: 0 },
};

function inThread(data: ControlTestResults, children: ReactNode) {
  const messages = threadOf([threadPart("data-control-test-results", data)]);
  return render(
    <ChatHelpersProvider value={chatHelpersFor(messages)}>
      {children}
    </ChatHelpersProvider>,
  );
}

describe("DataControlTestResults", () => {
  it("captions a run with both control sets, numbers and rates", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. Control tests on Genes by Molecular Weight: target 132 records, " +
        "2 of 3 positive controls recovered (recall 0.67), 1 of 4 negative " +
        "controls returned (false-positive rate 0.25).",
    );
  });

  it("omits the set a run did not test", () => {
    inThread(POSITIVES_ONLY, <DataControlTestResults data={POSITIVES_ONLY} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. Control tests on Genes by Taxon: target 16,784 records, " +
        "0 of 1 positive controls recovered (recall 0.00).",
    );
    expect(screen.queryByRole("row", { name: /Negative/ })).not.toBeInTheDocument();
  });

  it("omits a rate the result reports as null", () => {
    const noRate: ControlTestResults = {
      ...POSITIVES_ONLY,
      positive: { controlsCount: 2, intersectionCount: 1, recall: null },
    };
    inThread(noRate, <DataControlTestResults data={noRate} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. Control tests on Genes by Taxon: target 16,784 records, " +
        "1 of 2 positive controls recovered.",
    );
  });

  it("names the tested step when the run could not name it", () => {
    const unnamed: ControlTestResults = { ...POSITIVES_ONLY, targetLabel: "" };
    inThread(unnamed, <DataControlTestResults data={unnamed} />);
    expect(screen.getByTestId("figure-caption").textContent).toContain(
      "Control tests on step 440299493:",
    );
  });

  it("anchors the exhibit and offers its citation control", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);
    expect(screen.getByTestId("figure").getAttribute("id")).toBe("table-1");
    expect(
      screen.getByRole("button", { name: "Copy link to Table 1" }),
    ).toBeInTheDocument();
  });

  it("heads every column of the table and names the measure each row reports", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);

    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Control set", "Controls", "Returned", "Measure", "Value"]);
    const positive = screen.getAllByRole("row")[1];
    expect(positive?.textContent).toBe("Positive32Recall0.67");
    const negative = screen.getAllByRole("row")[2];
    expect(negative?.textContent).toBe("Negative41False-positive rate0.25");
  });

  it("reads the tested step, its size and every criterion it ran", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);

    expect(
      screen.getByText("Genes by Molecular Weight (step 440299573), 132 records"),
    ).toBeInTheDocument();
    expect(screen.getByText("Plasmodium falciparum 3D7")).toBeInTheDocument();
    expect(screen.getByText("40000 to 60000")).toBeInTheDocument();
  });

  it("names an unnamed step once, not twice", () => {
    const unnamed: ControlTestResults = { ...POSITIVES_ONLY, targetLabel: "" };
    inThread(unnamed, <DataControlTestResults data={unnamed} />);

    expect(screen.getByText("step 440299493, 16,784 records")).toBeInTheDocument();
  });

  it("offers the ids behind each count of a control set", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);

    expect(
      screen.getByRole("button", {
        name: "3 positive controls, click to copy the ids",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "2 positive controls the target returned, click to copy the ids",
      }),
    ).toBeInTheDocument();
  });

  it("offers the ids behind each count of the negative set, excluded ones included", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);

    expect(
      screen.getByRole("button", {
        name: "4 negative controls, click to copy the ids",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "1 negative controls the target returned, click to copy the ids",
      }),
    ).toBeInTheDocument();
  });

  it("leaves a count with no ids as a plain number", () => {
    inThread(POSITIVES_ONLY, <DataControlTestResults data={POSITIVES_ONLY} />);

    const positive = screen.getAllByRole("row")[1];
    expect(positive?.textContent).toBe("Positive10Recall0.00");
    expect(
      screen.queryByRole("button", { name: /positive controls, click to copy/ }),
    ).not.toBeInTheDocument();
  });

  it("lists the gene ids behind the counts", () => {
    inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);

    expect(screen.getByText("Positives recovered:")).toBeInTheDocument();
    expect(screen.getByText("PF3D7_1222600, PF3D7_1031000")).toBeInTheDocument();
    expect(screen.getByText("Positives missed:")).toBeInTheDocument();
    expect(screen.getByText("PF3D7_0102000")).toBeInTheDocument();
    expect(screen.getByText("Negatives returned:")).toBeInTheDocument();
    expect(screen.getByText("PF3D7_1133400")).toBeInTheDocument();
    expect(screen.getByText("Negatives excluded:")).toBeInTheDocument();
    expect(
      screen.getByText("PF3D7_0709000, PF3D7_0523000, PF3D7_1343700"),
    ).toBeInTheDocument();
  });

  it("lists no excluded negatives for a run that tested no negative set", () => {
    inThread(POSITIVES_ONLY, <DataControlTestResults data={POSITIVES_ONLY} />);

    expect(screen.queryByText("Negatives excluded:")).not.toBeInTheDocument();
  });

  it("counts the ids it does not list", () => {
    const many = Array.from({ length: 12 }, (_, index) => `PF3D7_100000${index}`);
    const wide: ControlTestResults = {
      ...BOTH_SETS,
      positive: { controlsCount: 12, intersectionCount: 12, recall: 1, hitIds: many },
    };
    inThread(wide, <DataControlTestResults data={wide} />);

    expect(screen.getByText("and 4 more")).toBeInTheDocument();
  });

  it("keeps the monospace face for gene ids alone", () => {
    const view = inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);

    const mono = [...view.container.querySelectorAll(".font-mono")].map(
      (node) => node.textContent,
    );
    expect(mono).toEqual([
      "PF3D7_1222600, PF3D7_1031000",
      "PF3D7_0102000",
      "PF3D7_1133400",
      "PF3D7_0709000, PF3D7_0523000, PF3D7_1343700",
    ]);
  });

  it("carries no JSON", () => {
    const view = inThread(BOTH_SETS, <DataControlTestResults data={BOTH_SETS} />);
    expect(view.container.textContent).not.toContain("{");
  });
});
