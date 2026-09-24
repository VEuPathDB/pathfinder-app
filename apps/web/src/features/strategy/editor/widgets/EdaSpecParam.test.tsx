// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { ParamSpec } from "@pathfinder/shared";

import { EdaSpecParam } from "./EdaSpecParam";
import { parseEdaSpec } from "./edaSpecLogic";
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

// An analysis the site's own EDA app edited: a pass compute that holds a
// histogram, beside a differential expression that holds a volcano.
const SITE_EDITED_VALUE = JSON.stringify({
  studyId: "DS_e973eadd57",
  displayName: "veupathdb-py fixture analysis_detail_pass_and_de",
  descriptor: {
    subset: { descriptor: [] },
    computations: [
      {
        computationId: "k3x9q",
        descriptor: { type: "pass" },
        visualizations: [
          {
            visualizationId: "0b6f1c2e-5a3d-4e8f-9c71-2d4a6b8e0f13",
            displayName: "Unnamed visualization",
            descriptor: {
              type: "histogram",
              configuration: {
                valueSpec: "count",
                xAxisVariable: { entityId: "ENT_8151325d", variableId: "VAR_7033e90f" },
              },
              currentPlotFilters: [],
            },
          },
        ],
      },
      {
        computationId: "m7p2d",
        displayName: "Unnamed computation",
        descriptor: {
          type: "differentialexpression",
          configuration: {
            identifierVariable: {
              entityId: "ENT_fd574cd6",
              variableId: "VEUPATHDB_GENE_ID",
            },
            valueVariable: {
              entityId: "ENT_fd574cd6",
              variableId: "SEQUENCE_READ_COUNT_ANTISENSE",
            },
            comparator: {
              variable: { entityId: "ENT_8151325d", variableId: "VAR_081ab087" },
              groupA: [{ label: "normal" }],
              groupB: [{ label: "febrile" }],
            },
            differentialExpressionMethod: "DESeq",
            pValueFloor: "1e-200",
          },
        },
        visualizations: [
          {
            visualizationId: "7e2c4a91-3b5d-4f60-8a1e-9c0d2b4f6a85",
            displayName: "Unnamed visualization",
            descriptor: {
              type: "volcanoplot",
              configuration: {
                effectSizeThreshold: 1,
                significanceThreshold: 0.05,
                markerBodyOpacity: 0.5,
                effectDirection: "upAndDown",
              },
              currentPlotFilters: [],
            },
          },
        ],
      },
    ],
  },
});

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

  it("takes a pass computation beside the comparison", () => {
    renderWidget(SITE_EDITED_VALUE);

    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent("DS_e973eadd57");
    expect(screen.getByTestId("eda-spec-computations")).toHaveTextContent(
      "2 computations",
    );
    expect(screen.queryByRole("alert")).toBeNull();
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
    expect(screen.getByRole("alert")).toHaveTextContent(/^displayName: /);

    expect(writes).toEqual([]);
    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent(
      "Genes upregulated at 24 h post blood meal versus 1",
    );
  });
});

describe("parseEdaSpec", () => {
  const subset = { subset: { descriptor: [] }, computations: [] };

  it("refuses the documents the backend's model refuses", () => {
    const noName = parseEdaSpec(
      JSON.stringify({ studyId: "DS_45abf80334", descriptor: subset }),
    );
    const numberComputation = parseEdaSpec(
      JSON.stringify({
        studyId: "DS_45abf80334",
        displayName: "Midgut",
        descriptor: { ...subset, computations: [42] },
      }),
    );

    expect([noName.ok, numberComputation.ok]).toEqual([false, false]);
    expect(noName.ok ? "" : noName.error).toMatch(/^displayName: /);
    expect(numberComputation.ok ? "" : numberComputation.error).toMatch(
      /^descriptor\.computations\.0: /,
    );
  });

  it("takes the documents the backend's model takes", () => {
    const noDescriptor = parseEdaSpec(
      JSON.stringify({ studyId: "DS_45abf80334", displayName: "Midgut" }),
    );
    const emptyStudy = parseEdaSpec(
      JSON.stringify({ studyId: "", displayName: "Midgut", descriptor: subset }),
    );

    expect(
      [noDescriptor, emptyStudy].map((parsed) => parsed.ok && parsed.summary),
    ).toEqual([
      {
        displayName: "Midgut",
        studyId: "DS_45abf80334",
        filters: [],
        computationCount: 0,
      },
      { displayName: "Midgut", studyId: "", filters: [], computationCount: 0 },
    ]);
  });
});

describe("EdaSpecParam stored value", () => {
  it("says no spec is set for an empty value", () => {
    renderWidget("");

    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent(
      "No analysis spec is set.",
    );
    expect(editor().value).toBe("");
  });

  it("shows why a stored spec does not parse and keeps it editable", () => {
    const stored = JSON.stringify({ studyId: "DS_45abf80334", descriptor: {} });
    const writes = renderWidget(stored);

    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent(
      /^The stored analysis spec does not parse\. displayName: /,
    );
    expect(JSON.parse(editor().value)).toEqual(JSON.parse(stored));

    const fixed = { studyId: "DS_45abf80334", displayName: "Midgut", descriptor: {} };
    fireEvent.change(editor(), { target: { value: JSON.stringify(fixed) } });

    expect(writes).toEqual([JSON.stringify(fixed)]);
    expect(screen.getByTestId("eda-spec-summary")).toHaveTextContent("Midgut");
  });
});
