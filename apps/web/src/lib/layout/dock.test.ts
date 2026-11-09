import { describe, expect, it } from "vitest";

import { dockLayout, type DockInput } from "./dock";

function input(overrides: Partial<DockInput> = {}): DockInput {
  return {
    viewport: 1440,
    leftOpen: true,
    leftWidth: 360,
    rightOpen: true,
    rightWidth: 360,
    lastOpened: "right",
    ...overrides,
  };
}

describe("dockLayout", () => {
  it("docks both panels while the chat keeps 600px", () => {
    expect(dockLayout(input())).toEqual({ leftFloats: false, rightFloats: false });
  });

  it("floats the panel opened last when both no longer fit", () => {
    expect([
      dockLayout(input({ viewport: 1200, lastOpened: "right" })),
      dockLayout(input({ viewport: 1200, lastOpened: "left" })),
    ]).toEqual([
      { leftFloats: false, rightFloats: true },
      { leftFloats: true, rightFloats: false },
    ]);
  });

  it("floats both when neither fits beside the chat alone", () => {
    expect(dockLayout(input({ viewport: 960 }))).toEqual({
      leftFloats: true,
      rightFloats: true,
    });
  });

  it("floats a lone panel that would leave the chat under 600px", () => {
    expect(dockLayout(input({ viewport: 980, leftOpen: false }))).toEqual({
      leftFloats: false,
      rightFloats: true,
    });
  });

  it("docks a lone panel that leaves the chat 600px", () => {
    expect(dockLayout(input({ viewport: 1004, leftOpen: false }))).toEqual({
      leftFloats: false,
      rightFloats: false,
    });
  });

  it("floats everything on a phone", () => {
    expect(
      dockLayout(input({ viewport: 390, leftOpen: true, rightOpen: false })),
    ).toEqual({
      leftFloats: true,
      rightFloats: false,
    });
  });
});
