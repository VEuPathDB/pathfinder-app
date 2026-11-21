// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useStore } from "@tanstack/react-form";
import { SearchTransformBody } from "./SearchTransformBody";
import { useParamForm } from "./hooks/useParamForm";
import { makeSpec } from "./integration/fixtures";
import type { StepEditorState } from "./useStepEditorState";
import type { ParamSpec, Step } from "@strategist/shared";

afterEach(cleanup);

const noop = (): void => {};

const STEP: Step = {
  id: "step-1",
  kind: "search",
  searchName: "GenesByTaxon",
  recordType: "transcript",
  displayName: "Genes by taxon",
  isFiltered: false,
};

function makeState(overrides: Partial<StepEditorState>): StepEditorState {
  const base = {
    paramSpecs: [],
    paramSpecsError: null,
    stepValidationError: null,
    selectedSearch: null,
    searchOptions: [],
    recordTypeOptions: [],
    form: {
      getFieldMeta: () => undefined,
    },
  } as unknown as StepEditorState;
  return { ...base, ...overrides };
}

describe("SearchTransformBody - paramSpecsError surfacing", () => {
  it("renders the failure banner when paramSpecsError is set", () => {
    const state = makeState({
      paramSpecsError: new Error("validation failed: organism is not a leaf"),
    });

    render(
      <SearchTransformBody
        state={state}
        step={STEP}
        onSearchChange={noop}
        onFieldChanged={noop}
        onFieldBlurred={noop}
      />,
    );

    const alert = screen.getByTestId("param-specs-error");
    expect(alert).toHaveTextContent("Failed to load parameters for this search.");
    expect(alert).toHaveTextContent("validation failed: organism is not a leaf");
    expect(
      screen.queryByText("No parameter options available for this search."),
    ).toBeNull();
  });

  it("does NOT render the failure banner when paramSpecsError is null", () => {
    const state = makeState({ paramSpecsError: null, paramSpecsSettled: true });

    render(
      <SearchTransformBody
        state={state}
        step={STEP}
        onSearchChange={noop}
        onFieldChanged={noop}
        onFieldBlurred={noop}
      />,
    );

    expect(screen.queryByTestId("param-specs-error")).toBeNull();
    expect(
      screen.getByText("No parameter options available for this search."),
    ).toBeInTheDocument();
  });
});

describe("an empty parameter list only means empty once it is known", () => {
  const EMPTY = "No parameter options available for this search.";

  function renderBody(overrides: Partial<StepEditorState>) {
    return render(
      <SearchTransformBody
        state={makeState(overrides)}
        step={STEP}
        onSearchChange={noop}
        onFieldChanged={noop}
        onFieldBlurred={noop}
      />,
    );
  }

  it("shows a placeholder while the specs are loading", () => {
    renderBody({ isLoading: true });

    expect(screen.getByTestId("param-specs-loading")).toBeInTheDocument();
  });

  it("does not claim the search has no parameters while loading", () => {
    renderBody({ isLoading: true });

    expect(screen.queryByText(EMPTY)).toBe(null);
  });

  it("does not claim the search has no parameters before a fetch runs", () => {
    // A disabled query returns no data, no error and no loading flag. That is
    // an absence of an answer, not an answer.
    renderBody({ isLoading: false, paramSpecsSettled: false });

    expect(screen.queryByText(EMPTY)).toBe(null);
  });

  it("says so when a completed fetch returned nothing", () => {
    renderBody({ isLoading: false, paramSpecsSettled: true, paramSpecs: [] });

    expect(screen.getByText(EMPTY)).toBeInTheDocument();
  });

  it("draws no field for the parameter that wires the step's input", () => {
    const inputStep: ParamSpec = {
      name: "gene_result",
      type: "input-step",
      displayName: "Input Result",
      displayType: "",
      allowEmptyValue: true,
      isVisible: true,
      isNumber: false,
      countOnlyLeaves: false,
      initialDisplayValue: "",
    };
    renderBody({ isLoading: false, paramSpecsSettled: true, paramSpecs: [inputStep] });

    expect(screen.queryByText("Input Result")).toBe(null);
    expect(screen.getByText(EMPTY)).toBeInTheDocument();
  });

  it("prefers the error over the loading placeholder", () => {
    renderBody({ isLoading: true, paramSpecsError: new Error("boom") });

    expect(screen.getByTestId("param-specs-error")).toBeInTheDocument();
    expect(screen.queryByTestId("param-specs-loading")).toBeNull();
  });
});

function BodyWithForm({ specs }: { specs: ParamSpec[] }) {
  const { form } = useParamForm(specs);
  const values = useStore(form.store, (s) => s.values);
  const state = makeState({
    paramSpecs: specs,
    paramSpecsSettled: true,
    isLoading: false,
    form,
    vocabOptions: {},
    dependentOptions: {},
    dependentLoading: {},
    dependentErrors: {},
  });
  return (
    <>
      <SearchTransformBody
        state={state}
        step={STEP}
        onSearchChange={noop}
        onFieldChanged={noop}
        onFieldBlurred={noop}
      />
      <output data-testid="organism-value">{String(values["organism"])}</output>
    </>
  );
}

describe("a read-only parameter is shown but not edited", () => {
  const readOnly = makeSpec({
    name: "organism",
    displayName: "Organism",
    isReadOnly: true,
    initialDisplayValue: "Plasmodium falciparum 3D7",
  });
  const editable = makeSpec({ name: "text_expression", displayName: "Text" });

  it("draws the read-only parameter with the site's value", () => {
    render(<BodyWithForm specs={[readOnly, editable]} />);

    expect(screen.getByText("Organism")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Plasmodium falciparum 3D7")).toBeInTheDocument();
  });

  it("disables the read-only parameter's field", () => {
    render(<BodyWithForm specs={[readOnly, editable]} />);

    expect(screen.getByDisplayValue("Plasmodium falciparum 3D7")).toBeDisabled();
  });

  it("keeps the site's value when a change is attempted", () => {
    render(<BodyWithForm specs={[readOnly, editable]} />);

    fireEvent.change(screen.getByDisplayValue("Plasmodium falciparum 3D7"), {
      target: { value: "Plasmodium vivax" },
    });

    expect(screen.getByTestId("organism-value")).toHaveTextContent(
      "Plasmodium falciparum 3D7",
    );
  });

  it("leaves an ordinary parameter enabled", () => {
    render(<BodyWithForm specs={[readOnly, editable]} />);

    const inputs = screen.getAllByRole("textbox");
    const text = inputs.find(
      (input) => input.getAttribute("name") === "text_expression",
    );
    expect(text).toBeEnabled();
  });

  it("names the disabled group of a read-only field after its label", () => {
    render(<BodyWithForm specs={[readOnly, editable]} />);

    expect(screen.getByRole("group", { name: "Organism" })).toBeDisabled();
  });

  it("puts an editable field in no group", () => {
    render(<BodyWithForm specs={[editable]} />);

    expect(screen.queryByRole("group")).toBe(null);
  });

  it("gives the read-only group a box with no border, padding or margin", () => {
    render(<BodyWithForm specs={[readOnly, editable]} />);

    const group = screen.getByRole("group", { name: "Organism" });
    expect([...group.classList].sort()).toEqual(["border-0", "m-0", "min-w-0", "p-0"]);
  });
});

describe("a read-only tree can be opened but not changed", () => {
  const tree = makeSpec({
    name: "organism",
    displayName: "Organism",
    type: "multi-pick-vocabulary",
    displayType: "treeBox",
    multiPick: true,
    allowMultipleValues: true,
    isReadOnly: true,
    initialDisplayValue: '["leaf-3","leaf-4"]',
    vocabulary: {
      data: { term: "@@fake@@", display: "@@fake@@" },
      children: [
        {
          data: { term: "branch-b", display: "Branch B" },
          children: [
            { data: { term: "leaf-3", display: "Leaf 3" }, children: [] },
            { data: { term: "leaf-4", display: "Leaf 4" }, children: [] },
          ],
        },
        { data: { term: "leaf-5", display: "Leaf 5" }, children: [] },
      ],
    },
  });

  it("keeps the read-only tree a group named after its label", () => {
    render(<BodyWithForm specs={[tree]} />);

    expect(screen.getByRole("group", { name: "Organism" })).toBeInTheDocument();
  });

  it("expands on click and shows the selected leaf", async () => {
    render(<BodyWithForm specs={[tree]} />);

    await userEvent.click(screen.getByRole("button", { name: "Expand" }));

    expect(screen.getByRole("checkbox", { name: "Leaf 3" })).toBeChecked();
  });

  it("disables every selection checkbox", async () => {
    render(<BodyWithForm specs={[tree]} />);

    await userEvent.click(screen.getByRole("button", { name: "Expand all" }));

    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(5);
    for (const box of boxes) expect(box).toBeDisabled();
  });

  it("keeps the search box usable", () => {
    render(<BodyWithForm specs={[tree]} />);

    expect(screen.getByPlaceholderText("Search...")).toBeEnabled();
  });

  it("changes nothing in the form when a leaf is clicked", async () => {
    render(<BodyWithForm specs={[tree]} />);

    await userEvent.click(screen.getByRole("checkbox", { name: "Leaf 5" }));

    expect(screen.getByTestId("organism-value")).toHaveTextContent("leaf-3,leaf-4");
  });
});
