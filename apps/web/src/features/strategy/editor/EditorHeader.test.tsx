// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Step, StepKind } from "@pathfinder/shared";
import { EditorHeader } from "./EditorHeader";

const STEP: Step = {
  id: "s1",
  kind: "search",
  displayName: "Genes by taxon",
  searchName: "GenesByTaxon",
  recordType: "gene",
  parameters: {},
  isFiltered: false,
};

function renderHeader(kind: StepKind) {
  return render(
    <EditorHeader
      step={STEP}
      kind={kind}
      stepNumber={1}
      onRename={() => {}}
      onDelete={() => {}}
      onDuplicate={() => {}}
      onCopyUrl={() => {}}
      onSaveAsReusable={() => {}}
    />,
  );
}

describe("EditorHeader kind badge", () => {
  it("tints the search badge from the leaf kind token", () => {
    renderHeader("search");
    expect(screen.getByText("search")).toHaveClass(
      "bg-[hsl(var(--kind-leaf)/0.15)]",
      "text-foreground",
    );
  });

  it("tints the combine badge from the combine kind token", () => {
    renderHeader("combine");
    expect(screen.getByText("combine")).toHaveClass(
      "bg-[hsl(var(--kind-combine)/0.15)]",
      "text-foreground",
    );
  });

  it("tints the transform badge from the transform kind token", () => {
    renderHeader("transform");
    expect(screen.getByText("transform")).toHaveClass(
      "bg-[hsl(var(--kind-transform)/0.15)]",
      "text-foreground",
    );
  });
});

describe("EditorHeader subtitle", () => {
  it("shows the request's words beneath the name of the search that runs", () => {
    render(
      <EditorHeader
        step={{
          ...STEP,
          displayName: "Exported Protein",
          criterionText: "genes with a predicted GPI anchor",
        }}
        kind="search"
        stepNumber={1}
        onRename={() => {}}
        onDelete={() => {}}
        onDuplicate={() => {}}
        onCopyUrl={() => {}}
        onSaveAsReusable={() => {}}
      />,
    );

    expect(screen.getByLabelText("Step name")).toHaveValue("Exported Protein");
    expect(screen.getByTestId("step-editor-subtitle")).toHaveTextContent(
      "genes with a predicted GPI anchor",
    );
  });

  it("shows no subtitle for a step that carries no words", () => {
    renderHeader("search");

    expect(screen.getByLabelText("Step name")).toHaveValue("Genes by taxon");
    expect(screen.queryByTestId("step-editor-subtitle")).toBeNull();
  });
});
