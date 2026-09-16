import { describe, expect, it } from "vitest";

import { extractErrorMessage } from "./http";

const A_FASTAPI_VALIDATION_BODY = {
  type: "/errors/VALIDATION_ERROR",
  title: "Request validation failed",
  status: 422,
  detail: "Field required; Field required",
  code: "VALIDATION_ERROR",
  errors: [
    {
      type: "missing",
      loc: ["body", "base", "controlsSearchName"],
      msg: "Field required",
      input: { siteId: "plasmodb" },
    },
    {
      type: "missing",
      loc: ["body", "base", "controlsParamName"],
      msg: "Field required",
      input: { siteId: "plasmodb" },
    },
  ],
};

describe("extractErrorMessage", () => {
  it("names the refused fields of a validation problem", () => {
    expect(extractErrorMessage(A_FASTAPI_VALIDATION_BODY)).toBe(
      "controlsSearchName: Field required; controlsParamName: Field required",
    );
  });

  it("keeps the detail of a problem whose errors member it cannot read", () => {
    expect(
      extractErrorMessage({
        detail: "This gene set was not taken from a strategy.",
        errors: [{ unexpected: 1 }],
      }),
    ).toBe("This gene set was not taken from a strategy.");
  });

  it("reads the entry shape that carries message instead of msg", () => {
    expect(
      extractErrorMessage({ errors: [{ message: "Name is already taken" }] }),
    ).toBe("Name is already taken");
  });

  it("falls back to the detail when no entry carries a sentence", () => {
    expect(extractErrorMessage({ detail: "Not found", errors: [] })).toBe("Not found");
  });

  it("falls back to the title when a problem carries nothing else", () => {
    expect(extractErrorMessage({ title: "Conflict" })).toBe("Conflict");
  });

  it("offers nothing for a body that is not a problem", () => {
    expect(extractErrorMessage("<html>gateway</html>")).toBe(null);
    expect(extractErrorMessage({ detail: "   ", title: "", errors: [] })).toBe(null);
  });
});

describe("extractErrorMessage keeps the subject of a refusal", () => {
  it("keeps the summary when the entries write bare fragments", () => {
    expect(
      extractErrorMessage({
        title: "Validation failed",
        detail: "siteId is required",
        errors: [{ path: "siteId", message: "Required" }],
      }),
    ).toBe("siteId is required");
  });

  it("reads a written entry when the problem carries no summary", () => {
    expect(
      extractErrorMessage({
        title: "Invalid plan",
        errors: [{ path: "recordType", message: "Record type is required" }],
      }),
    ).toBe("Record type is required");
  });

  it("does not name the request part as if it were a field", () => {
    expect(
      extractErrorMessage({ errors: [{ loc: ["body"], msg: "Field required" }] }),
    ).toBe("Field required");
  });

  it("names the field rather than the index of a refused list entry", () => {
    expect(
      extractErrorMessage({
        errors: [
          { loc: ["body", "targetOrganisms", 0], msg: "Input should be an object" },
        ],
      }),
    ).toBe("targetOrganisms: Input should be an object");
  });

  it("keeps an entry whose location it cannot read", () => {
    expect(
      extractErrorMessage({ errors: [{ loc: ["body", null], msg: "Field required" }] }),
    ).toBe("Field required");
  });

  it("offers nothing for a detail that is not a sentence", () => {
    expect(extractErrorMessage({ detail: { code: 7 } })).toBe(null);
    expect(extractErrorMessage({ detail: 42 })).toBe(null);
    expect(extractErrorMessage({ detail: false })).toBe(null);
  });

  it("prefers a title to a detail it cannot read", () => {
    expect(extractErrorMessage({ detail: { code: 7 }, title: "Conflict" })).toBe(
      "Conflict",
    );
  });

  it("bounds what it hands the reader", () => {
    const many = Array.from({ length: 300 }, (_unused, i) => ({
      loc: ["body", `field${i}`],
      msg: "Field required",
    }));
    const message = extractErrorMessage({ errors: many });
    expect(message).not.toBe(null);
    expect((message ?? "").length).toBeLessThanOrEqual(300);
    expect(message).toContain("field0: Field required");
  });
});
