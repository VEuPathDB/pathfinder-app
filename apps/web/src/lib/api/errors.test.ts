import { describe, expect, it } from "vitest";
import { APIError } from "./http";
import {
  notOnSiteRefusal,
  siteUnavailableRefusal,
  toUserMessage,
  wdkAuthRefusal,
} from "./errors";

describe("lib/api/errors", () => {
  it("reads the title when the problem body carries no detail", () => {
    const err = new APIError("HTTP 404 Not Found", {
      status: 404,
      statusText: "Not Found",
      url: "http://localhost:8000/api",
      data: {
        type: "/errors/NOT_FOUND",
        title: "Target message not found",
        status: 404,
        code: "NOT_FOUND",
      },
    });
    expect(toUserMessage(err, "Failed to revert")).toBe("Target message not found");
  });

  it("formats APIError messages using problem detail when present", () => {
    const err = new APIError("fallback", {
      status: 422,
      statusText: "Unprocessable Entity",
      url: "http://localhost:8000/api",
      data: { title: "Validation Error", status: 422, detail: "Invalid input" },
    });
    expect(toUserMessage(err, "Request failed.")).toBe("Invalid input");
  });

  it("falls back to APIError.message when not problem+json", () => {
    const err = new APIError("HTTP 500", {
      status: 500,
      statusText: "Internal Server Error",
      url: "http://localhost:8000/api",
      data: { detail: "Something broke" },
    });
    expect(toUserMessage(err, "Request failed.")).toBe("Something broke");
  });

  it("formats unknown errors safely", () => {
    expect(toUserMessage(new Error("Boom"), "Request failed.")).toBe("Boom");
    expect(toUserMessage("string error", "Request failed.")).toBe("string error");
    expect(toUserMessage(null, "Request failed.")).toBe("Request failed.");
  });
});

const LOGIN_REQUIRED_BODY = {
  type: "about:blank",
  title: "VEuPathDB login required",
  status: 401,
  detail:
    "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
  code: "WDK_LOGIN_REQUIRED",
};

const IDENTITY_MISMATCH_BODY = {
  type: "about:blank",
  title: "VEuPathDB account changed",
  status: 401,
  detail:
    "Signed in to VEuPathDB as a different account than this PathFinder session. Sign in again.",
  code: "WDK_IDENTITY_MISMATCH",
};

describe("wdkAuthRefusal", () => {
  it("names the code and detail for a 401 APIError that wants a login", () => {
    const err = new APIError(LOGIN_REQUIRED_BODY.detail, {
      status: 401,
      statusText: "Unauthorized",
      url: "http://localhost:3000/api/v1/conversations/c1/begin",
      data: LOGIN_REQUIRED_BODY,
    });
    expect(wdkAuthRefusal(err)).toEqual({
      code: "WDK_LOGIN_REQUIRED",
      detail:
        "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
    });
  });

  it("names the code and detail for a 401 that reports a second account", () => {
    const err = new APIError(IDENTITY_MISMATCH_BODY.detail, {
      status: 401,
      statusText: "Unauthorized",
      url: "http://localhost:3000/api/v1/eda/viz",
      data: IDENTITY_MISMATCH_BODY,
    });
    expect(wdkAuthRefusal(err)).toEqual({
      code: "WDK_IDENTITY_MISMATCH",
      detail: IDENTITY_MISMATCH_BODY.detail,
    });
  });

  it("reads the body when the chat transport rethrows it as text", () => {
    const err = new Error(JSON.stringify(LOGIN_REQUIRED_BODY));
    expect(wdkAuthRefusal(err)).toEqual({
      code: "WDK_LOGIN_REQUIRED",
      detail:
        "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
    });
  });

  it("ignores a 401 that carries another code", () => {
    const err = new APIError("Unauthorized", {
      status: 401,
      statusText: "Unauthorized",
      url: "/x",
      data: { title: "Unauthorized", status: 401, detail: "no", code: "UNAUTHORIZED" },
    });
    expect(wdkAuthRefusal(err)).toBe(null);
  });

  it("ignores non-401 errors, plain text errors and non-errors", () => {
    const wrongStatus = new APIError("nope", {
      status: 403,
      statusText: "Forbidden",
      url: "/x",
      data: LOGIN_REQUIRED_BODY,
    });
    expect(wdkAuthRefusal(wrongStatus)).toBe(null);
    expect(wdkAuthRefusal(new Error("Failed to fetch"))).toBe(null);
    expect(wdkAuthRefusal(null)).toBe(null);
    expect(wdkAuthRefusal("WDK_LOGIN_REQUIRED")).toBe(null);
  });
});

describe("a body the transport rethrows as text", () => {
  it("reads the field message out of a chat 422 body", () => {
    const body = {
      type: "about:blank",
      title: "Invalid plan",
      status: 422,
      code: "VALIDATION_ERROR",
      errors: [{ path: "recordType", message: "Record type is required" }],
    };
    expect(toUserMessage(new Error(JSON.stringify(body)))).toBe(
      "Record type is required",
    );
  });

  it("names the field a FastAPI validation body refused", () => {
    const body = { detail: [{ loc: ["body", "siteId"], msg: "field required" }] };
    expect(toUserMessage(new Error(JSON.stringify(body)))).toBe(
      "siteId: field required",
    );
  });

  it("leaves a plain message alone", () => {
    expect(toUserMessage(new Error("Failed to fetch"))).toBe("Failed to fetch");
  });
});

const SITE_UNAVAILABLE_BODY = {
  type: "/errors/SITE_UNAVAILABLE",
  title: "Cannot reach the site",
  status: 503,
  detail: "Could not connect to veupathdb (ReadTimeout).",
  code: "SITE_UNAVAILABLE",
};

describe("siteUnavailableRefusal", () => {
  it("names the detail for a 503 that reports the site as down", () => {
    const err = new APIError(SITE_UNAVAILABLE_BODY.detail, {
      status: 503,
      statusText: "Service Unavailable",
      url: "http://localhost:3000/api/v1/veupathdb/auth/login",
      data: SITE_UNAVAILABLE_BODY,
    });
    expect(siteUnavailableRefusal(err)).toEqual({
      code: "SITE_UNAVAILABLE",
      detail: "Could not connect to veupathdb (ReadTimeout).",
    });
  });

  it("reads the body when the transport rethrows it as text", () => {
    const err = new Error(JSON.stringify(SITE_UNAVAILABLE_BODY));
    expect(siteUnavailableRefusal(err)).toEqual({
      code: "SITE_UNAVAILABLE",
      detail: "Could not connect to veupathdb (ReadTimeout).",
    });
  });

  it("ignores a 503 that carries another code", () => {
    const err = new APIError("Service Unavailable", {
      status: 503,
      statusText: "Service Unavailable",
      url: "/x",
      data: {
        title: "External service error",
        status: 503,
        detail: "no",
        code: "EXTERNAL_SERVICE_ERROR",
      },
    });
    expect(siteUnavailableRefusal(err)).toBe(null);
  });

  it("ignores another status, a plain error and a non-error", () => {
    const wrongStatus = new APIError("nope", {
      status: 500,
      statusText: "Internal Server Error",
      url: "/x",
      data: SITE_UNAVAILABLE_BODY,
    });
    expect(siteUnavailableRefusal(wrongStatus)).toBe(null);
    expect(siteUnavailableRefusal(new Error("Failed to fetch"))).toBe(null);
    expect(siteUnavailableRefusal(null)).toBe(null);
  });
});

describe("notOnSiteRefusal", () => {
  const body = {
    type: "/errors/INVALID_STRATEGY",
    title: "Invalid strategy",
    status: 409,
    detail: "Step step_1 is not on the site yet.",
    code: "INVALID_STRATEGY",
  };

  it("names the detail for a 409 that says the step is not on the site", () => {
    const err = new APIError(body.detail, {
      status: 409,
      statusText: "Conflict",
      url: "http://localhost:3000/api/v1/conversations/c/strategy/steps/step_1/records",
      data: body,
    });
    expect(notOnSiteRefusal(err)).toEqual({
      code: "INVALID_STRATEGY",
      detail: "Step step_1 is not on the site yet.",
    });
  });

  it("returns null for a 409 with another code", () => {
    const err = new APIError("locked", {
      status: 409,
      statusText: "Conflict",
      url: "http://localhost:3000/api",
      data: { ...body, code: "CONFLICT" },
    });
    expect(notOnSiteRefusal(err)).toBe(null);
  });

  it("returns null for the same code on another status", () => {
    const err = new APIError(body.detail, {
      status: 400,
      statusText: "Bad Request",
      url: "http://localhost:3000/api",
      data: body,
    });
    expect(notOnSiteRefusal(err)).toBe(null);
  });
});
