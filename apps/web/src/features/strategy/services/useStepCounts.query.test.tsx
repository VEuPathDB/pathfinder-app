/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import type { StrategyAst } from "@pathfinder/shared";
import { createTestWrapper } from "@/lib/query/testing";

import { useStepCounts } from "./useStepCounts";

const PLAN: StrategyAst = {
  recordType: "gene",
  root: { id: "s1", searchName: "GenesByTaxon" },
};

function mount(wanted: boolean) {
  const fetchCounts = vi.fn(async () => ({ counts: { s1: 42 } }));
  const applyStepCounts = vi.fn();
  const { Wrapper } = createTestWrapper();
  const view = renderHook(
    ({ wanted: on }: { wanted: boolean }) =>
      useStepCounts({
        siteId: "plasmodb",
        plan: PLAN,
        planHash: "h1",
        stepIds: ["s1"],
        wanted: on,
        applyStepCounts,
        fetchCounts,
        debounceMs: 0,
      }),
    { wrapper: Wrapper, initialProps: { wanted } },
  );
  return { ...view, fetchCounts, applyStepCounts };
}

function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 50));
}

describe("useStepCounts against a real query client", () => {
  it("sends no request while no count is wanted", async () => {
    const { fetchCounts } = mount(false);
    await settle();

    expect(fetchCounts).toHaveBeenCalledTimes(0);
  });

  it("sends one request once a count is wanted, and applies what it answers", async () => {
    const { fetchCounts, applyStepCounts, rerender } = mount(false);
    await settle();

    rerender({ wanted: true });

    await waitFor(() => expect(applyStepCounts).toHaveBeenCalledWith({ s1: 42 }));
    expect(fetchCounts).toHaveBeenCalledTimes(1);
    expect(fetchCounts).toHaveBeenCalledWith("plasmodb", PLAN);
  });

  it("sends no second request when the count stops being wanted", async () => {
    const { fetchCounts, applyStepCounts, rerender } = mount(true);
    await waitFor(() => expect(applyStepCounts).toHaveBeenCalledWith({ s1: 42 }));

    rerender({ wanted: false });
    await settle();
    rerender({ wanted: true });
    await settle();

    expect(fetchCounts).toHaveBeenCalledTimes(1);
  });
});
