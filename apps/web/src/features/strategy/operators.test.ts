import { describe, expect, test } from "vitest";
import { combineOpEnum } from "@pathfinder/shared";
import {
  OFFERED_OPERATORS,
  RETIRED_OPERATOR_LABELS,
  isOperatorLabel,
  operatorLabel,
  operatorPatch,
} from "./operators";
import { DEFAULT_COLOCATION } from "./editor/schema/colocationSchema";

import fixture from "../../../../../packages/spec/operations_parity.json";

describe("operatorLabel", () => {
  test("names every operator the way the api names its combine", () => {
    const labels = Object.fromEntries(
      Object.values(combineOpEnum).map((op) => [op, operatorLabel(op)]),
    );

    expect(labels).toEqual(fixture.combine_labels);
    expect(labels["RMINUS"]).toBe("Right minus");
    expect(labels["COLOCATE"]).toBe("Colocate");
  });

  test("names an operator it does not know by its value", () => {
    expect(operatorLabel("XOR")).toBe("XOR");
    expect(operatorLabel("toString")).toBe("toString");
  });
});

describe("isOperatorLabel", () => {
  test("a label an earlier release gave is not a researcher's name", () => {
    expect(RETIRED_OPERATOR_LABELS).toEqual(fixture.retired_combine_labels);
    expect(RETIRED_OPERATOR_LABELS.map(isOperatorLabel)).toEqual([true, true]);
  });

  test("a name a researcher gave is not a label", () => {
    expect(isOperatorLabel("Kinases not in the apicoplast")).toBe(false);
  });
});

describe("OFFERED_OPERATORS", () => {
  test("offers the site's four set operators in the site's order, then Colocate", () => {
    expect(OFFERED_OPERATORS).toEqual([
      combineOpEnum.INTERSECT,
      combineOpEnum.UNION,
      combineOpEnum.MINUS,
      combineOpEnum.RMINUS,
      combineOpEnum.COLOCATE,
    ]);
  });
});

describe("operatorPatch", () => {
  test("a set operator carries no colocation parameters", () => {
    expect(operatorPatch(combineOpEnum.UNION)).toEqual({ operator: "UNION" });
  });

  test("Colocate carries the default colocation parameters", () => {
    expect(operatorPatch(combineOpEnum.COLOCATE)).toEqual({
      operator: "COLOCATE",
      colocationParams: DEFAULT_COLOCATION,
    });
  });
});
