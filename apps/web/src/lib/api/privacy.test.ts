// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { DATA_STATEMENT_VERSION } from "@pathfinder/shared";

import {
  continuePastDataNotice,
  getPrivacySettings,
  updatePrivacySettings,
} from "./privacy";

const SETTINGS = {
  evalDataConsent: false,
  dataNoticeSeen: DATA_STATEMENT_VERSION,
  noticeDue: false,
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function call(spy: ReturnType<typeof vi.fn>): [string, RequestInit] {
  return spy.mock.calls[0] as [string, RequestInit];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("privacy API client", () => {
  it("reads the settings under the base path", async () => {
    const spy = vi.fn().mockResolvedValue(json(SETTINGS));
    vi.stubGlobal("fetch", spy);

    await expect(getPrivacySettings()).resolves.toEqual(SETTINGS);

    expect(call(spy)[0]).toBe("http://localhost:3000/pathfinder/api/v1/me/privacy");
  });

  it("writes the learning choice under the base path", async () => {
    const spy = vi.fn().mockResolvedValue(json(SETTINGS));
    vi.stubGlobal("fetch", spy);

    await updatePrivacySettings({ evalDataConsent: false });

    const [url, init] = call(spy);
    expect(url).toBe("http://localhost:3000/pathfinder/api/v1/me/privacy");
    expect(init).toMatchObject({
      method: "PATCH",
      body: JSON.stringify({ evalDataConsent: false }),
    });
  });

  it("records the statement version and the learning choice in one call", async () => {
    const spy = vi.fn().mockResolvedValue(json(SETTINGS));
    vi.stubGlobal("fetch", spy);

    await continuePastDataNotice(false);

    const [url, init] = call(spy);
    expect(url).toBe("http://localhost:3000/pathfinder/api/v1/me/privacy/data-notice");
    expect(init).toMatchObject({
      method: "POST",
      body: JSON.stringify({ version: DATA_STATEMENT_VERSION, evalDataConsent: false }),
    });
  });
});
