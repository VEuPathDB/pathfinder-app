// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { ParamSpec } from "@pathfinder/shared";

import { EdaSpecParam } from "./EdaSpecParam";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

const SPEC_VALUE = JSON.stringify({
  studyId: "DS_45abf80334",
  displayName: "Genes upregulated at 24 h post blood meal versus 1",
  descriptor: {
    subset: {
      descriptor: [
        {
          entityId: "ENT_8151325d",
          variableId: "VAR_bb8eb17c",
          type: "stringSet",
          stringSet: ["Midgut"],
        },
        {
          entityId: "ENT_8151325d",
          variableId: "VAR_0c6d3e07",
          type: "numberRange",
          min: 24,
          max: 48,
        },
      ],
    },
    computations: [],
  },
});

const PARAM: ParamSpec = {
  name: "eda_analysis_spec",
  type: "string",
  displayName: "Filter genes based on phenotype data",
  allowEmptyValue: true,
  isVisible: true,
  isNumber: false,
  countOnlyLeaves: false,
};

function renderWidget(value: string) {
  const writes: (string | string[])[] = [];
  render(
    <WidgetTestForm name="eda_analysis_spec" defaultValue={value}>
      {(field) => (
        <EdaSpecParam
          spec={PARAM}
          name="eda_analysis_spec"
          options={[]}
          vocabTree={null}
          field={{
            ...field,
            handleChange: (next) => {
              writes.push(next);
              field.handleChange(next);
            },
            handleBlur: vi.fn(),
          }}
        />
      )}
    </WidgetTestForm>,
  );
  return writes;
}

function editor(): HTMLTextAreaElement {
  return screen.getByLabelText<HTMLTextAreaElement>("Analysis spec JSON");
}

describe("EdaSpecParam", () => {
  it("summarises the analysis the spec describes", () => {
    renderWidget(SPEC_VALUE);

    const summary = screen.getByTestId("eda-spec-summary");
    expect(summary).toHaveTextContent(
      "Genes upregulated at 24 h post blood meal versus 1",
    );
    expect(summary).toHaveTextContent("DS_45abf80334");
    expect(
      screen.getAllByTestId("eda-spec-filter").map((line) => line.textContent),
    ).toEqual(["VAR_bb8eb17c: Midgut", "VAR_0c6d3e07: 24 to 48"]);
    expect(screen.getByTestId("eda-spec-computations")).toHaveTextContent(
      "0 computations",
    );
    expect(JSON.parse(editor().value)).toEqual(JSON.parse(SPEC_VALUE));
    expect(editor().value).toContain("\n");
  });

  it("writes a valid edit as compact JSON", () => {
    const writes = renderWidget(SPEC_VALUE);
    const edited = JSON.parse(SPEC_VALUE) as { displayName: string };
    edited.displayName = "Midgut only";

    fireEvent.change(editor(), { target: { value: JSON.stringify(edited, null, 2) } });

    expect(writes).toEqual([JSON.stringify(edited)]);
    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent("Midgut only");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("refuses an invalid edit and says why", () => {
    const writes = renderWidget(SPEC_VALUE);

    fireEvent.change(editor(), { target: { value: '{"studyId": "DS_45abf80334",' } });
    expect(screen.getByRole("alert").textContent).toMatch(/^Not valid JSON/);

    fireEvent.change(editor(), {
      target: { value: '{"studyId": "DS_45abf80334", "descriptor": {}}' },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("descriptor.subset");

    expect(writes).toEqual([]);
    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent(
      "Genes upregulated at 24 h post blood meal versus 1",
    );
  });
});
