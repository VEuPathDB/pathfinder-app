import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";

import { toTraceParts } from "./traceParts";

type UIPart = UIMessage["parts"][number];

describe("toTraceParts", () => {
  it("keeps the parts the protocol defines", () => {
    const parts: UIPart[] = [
      { type: "text", text: "the count is 42" },
      { type: "step-start" },
      {
        type: "tool-run_control_tests_on_step",
        toolCallId: "call_1",
        state: "output-available",
        input: { stepId: 7 },
        output: { mcc: 0.81 },
      },
    ];

    expect(toTraceParts(parts)).toEqual([
      { type: "text", text: "the count is 42" },
      { type: "step-start" },
      {
        type: "tool-run_control_tests_on_step",
        toolCallId: "call_1",
        state: "output-available",
        input: { stepId: 7 },
        output: { mcc: 0.81 },
      },
    ]);
  });

  it("drops the part kinds the protocol does not name", () => {
    const parts: UIPart[] = [
      { type: "text", text: "kept" },
      { type: "custom", kind: "acme.widget" },
      { type: "reasoning-file", mediaType: "text/plain", url: "data:," },
      {
        type: "dynamic-tool",
        toolName: "whatever",
        toolCallId: "call_2",
        state: "input-available",
        input: {},
      },
    ];

    expect(toTraceParts(parts)).toEqual([{ type: "text", text: "kept" }]);
  });
});
