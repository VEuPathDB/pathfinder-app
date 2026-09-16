// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import type { Experiment } from "@pathfinder/shared";

import { useSweepState } from "./useSweepState";

const A_NUMERIC_SPEC = {
  name: "min_molecular_weight",
  displayName: "Minimum molecular weight",
  type: "number",
  isVisible: true,
  vocabulary: null,
};

vi.mock("@/lib/hooks/useParamSpecs", () => ({
  useParamSpecs: () => ({ paramSpecs: [A_NUMERIC_SPEC], isLoading: false }),
}));

function experimentWith(parameters: Record<string, unknown>): Experiment {
  return {
    id: "exp_1",
    status: "completed",
    config: {
      siteId: "plasmodb",
      recordType: "transcript",
      searchName: "GenesByMolecularWeight",
      parameters,
      positiveControls: [],
      negativeControls: [],
      controlsSearchName: "GeneByLocusTag",
      controlsParamName: "ds_gene_ids",
    },
  } as unknown as Experiment;
}

describe("useSweepState reads a typed parameter value", () => {
  it("shows the number a saved search bound, not the shape of its wire value", () => {
    const { result } = renderHook(() =>
      useSweepState(
        experimentWith({ min_molecular_weight: { type: "number", value: 50000 } }),
      ),
    );
    const param = result.current.sweepableParams.at(0);
    expect(param?.currentValue).toBe("50000");
    expect(param?.numericValue).toBe(50000);
  });
});
