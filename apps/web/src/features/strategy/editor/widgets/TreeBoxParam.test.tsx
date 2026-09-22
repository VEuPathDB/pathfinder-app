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

  it("opens a lone root one level and no deeper when nothing is selected", () => {
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
    expect(screen.getByText("Branch A")).toBeTruthy();
    expect(screen.queryByText("Leaf 1")).toBeNull();
    expect(screen.queryByText("Leaf 4")).toBeNull();
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
    expect(screen.getByRole("checkbox", { name: "Leaf 1" })).toBeTruthy();
    const branchALabel = screen.getByText("Branch A");
    const branchARow = branchALabel.closest("[data-node-row]");
    const toggleBtn = branchARow?.querySelector("button");
    fireEvent.click(toggleBtn!);
    expect(screen.queryByRole("checkbox", { name: "Leaf 1" })).toBeNull();
    expect(screen.getByRole("checkbox", { name: "Leaf 3" })).toBeTruthy();
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
    expect(
      screen.getAllByRole("radio").map((r) => r.getAttribute("aria-label")),
    ).toEqual(["Leaf 1", "Leaf 2"]);
    fireEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(screen.getAllByRole("radio").length).toBe(4);
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

const userTree: VocabNode[] = [
  {
    value: "a",
    label: "A",
    children: [
      {
        value: "b",
        label: "B",
        children: [
          { value: "c", label: "C" },
          { value: "d", label: "D" },
        ],
      },
      { value: "e", label: "E" },
    ],
  },
];

function renderTree(tree: VocabNode[], defaultValue: string[]) {
  render(
    <WidgetTestForm name="test_tree" defaultValue={defaultValue}>
      {(field) => (
        <TreeBoxParam
          spec={makeSpec()}
          name="test_tree"
          options={flatOptions}
          vocabTree={tree}
          field={field}
        />
      )}
    </WidgetTestForm>,
  );
}

function caretOf(label: string): HTMLElement {
  const button = screen
    .getByText(label)
    .closest("[data-node-row]")
    ?.querySelector("button");
  if (!(button instanceof HTMLElement)) throw new Error(`no caret on ${label}`);
  return button;
}

describe("TreeBoxParam -- least depth that shows the selection", () => {
  it("renders a fully selected branch checked and collapsed under an open parent", () => {
    renderTree(userTree, ["c", "d"]);
    expect(screen.getByLabelText("B").getAttribute("data-state")).toBe("checked");
    expect(screen.getByLabelText("A").getAttribute("data-state")).toBe("indeterminate");
    expect(caretOf("B").getAttribute("aria-label")).toBe("Expand");
    expect(screen.getByText("E")).toBeTruthy();
    expect(screen.queryByText("C")).toBeNull();
  });

  it("keeps a branch the user opened open across a selection change", () => {
    renderTree(userTree, ["c", "d"]);
    fireEvent.click(caretOf("B"));
    expect(screen.getByText("C")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("C"));
    fireEvent.click(screen.getByLabelText("C"));
    expect(screen.getByLabelText("B").getAttribute("data-state")).toBe("checked");
    expect(screen.getByText("C")).toBeTruthy();
  });

  it("opens the path to a deep selected leaf on Expand selected", () => {
    renderTree(userTree, ["c", "d"]);
    fireEvent.click(screen.getByRole("button", { name: "Expand selected" }));
    expect(screen.getByLabelText("C").getAttribute("data-state")).toBe("checked");
  });

  it("hides every branch on Collapse all", () => {
    renderTree(userTree, ["c"]);
    expect(screen.getByRole("checkbox", { name: "C" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByRole("checkbox", { name: "B" })).toBeNull();
  });

  it("shows a search match under a collapsed branch", () => {
    const deep: VocabNode[] = [
      {
        value: "x",
        label: "Xray",
        children: [
          {
            value: "y",
            label: "Yankee",
            children: [
              {
                value: "z",
                label: "Zulu",
                children: [
                  { value: "n", label: "Needle" },
                  { value: "h", label: "Hay" },
                ],
              },
            ],
          },
        ],
      },
    ];
    renderTree(deep, []);
    expect(screen.queryByText("Needle")).toBeNull();
    fireEvent.change(screen.getByPlaceholderText("Search..."), {
      target: { value: "need" },
    });
    expect(screen.getByText("Needle")).toBeTruthy();
    expect(screen.queryByText("Hay")).toBeNull();
  });

  it("names the selection by its smallest cover in the footer", () => {
    renderTree(userTree, ["c", "d"]);
    expect(screen.getByText("2 of 3 selected")).toBeTruthy();
    expect(
      screen.getAllByTestId("treebox-summary-chip").map((chip) => chip.textContent),
    ).toEqual(["B (all 2)"]);
  });

  it("caps the chips at twelve and counts the rest", () => {
    const wide: VocabNode[] = Array.from({ length: 15 }, (_, i) => ({
      value: `p${String(i)}`,
      label: `P${String(i)}`,
      children: [{ value: `q${String(i)}`, label: `Q${String(i)}` }],
    }));
    renderTree(
      wide,
      wide.map((_, i) => `q${String(i)}`),
    );
    expect(screen.getAllByTestId("treebox-summary-chip").length).toBe(12);
    expect(screen.getByText("+3 more")).toBeTruthy();
  });
});

const siblingTree: VocabNode[] = [
  {
    value: "a",
    label: "A",
    children: [
      {
        value: "b",
        label: "B",
        children: [
          { value: "c", label: "C" },
          { value: "d", label: "D" },
        ],
      },
      {
        value: "f",
        label: "F",
        children: [
          { value: "g", label: "G" },
          { value: "h", label: "H" },
        ],
      },
    ],
  },
];

describe("TreeBoxParam -- the area a click works in keeps its shape", () => {
  it("keeps a branch open when its last leaf is ticked and when it is emptied", () => {
    renderTree(userTree, ["c"]);
    fireEvent.click(screen.getByLabelText("D"));
    expect(screen.getByLabelText("B").getAttribute("data-state")).toBe("checked");
    expect(screen.getByRole("checkbox", { name: "C" })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "D" })).toBeTruthy();
    fireEvent.click(screen.getByLabelText("C"));
    fireEvent.click(screen.getByLabelText("D"));
    expect(screen.getByLabelText("B").getAttribute("data-state")).toBe("unchecked");
    expect(screen.getByRole("checkbox", { name: "C" })).toBeTruthy();
  });

  it("lets an untouched sibling branch follow the selection", () => {
    renderTree(siblingTree, ["c", "g"]);
    fireEvent.click(screen.getByLabelText("D"));
    expect(screen.getByRole("checkbox", { name: "G" })).toBeTruthy();
    fireEvent.click(screen.getByLabelText("A"));
    expect(screen.getByLabelText("A").getAttribute("data-state")).toBe("checked");
    expect(screen.getByRole("checkbox", { name: "C" })).toBeTruthy();
    expect(screen.getByLabelText("F").getAttribute("data-state")).toBe("checked");
    expect(screen.queryByRole("checkbox", { name: "G" })).toBeNull();
  });
});

describe("TreeBoxParam -- carets during a search", () => {
  it("ignores a caret click while a search is active", () => {
    renderTree(userTree, ["c"]);
    const search = screen.getByPlaceholderText("Search...");
    fireEvent.change(search, { target: { value: "c" } });
    fireEvent.click(caretOf("B"));
    expect(screen.getByRole("checkbox", { name: "C" })).toBeTruthy();
    fireEvent.change(search, { target: { value: "" } });
    expect(caretOf("B").getAttribute("aria-label")).toBe("Collapse");
    expect(screen.getByRole("checkbox", { name: "D" })).toBeTruthy();
  });
});
