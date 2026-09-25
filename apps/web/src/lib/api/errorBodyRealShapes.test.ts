import { describe, expect, it } from "vitest";
import { extractErrorMessage } from "@/lib/api/http";

describe("the reader against bodies the backend actually sends", () => {
  it("plan validation with an empty path", () => {
    expect(
      extractErrorMessage({
        title: "Invalid plan",
        errors: [{ path: "", message: "root.operator: bad", code: "INVALID_STRATEGY" }],
      }),
    ).toBe("root.operator: bad");
  });
  it("a missing site id keeps its summary", () => {
    expect(
      extractErrorMessage({
        detail: "siteId is required",
        errors: [{ path: "siteId", message: "Required", code: "INVALID_PARAMETERS" }],
      }),
    ).toBe("siteId is required");
  });
  it("a conversation that is not in Recently deleted keeps its summary", () => {
    expect(
      extractErrorMessage({
        detail: "The conversation is not in Recently deleted.",
        errors: [
          {
            path: "strategyId",
            message: "Not in Recently deleted",
            code: "INVALID_STATE",
          },
        ],
      }),
    ).toBe("The conversation is not in Recently deleted.");
  });
  it("a FastAPI validation body names its fields", () => {
    expect(
      extractErrorMessage({
        detail: "Field required; Field required",
        errors: [
          {
            type: "missing",
            loc: ["body", "base", "controlsSearchName"],
            msg: "Field required",
          },
          {
            type: "missing",
            loc: ["body", "base", "controlsParamName"],
            msg: "Field required",
          },
        ],
      }),
    ).toBe("controlsSearchName: Field required; controlsParamName: Field required");
  });
  it("a body carrying both shapes prefers the located one", () => {
    expect(
      extractErrorMessage({
        detail: "Summary",
        errors: [
          { path: "a", message: "written" },
          { loc: ["body", "b"], msg: "located" },
        ],
      }),
    ).toBe("b: located");
  });
  it("an entry with both loc and path prefers the path it declares", () => {
    expect(
      extractErrorMessage({
        errors: [{ path: "chosen", loc: ["body", "other"], msg: "x" }],
      }),
    ).toBe("chosen: x");
  });
});
