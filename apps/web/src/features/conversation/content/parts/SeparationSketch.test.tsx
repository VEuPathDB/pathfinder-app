/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { SeparationSketch } from "./SeparationSketch";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const TASK = "4d3dc4f9-9400-4e7c-9a81-994c53c60682";

function progress(toolSpecific: object) {
  return threadPart("data-task-progress", {
    taskId: TASK,
    message: "m",
    percent: 0.5,
    toolSpecific,
  });
}

function measured(candidateId: string, displayName: string, basis: string) {
  return progress({
    candidateId,
    search: "GenesByGoTerm",
    displayName,
    basis,
    recovered: 42,
    admitted: 0,
    size: 637,
  });
}

function renderSketch(parts: ReturnType<typeof threadPart>[]) {
  return render(
    <ChatHelpersProvider value={chatHelpersFor(threadOf(parts))}>
      <SeparationSketch taskId={TASK} />
    </ChatHelpersProvider>,
  );
}

describe("SeparationSketch", () => {
  it("lists each search as it is measured, in the order it arrived", () => {
    renderSketch([
      progress({ bySource: { catalog: 2 } }),
      measured("c4", "GO Term", "GO:0044217 other organism part"),
      progress({
        candidateId: "c9",
        search: "GenesByText",
        displayName: "Text (product name, notes, etc.)",
        basis: "rifin",
        refused: "the step has no count",
      }),
    ]);

    expect(
      screen.getAllByTestId("separation-sketch-search").map((row) => row.textContent),
    ).toEqual([
      "GO Term: GO:0044217 other organism part - 42 positives, 0 negatives",
      "Text (product name, notes, etc.): rifin - refused by the site",
    ]);
    expect(screen.queryByTestId("separation-sketch-tree")).toBeNull();
  });

  it("draws the assembled combination once the run has one", () => {
    renderSketch([
      measured("c4", "GO Term", "GO:0044217 other organism part"),
      measured("c16", "Gene Lists from Pexel motif analysis", "the site's catalog"),
      progress({
        mode: "exact",
        leaves: 2,
        tree: {
          kind: "combine",
          candidateId: null,
          operator: "UNION",
          inputs: [
            { kind: "leaf", candidateId: "c4", operator: null, inputs: [] },
            { kind: "leaf", candidateId: "c16", operator: null, inputs: [] },
          ],
        },
      }),
    ]);

    const tree = screen.getByTestId("separation-sketch-tree");
    expect(
      within(tree)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "UnionGO Term: GO:0044217 other organism partGene Lists from Pexel motif analysis: the site's catalog",
      "GO Term: GO:0044217 other organism part",
      "Gene Lists from Pexel motif analysis: the site's catalog",
    ]);
    expect(screen.queryAllByTestId("separation-sketch-search")).toHaveLength(0);
  });

  it("draws nothing before the first search is measured", () => {
    const { container } = renderSketch([progress({ bySource: { catalog: 2 } })]);

    expect(container.childElementCount).toBe(0);
  });
});
