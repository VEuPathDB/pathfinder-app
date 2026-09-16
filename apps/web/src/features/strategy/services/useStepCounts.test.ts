/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import type { StrategyAst } from "@pathfinder/shared";

const useQueryMock = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: (opts: unknown) => useQueryMock(opts),
  keepPreviousData: Symbol("keepPreviousData"),
}));
vi.mock("use-debounce", () => ({
  useDebounce: (v: unknown) => [v],
}));

import { useStepCounts } from "./useStepCounts";

const PLAN: StrategyAst = {
  recordType: "gene",
  root: { id: "a", searchName: "GenesByTaxon" },
};

function run(applyStepCounts: (c: Record<string, number | null | undefined>) => void) {
  return renderHook(() =>
    useStepCounts({
      siteId: "plasmodb",
      plan: PLAN,
      planHash: "h1",
      stepIds: ["s1"],
      applyStepCounts,
      fetchCounts: vi.fn(),
    }),
  );
}

describe("useStepCounts", () => {
  beforeEach(() => {
    useQueryMock.mockReset();
  });

  it("defers applyStepCounts out of render when counts arrive", async () => {
    // Baseline render establishes the prev-key; the write branch only fires on
    // the re-render where the query's data actually changes (async arrival).
    useQueryMock.mockReturnValue({ data: { counts: {} } });
    const applyStepCounts = vi.fn();
    const { rerender } = run(applyStepCounts);
    await Promise.resolve();
    applyStepCounts.mockClear();

    useQueryMock.mockReturnValue({ data: { counts: { s1: 5 } } });
    rerender();

    // Writing to the store synchronously during render updates other mounted
    // subscribers mid-render - the React error we are guarding against.
    expect(applyStepCounts).not.toHaveBeenCalled();

    await Promise.resolve();
    expect(applyStepCounts).toHaveBeenCalledWith({ s1: 5 });
  });

  it("maps missing counts to null once the write flushes", async () => {
    useQueryMock.mockReturnValue({ data: { counts: { s1: 5 } } });
    const applyStepCounts = vi.fn();
    const { rerender } = run(applyStepCounts);
    await Promise.resolve();
    applyStepCounts.mockClear();

    useQueryMock.mockReturnValue({ data: { counts: {} } });
    rerender();
    await Promise.resolve();

    expect(applyStepCounts).toHaveBeenCalledWith({ s1: null });
  });
});
