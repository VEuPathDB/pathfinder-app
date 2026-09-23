// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SearchTransformBody } from "./SearchTransformBody";
import type { StepEditorState } from "./useStepEditorState";
import type { ParamSpec, Step } from "@pathfinder/shared";

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
