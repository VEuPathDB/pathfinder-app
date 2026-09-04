// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { makeStrategy } from "@/lib/types/fixtures";
import { deserializeStrategyToGraph, readEdgeColors } from "./deserialize";

afterEach(() => document.documentElement.removeAttribute("style"));

function setTokens(): void {
  const root = document.documentElement;
  root.style.setProperty("--border", "212 20% 89%");
  root.style.setProperty("--foreground", "215 42% 12%");
  root.style.setProperty("--card", "0 0% 100%");
  root.style.setProperty("--muted-foreground", "215 16% 40%");
}

const COMBINE = makeStrategy({
  id: "s1",
  steps: [
    { id: "a", displayName: "A" },
    { id: "b", displayName: "B" },
    {
      id: "c",
      displayName: "C",
      primaryInputStepId: "a",
      secondaryInputStepId: "b",
    },
  ],
  rootStepId: "c",
});

describe("readEdgeColors", () => {
  it("resolves the four canvas tokens on the document", () => {
    setTokens();
    expect(readEdgeColors()).toEqual({
      border: "hsl(212 20% 89%)",
      foreground: "hsl(215 42% 12%)",
      card: "hsl(0 0% 100%)",
      mutedForeground: "hsl(215 16% 40%)",
    });
  });

  it("follows the ground the document is on", () => {
    setTokens();
    document.documentElement.style.setProperty("--border", "215 20% 22%");
    expect(readEdgeColors().border).toBe("hsl(215 20% 22%)");
  });

  it("inherits the surrounding ink when the stylesheet defines nothing", () => {
    expect(readEdgeColors()).toEqual({
      border: "currentColor",
      foreground: "currentColor",
      card: "transparent",
      mutedForeground: "currentColor",
    });
  });
});

describe("deserializeStrategyToGraph edge paint", () => {
  it("paints every edge from the token layer, with no hex left", () => {
    setTokens();
    const positions = new Map(
      ["a", "b", "c"].map((id, i) => [id, { x: 200 + i * 300, y: 200 }] as const),
    );
    const { edges } = deserializeStrategyToGraph(
      COMBINE,
      undefined,
      undefined,
      undefined,
      { computedPositions: positions },
    );
    const primary = edges.find((e) => e.id === "a-c-primary");
    const secondary = edges.find((e) => e.id === "b-c-secondary");

    expect(primary?.style).toEqual({ stroke: "hsl(212 20% 89%)", strokeWidth: 2 });
    expect(primary?.labelStyle).toEqual({
      fontSize: 11,
      fontWeight: 700,
      fill: "hsl(215 42% 12%)",
    });
    expect(primary?.labelBgStyle).toEqual({
      fill: "hsl(0 0% 100%)",
      stroke: "hsl(212 20% 89%)",
      strokeWidth: 1,
    });
    expect(secondary?.style).toEqual({ stroke: "hsl(215 16% 40%)", strokeWidth: 2 });
    expect(JSON.stringify(edges)).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });
});
