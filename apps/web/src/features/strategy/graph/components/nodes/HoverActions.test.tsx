// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Step } from "@pathfinder/shared";

import { HoverActions } from "./HoverActions";

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    kind: "search",
    displayName: "Genes by taxon",
    searchName: "GenesByTaxon",
    recordType: "gene",
    parameters: {},
    estimatedSize: 100,
    isFiltered: false,
    validation: null,
    ...overrides,
  };
}

afterEach(cleanup);

describe("HoverActions delete affordance", () => {
  it("the kebab 'Delete step' invokes onDelete once with the exact step id", async () => {
    const onDelete = vi.fn();
    render(
      <HoverActions step={makeStep({ id: "interpro_or_go" })} onDelete={onDelete} />,
    );

    await userEvent.click(screen.getByTestId("rf-more-interpro_or_go"));
    await userEvent.click(
      await screen.findByRole("menuitem", { name: /delete step/i }),
    );

    expect(onDelete.mock.calls).toEqual([["interpro_or_go"]]);
  });

  it("the kebab 'Intersect with a copy' invokes onDuplicate once with the exact step id", async () => {
    const onDuplicate = vi.fn();
    render(
      <HoverActions
        step={makeStep({ id: "interpro_kinases" })}
        onDuplicate={onDuplicate}
      />,
    );

    await userEvent.click(screen.getByTestId("rf-more-interpro_kinases"));
    const item = await screen.findByRole("menuitem", { name: "Intersect with a copy" });
    expect(item).toHaveAttribute(
      "title",
      "Adds a copy of this step and intersects it with the original, so the copy's parameters can be changed.",
    );
    await userEvent.click(item);

    expect(onDuplicate.mock.calls).toEqual([["interpro_kinases"]]);
  });

  it("offers no copy of a combine, whose copy would have no inputs", async () => {
    render(
      <HoverActions
        step={makeStep({
          id: "c1",
          kind: "combine",
          operator: "UNION",
          primaryInputStepId: "a",
          secondaryInputStepId: "b",
        })}
        onDuplicate={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByTestId("rf-more-c1"));
    const labels = (await screen.findAllByRole("menuitem")).map((el) =>
      el.textContent.trim(),
    );
    expect(labels).not.toContain("Intersect with a copy");
  });

  it("offers no destructive action when its handlers are unwired", async () => {
    render(<HoverActions step={makeStep({ id: "s2" })} />);
    await userEvent.click(screen.getByTestId("rf-more-s2"));
    const labels = (await screen.findAllByRole("menuitem")).map((el) =>
      el.textContent.trim(),
    );
    expect(labels).toContain("Copy step ID");
    expect(labels).not.toContain("Delete step");
    expect(labels).not.toContain("Intersect with a copy");
  });

  it("nests the kebab inside the toolbar the onNodeClick guard keys on", () => {
    render(<HoverActions step={makeStep({ id: "s3" })} onDelete={vi.fn()} />);
    const kebab = screen.getByTestId("rf-more-s3");
    expect(kebab.closest("[data-node-toolbar]")).not.toBe(null);
  });
});
