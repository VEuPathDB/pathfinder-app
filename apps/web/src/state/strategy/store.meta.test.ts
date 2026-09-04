import { beforeEach, describe, expect, it } from "vitest";
import { useStrategyStore } from "./store";

function resetStore() {
  useStrategyStore.setState({ graphValidationStatus: {} });
}

describe("strategy store - setGraphValidationStatus", () => {
  beforeEach(resetStore);

  it("records the error flag under the given strategy id", () => {
    useStrategyStore.getState().setGraphValidationStatus("strategy-1", true);
    expect(useStrategyStore.getState().graphValidationStatus).toEqual({
      "strategy-1": true,
    });
  });

  it("records a cleared error flag rather than dropping the id", () => {
    useStrategyStore.getState().setGraphValidationStatus("strategy-1", false);
    expect(useStrategyStore.getState().graphValidationStatus["strategy-1"]).toBe(false);
  });

  it("merges into the existing map so other strategies keep their status", () => {
    const api = useStrategyStore.getState();
    api.setGraphValidationStatus("strategy-1", true);
    api.setGraphValidationStatus("strategy-2", false);
    expect(useStrategyStore.getState().graphValidationStatus).toEqual({
      "strategy-1": true,
      "strategy-2": false,
    });
  });

  it("overwrites the status of an id that already has one", () => {
    const api = useStrategyStore.getState();
    api.setGraphValidationStatus("strategy-1", true);
    api.setGraphValidationStatus("strategy-1", false);
    expect(useStrategyStore.getState().graphValidationStatus).toEqual({
      "strategy-1": false,
    });
  });

  it("replaces the map reference so subscribers re-render", () => {
    const api = useStrategyStore.getState();
    api.setGraphValidationStatus("strategy-1", true);
    const before = useStrategyStore.getState().graphValidationStatus;
    api.setGraphValidationStatus("strategy-2", true);
    expect(useStrategyStore.getState().graphValidationStatus).not.toBe(before);
    expect(before).toEqual({ "strategy-1": true });
  });
});
