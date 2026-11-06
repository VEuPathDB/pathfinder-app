import { afterEach, describe, expect, it } from "vitest";

import { useThreadModeStore } from "./useThreadModeStore";

describe("useThreadModeStore", () => {
  afterEach(() => useThreadModeStore.setState({ modes: {} }));

  it("keeps one pick per thread", () => {
    const { setMode } = useThreadModeStore.getState();
    setMode("c1", "explore");
    setMode("c2", "build");
    setMode("c1", "auto");
    expect(useThreadModeStore.getState().modes).toEqual({ c1: "auto", c2: "build" });
  });
});
