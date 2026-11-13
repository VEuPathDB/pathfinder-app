import type { Step, Strategy } from "@strategist/shared";

/**
 * Complete, type-checked fixtures for the shared domain types.
 *
 * Tests used to build partial objects and reach for `as Strategy` or
 * `as unknown as Strategy` to silence the missing fields. A cast turns off
 * excess-property checking too, so a fixture could set a field the type does
 * not have and nothing failed: five of them kept setting `isBuilt` long after
 * it was deleted from the backend and the generated types.
 *
 * Build from these instead. Overrides are checked, so a field that does not
 * exist is a compile error at the call site.
 */

export function makeStep(overrides: Partial<Step> & { id: string }): Step {
  return {
    kind: "search",
    displayName: overrides.id,
    searchName: "GenesByTaxon",
    recordType: "gene",
    isFiltered: false,
    ...overrides,
  };
}

export function makeStrategy(overrides: Partial<Strategy> = {}): Strategy {
  return {
    id: "strategy-1",
    name: "Test strategy",
    siteId: "plasmodb",
    recordType: "gene",
    steps: [],
    isSaved: false,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}
