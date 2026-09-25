// @vitest-environment jsdom
import { makeStep, makeStrategy } from "@/lib/types/fixtures";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import type { ReactNode } from "react";
import { createElement } from "react";
import type * as SitesApi from "@/lib/api/sites";
import { useStrategyStore } from "@/state/strategy/store";

vi.mock("@/lib/api/sites", async () => {
  const actual = await vi.importActual<typeof SitesApi>("@/lib/api/sites");
  return {
    ...actual,
    validateSearchParams: async () => ({
      validation: {
        isValid: false,
        normalizedContextValues: {},
        errors: { general: [], byKey: { organism: ["Required value is missing"] } },
      },
    }),
  };
});

import { useStrategyGraphNodes } from "./useStrategyGraphNodes";

const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(ReactFlowProvider, null, children);

beforeEach(() => {
  useStrategyStore.setState({ graphValidationStatus: {} });
});

describe("useStrategyGraphNodes - the strategy's check flag", () => {
  it("rises when an edit leaves a step with a value the site refuses", async () => {
    const strategyWith = (organism: string[]) =>
      makeStrategy({
        id: "conv-1",
        recordType: "transcript",
        steps: [
          makeStep({
            id: "step_a",
            displayName: "Genes by taxon",
            searchName: "GenesByTaxon",
            parameters: {
              organism: { type: "multi-pick-vocabulary", values: organism },
            },
          }),
        ],
      });

    const { rerender } = renderHook(
      ({ organism }: { organism: string[] }) =>
        useStrategyGraphNodes({
          strategy: strategyWith(organism),
          siteId: "plasmodb",
          variant: "full",
        }),
      { wrapper, initialProps: { organism: ["Plasmodium falciparum 3D7"] } },
    );
    rerender({ organism: [] });

    await waitFor(
      () => {
        expect(useStrategyStore.getState().graphValidationStatus["conv-1"]).toBe(true);
      },
      { timeout: 3000 },
    );
  });
});
