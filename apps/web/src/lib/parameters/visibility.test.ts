import { describe, expect, it } from "vitest";
import type { ParamSpec } from "@strategist/shared";
import { isEditable, isInputStepParam, isShown } from "./visibility";

function spec(over: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "organism",
    type: "single-pick-vocabulary",
    isVisible: true,
    isReadOnly: false,
    group: null,
    ...over,
  };
}

describe("isShown", () => {
  it("shows a plain parameter", () => {
    expect(isShown(spec())).toBe(true);
  });

  it("does not show a parameter WDK hides, which WDK also puts in its hidden group", () => {
    expect(isShown(spec({ isVisible: false, group: "_hidden" }))).toBe(false);
  });

  it("does not show the parameter that wires a step's input", () => {
    expect(isShown(spec({ type: "input-step" }))).toBe(false);
  });

  it("does not show a parameter with no name", () => {
    expect(isShown(spec({ name: "" }))).toBe(false);
  });

  it("shows a read-only parameter", () => {
    expect(isShown(spec({ isReadOnly: true }))).toBe(true);
  });
});

describe("isEditable", () => {
  it("lets a researcher edit a plain parameter", () => {
    expect(isEditable(spec())).toBe(true);
  });

  it("does not let a researcher edit a read-only parameter", () => {
    expect(isEditable(spec({ isReadOnly: true }))).toBe(false);
  });

  it("does not let a researcher edit a parameter that is not shown", () => {
    expect(isEditable(spec({ isVisible: false }))).toBe(false);
    expect(isEditable(spec({ type: "input-step" }))).toBe(false);
  });
});

describe("isInputStepParam", () => {
  it("is true for the parameter that wires a step's input", () => {
    expect(isInputStepParam({ type: "input-step" })).toBe(true);
  });

  it("is false for a parameter the researcher sets", () => {
    expect(isInputStepParam({ type: "single-pick-vocabulary" })).toBe(false);
    expect(isInputStepParam({ type: "input-dataset" })).toBe(false);
  });
});
