// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { UnreadableState } from "./UnreadableState";

afterEach(cleanup);

describe("UnreadableState", () => {
  it("names the stored strategy unreadable with its reason", () => {
    render(<UnreadableState reason="root: a combine names one step twice" />);

    expect(screen.getByTestId("strategy-unreadable-state").textContent).toBe(
      "This strategy could not be read" +
        "Its stored plan does not load, so no step can be shown or built on: " +
        "root: a combine names one step twice",
    );
  });
});
