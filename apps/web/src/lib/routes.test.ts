import { describe, expect, it } from "vitest";
import {
  chatRoot,
  chatUrl,
  edaTabUrl,
  strategyCanvasUrl,
  strategyStepUrl,
  workbenchGeneSetUrl,
  workbenchRoot,
} from "./routes";

describe("route builders", () => {
  it("prefix every target with the site id", () => {
    expect(chatRoot("plasmodb")).toBe("/plasmodb/conversation");
    expect(chatUrl("plasmodb", "c1")).toBe("/plasmodb/conversation/c1");
    expect(workbenchRoot("toxodb")).toBe("/toxodb/workbench");
    expect(workbenchGeneSetUrl("toxodb", "g1")).toBe("/toxodb/workbench/g1");
  });

  it("builds the site-scoped conversation eda path", () => {
    expect(edaTabUrl("plasmodb", "conv-1")).toBe("/plasmodb/conversation/conv-1/eda");
  });

  it("builds the strategy canvas path", () => {
    expect(strategyCanvasUrl("plasmodb", "conv-1")).toBe(
      "/plasmodb/conversation/conv-1/strategy",
    );
  });

  it("builds a step deep link under the canvas path", () => {
    expect(strategyStepUrl("plasmodb", "conv-1", "step_1")).toBe(
      "/plasmodb/conversation/conv-1/strategy/step/step_1",
    );
  });
});
