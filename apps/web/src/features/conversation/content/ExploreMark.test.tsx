/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const state = {
  message: {
    role: "assistant",
    content: [{ type: "data-turn-route", data: { route: "explore" } }],
  },
};

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (s: typeof state) => unknown) => select(state),
}));

import { ExploreMark, exploreRouteOfMessage } from "./ExploreMark";

describe("exploreRouteOfMessage", () => {
  it("marks a message Explore answered", () => {
    expect(
      exploreRouteOfMessage({
        role: "assistant",
        content: [{ type: "data-turn-route", data: { route: "explore" } }],
      }),
    ).toBe(true);
  });

  it("marks no Build message", () => {
    expect(
      exploreRouteOfMessage({
        role: "assistant",
        content: [{ type: "data-turn-route", data: { route: "build" } }],
      }),
    ).toBe(false);
  });

  it("reads the generic data part shape", () => {
    expect(
      exploreRouteOfMessage({
        role: "assistant",
        content: [{ type: "data", name: "turn-route", data: { route: "explore" } }],
      }),
    ).toBe(true);
  });

  it("marks no message without a route", () => {
    expect(
      exploreRouteOfMessage({ role: "assistant", content: [{ type: "text" }] }),
    ).toBe(false);
    expect(exploreRouteOfMessage(undefined)).toBe(false);
  });

  it("marks no user message", () => {
    expect(
      exploreRouteOfMessage({
        role: "user",
        content: [{ type: "data-turn-route", data: { route: "explore" } }],
      }),
    ).toBe(false);
  });
});

describe("ExploreMark", () => {
  it("labels an Explore answer", () => {
    render(<ExploreMark />);
    expect(screen.getByTestId("explore-mark")).toHaveTextContent("Explore");
  });
});
