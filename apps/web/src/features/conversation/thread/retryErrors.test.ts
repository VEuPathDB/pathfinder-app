import { describe, expect, it } from "vitest";

import { retryErrorLine } from "./retryErrors";

const SHORT_REPLY =
  '[{"type":"string_too_short","loc":["reply"],"msg":"String should have at least 20 characters","input":"[mock] Two","ctx":{"min_length":20}}]';

describe("retryErrorLine", () => {
  it("says a validation error as its field and message", () => {
    expect(retryErrorLine(SHORT_REPLY)).toBe(
      "1 validation error: reply: String should have at least 20 characters",
    );
  });

  it("counts several errors and joins a nested field with dots", () => {
    const two = JSON.stringify([
      { type: "missing", loc: ["control_set_id"], msg: "Field required" },
      {
        type: "int_parsing",
        loc: ["filters", 0, "limit"],
        msg: "Input should be a valid integer",
      },
    ]);

    expect(retryErrorLine(two)).toBe(
      "2 validation errors: control_set_id: Field required; filters.0.limit: Input should be a valid integer",
    );
  });

  it("keeps an error with no field as its message", () => {
    const whole = JSON.stringify([
      { type: "value_error", loc: [], msg: "Value error, no step" },
    ]);

    expect(retryErrorLine(whole)).toBe("1 validation error: Value error, no step");
  });

  it("leaves a refusal in words as it is", () => {
    expect(retryErrorLine("PF3D7_0401600 is a control.")).toBe(
      "PF3D7_0401600 is a control.",
    );
  });

  it("leaves JSON that is no error list as it is", () => {
    expect(retryErrorLine('{"error":"boom"}')).toBe('{"error":"boom"}');
  });
});
