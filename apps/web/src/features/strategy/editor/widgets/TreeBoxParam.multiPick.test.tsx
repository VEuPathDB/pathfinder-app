// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { TreeBoxParam } from "./TreeBoxParam";
import type { ParamSpec } from "@pathfinder/shared";
import type { VocabNode, VocabOption } from "@/lib/utils/vocab";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

const sampleTree: VocabNode[] = [
  {
    value: "root",
    label: "Root",
    children: [
      {
        value: "branch-a",
        label: "Branch A",
        children: [
          { value: "leaf-1", label: "Leaf 1" },
          { value: "leaf-2", label: "Leaf 2" },
        ],
      },
      {
        value: "branch-b",
        label: "Branch B",
        children: [
          { value: "leaf-3", label: "Leaf 3" },
          { value: "leaf-4", label: "Leaf 4" },
        ],
      },
    ],
  },
];

const flatOptions: VocabOption[] = [
  { label: "Leaf 1", value: "leaf-1" },
  { label: "Leaf 2", value: "leaf-2" },
  { label: "Leaf 3", value: "leaf-3" },
  { label: "Leaf 4", value: "leaf-4" },
];

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "test_tree",
    type: "string",
    displayName: "Test Tree",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    multiPick: true,
    ...overrides,
  };
}

function stateOf(label: string): string | null {
  return screen.getByLabelText(label).getAttribute("data-state");
}

function expandAll(): void {
  fireEvent.click(screen.getByRole("button", { name: "Expand all" }));
}

describe("TreeBoxParam - multi-pick (shadcn checkboxes)", () => {
  it("renders a checkbox for every node once expanded", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expandAll();
    expect(screen.getAllByRole("checkbox").length).toBe(7);
  });

  it("checks a leaf when its value is in the form value", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(stateOf("Leaf 1")).toBe("checked");
  });

  it("clicking a leaf adds it to the form value", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expandAll();
    await user.click(screen.getByLabelText("Leaf 1"));
    expect(stateOf("Leaf 1")).toBe("checked");
  });

  it("clicking a checked leaf removes it from the form value", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1", "leaf-2"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expandAll();
    await user.click(screen.getByLabelText("Leaf 1"));
    expect(stateOf("Leaf 1")).toBe("unchecked");
    expect(stateOf("Leaf 2")).toBe("checked");
  });

  it("clicking a branch selects all its leaf descendants", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expandAll();
    await user.click(screen.getByLabelText("Branch A"));
    expect(stateOf("Leaf 1")).toBe("checked");
    expect(stateOf("Leaf 2")).toBe("checked");
  });

  it("branch checkbox is indeterminate when some children selected", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(stateOf("Branch A")).toBe("indeterminate");
  });

  it("branch checkbox is checked when all children selected", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1", "leaf-2"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(stateOf("Branch A")).toBe("checked");
  });
});

describe("TreeBoxParam - search filter", () => {
  it("renders search input", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByPlaceholderText("Search...")).toBeTruthy();
  });

  it("filters nodes by search term", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    fireEvent.change(screen.getByPlaceholderText("Search..."), {
      target: { value: "Leaf 1" },
    });
    expect(screen.getByText("Leaf 1")).toBeTruthy();
    expect(screen.queryByText("Leaf 3")).toBeNull();
  });
});

describe("TreeBoxParam - a value stored as a parent term", () => {
  /**
   * FRAME binds organism scope as a species-level term, e.g.
   * `organism: ["Plasmodium falciparum"]`, and the backend expands parent
   * terms to leaves at the WDK boundary (`_expand_tree_params_to_leaves`,
   * because WDK silently returns 0 genes for a parent node). The tree only
   * ever matched leaves, so a correctly-scoped step opened showing
   * "0 of 62 selected" on a REQUIRED field - and any interaction would have
   * written the tree's own state over the real scope.
   */

  it("counts a parent term as its leaves", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["branch-a"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expect(screen.getByText(/of 4 selected/)).toHaveTextContent("2 of 4 selected");
  });

  it("checks the parent and its leaves", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["branch-a"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expandAll();
    expect(stateOf("Branch A")).toBe("checked");
    expect(stateOf("Leaf 1")).toBe("checked");
    expect(stateOf("Leaf 2")).toBe("checked");
  });

  it("leaves an unrelated branch alone", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["branch-a"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expandAll();
    expect(stateOf("Branch B")).toBe("unchecked");
    expect(stateOf("Leaf 3")).toBe("unchecked");
  });

  it("marks the root indeterminate when only one branch is stored", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["branch-a"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expect(stateOf("Root")).toBe("indeterminate");
  });

  it("unchecking one leaf of a stored parent keeps the others", async () => {
    // Editing must start from what the tree SHOWS. Filtering the raw
    // ["branch-a"] for "leaf-1" would remove nothing and silently keep the
    // whole branch selected.
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_tree" defaultValue={["branch-a"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expandAll();
    await user.click(screen.getByLabelText("Leaf 1"));

    expect(stateOf("Leaf 1")).toBe("unchecked");
    expect(stateOf("Leaf 2")).toBe("checked");
    expect(screen.getByText("1 of 4 selected")).toBeTruthy();
  });

  it("adding a leaf from another branch keeps the stored branch", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_tree" defaultValue={["branch-a"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expandAll();
    await user.click(screen.getByLabelText("Leaf 3"));

    expect(screen.getByText(/of 4 selected/)).toHaveTextContent("3 of 4 selected");
    expect(stateOf("Branch A")).toBe("checked");
  });

  it("still counts plain leaf values", () => {
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1", "leaf-3"]}>
        {(field) => (
          <TreeBoxParam
            spec={makeSpec()}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );

    expect(screen.getByText(/of 4 selected/)).toHaveTextContent("2 of 4 selected");
  });
});
