// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
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

describe("TreeBoxParam -- flat fallback", () => {
  it("delegates to CheckboxParam when vocabTree is null (multi)", () => {
    const spec = makeSpec({ multiPick: true });
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1"]}>
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBe(5);
    expect(screen.getByText("Leaf 1")).toBeTruthy();
  });

  it("delegates to CheckboxParam when vocabTree is null (single)", () => {
    const spec = makeSpec({ multiPick: false });
    render(
      <WidgetTestForm name="test_tree" defaultValue="leaf-2">
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBe(4);
    expect(screen.getByLabelText("Leaf 2").getAttribute("data-state")).toBe("checked");
  });
});

describe("TreeBoxParam -- tree rendering", () => {
  it("renders the tree with root and branches visible", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("Root")).toBeTruthy();
    expect(screen.getByText("Branch A")).toBeTruthy();
    expect(screen.getByText("Branch B")).toBeTruthy();
  });

  it("shows leaves when branches are expanded by default", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("Leaf 1")).toBeTruthy();
    expect(screen.getByText("Leaf 4")).toBeTruthy();
  });

  it("shows selection count footer", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_tree" defaultValue={["leaf-1", "leaf-3"]}>
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("2 of 4 selected")).toBeTruthy();
  });

  it("shows '0 of N selected' when none selected", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("0 of 4 selected")).toBeTruthy();
  });
});

describe("TreeBoxParam -- expand/collapse", () => {
  it("collapses a branch when its chevron is clicked", () => {
    const spec = makeSpec();
    render(
      <WidgetTestForm name="test_tree" defaultValue={[]}>
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("Leaf 1")).toBeTruthy();
    const branchALabel = screen.getByText("Branch A");
    const branchARow = branchALabel.closest("[data-node-row]");
    const toggleBtn = branchARow?.querySelector("button");
    fireEvent.click(toggleBtn!);
    expect(screen.queryByText("Leaf 1")).toBeNull();
    expect(screen.getByText("Leaf 3")).toBeTruthy();
  });
});

describe("TreeBoxParam -- single-pick (radios)", () => {
  it("renders radio buttons when spec is not multi", () => {
    const spec = makeSpec({ multiPick: false });
    render(
      <WidgetTestForm name="test_tree" defaultValue="leaf-2">
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBe(4);
  });

  it("selects the radio matching the form value", () => {
    const spec = makeSpec({ multiPick: false });
    render(
      <WidgetTestForm name="test_tree" defaultValue="leaf-2">
        {(field) => (
          <TreeBoxParam
            spec={spec}
            name="test_tree"
            options={flatOptions}
            vocabTree={sampleTree}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByLabelText("Leaf 2").getAttribute("data-state")).toBe("checked");
  });
});
