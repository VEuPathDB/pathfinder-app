import { describe, expect, test } from "vitest";
import type { Step, Strategy } from "@pathfinder/shared";
import { applyOperation } from "./apply";
import type { GraphOperation } from "@/lib/types/graphOperation";

import fixture from "../../../../../../packages/spec/operations_parity.json";

interface Case {
  name: string;
  initial: {
    steps: Array<{
      id: string;
      kind?: string;
      primaryInputStepId?: string;
      secondaryInputStepId?: string;
    }>;
    rootStepId: string | null;
  };
  op: unknown;
  expected: {
    stepIds: string[];
    rootInputs: Record<string, { primary?: string | null; secondary?: string | null }>;
    droppedStepIds: string[];
  };
}

function makeStep(s: Case["initial"]["steps"][number]): Step {
  return {
    id: s.id,
    kind: s.kind ?? "search",
    displayName: s.id,
    searchName:
      s.kind === "combine"
        ? "__combine__"
        : s.kind === "transform"
          ? "orthologs"
          : "geneById",
    primaryInputStepId: s.primaryInputStepId ?? null,
    secondaryInputStepId: s.secondaryInputStepId ?? null,
    operator: s.kind === "combine" ? "INTERSECT" : null,
    isFiltered: false,
  };
}

function strategy(c: Case["initial"]): Strategy {
  return {
    id: "s",
    name: "T",
    siteId: "plasmodb",
    recordType: "gene",
    steps: c.steps.map(makeStep),
    rootStepId: c.rootStepId,
    isSaved: false,
    description: null,
    wdkStrategyId: null,
    wdkUrl: null,
    createdAt: "t",
    updatedAt: "t",
  };
}

const cases = (fixture as { cases: Case[] }).cases;

describe("operations parity (shared FE/BE fixture)", () => {
  for (const c of cases) {
    test(c.name, () => {
      const initial = strategy(c.initial);
      const initialIds = new Set(initial.steps.map((s) => s.id));
      const result = applyOperation(initial, c.op as GraphOperation);
      expect(result.kind).toBe("applied");
      if (result.kind !== "applied") return;
      const next = result.next;
      expect(next.steps.map((s) => s.id).sort()).toEqual(
        [...c.expected.stepIds].sort(),
      );
      const dropped = [...initialIds].filter(
        (id) => !next.steps.some((s) => s.id === id),
      );
      expect(dropped.sort()).toEqual([...c.expected.droppedStepIds].sort());
      for (const [parentId, slots] of Object.entries(c.expected.rootInputs)) {
        const node = next.steps.find((s) => s.id === parentId);
        expect(node).toBeDefined();
        if (slots.primary !== undefined) {
          expect(node!.primaryInputStepId ?? null).toBe(slots.primary);
        }
        if (slots.secondary !== undefined) {
          expect(node!.secondaryInputStepId ?? null).toBe(slots.secondary);
        }
      }
    });
  }
});
