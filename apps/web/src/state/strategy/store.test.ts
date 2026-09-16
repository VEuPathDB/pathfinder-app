/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("strategy store - devtools registration", () => {
  it("registers exactly one Redux DevTools connection named StrategyStore", async () => {
    const connect = vi.fn(() => ({
      init: vi.fn(),
      send: vi.fn(),
      subscribe: vi.fn(() => () => undefined),
      unsubscribe: vi.fn(),
    }));
    vi.stubGlobal("__REDUX_DEVTOOLS_EXTENSION__", { connect });
    vi.resetModules();

    await import("./store");

    expect(connect).toHaveBeenCalledTimes(1);
    expect(connect).toHaveBeenCalledWith({ name: "StrategyStore" });
  });
});
