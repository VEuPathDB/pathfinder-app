// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("EditorHeader copy action", () => {
  it("names the action for what it does on a search step", async () => {
    renderHeader("search");
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));

    const item = await screen.findByRole("menuitem", { name: "Intersect with a copy" });
    expect(item).toHaveAttribute(
      "title",
      "Adds a copy of this step and intersects it with the original, so the copy's parameters can be changed.",
    );
    expect(screen.queryByRole("menuitem", { name: /duplicate/i })).toBeNull();
  });

  it.each(["combine", "transform"] as const)(
    "offers no copy of a %s step",
    async (kind) => {
      renderHeader(kind);
      await userEvent.click(screen.getByRole("button", { name: "More actions" }));

      await screen.findByRole("menuitem", { name: "Copy step URL" });
      expect(
        screen.queryByRole("menuitem", { name: "Intersect with a copy" }),
      ).toBeNull();
    },
  );
});
