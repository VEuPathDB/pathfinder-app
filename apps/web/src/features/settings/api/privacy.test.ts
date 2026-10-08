// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { getPrivacySettings, updatePrivacySettings } from "./privacy";

const SETTINGS = { evalDataConsent: false, noticeSeen: true };

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function calledUrl(spy: ReturnType<typeof vi.fn>): string {
  const [url] = spy.mock.calls[0] as [string, RequestInit];
  return url;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("privacy API client", () => {
  it("reads the settings under the base path", async () => {
    const spy = vi.fn().mockResolvedValue(json(SETTINGS));
    vi.stubGlobal("fetch", spy);

    await getPrivacySettings();

    expect(calledUrl(spy)).toBe("http://localhost:3000/pathfinder/api/v1/me/privacy");
  });

  it("writes the settings under the base path", async () => {
    const spy = vi.fn().mockResolvedValue(json(SETTINGS));
    vi.stubGlobal("fetch", spy);

    await updatePrivacySettings({ noticeSeen: true });

    expect(calledUrl(spy)).toBe("http://localhost:3000/pathfinder/api/v1/me/privacy");
    expect(spy.mock.calls[0]?.[1]).toMatchObject({ method: "PATCH" });
  });
});
