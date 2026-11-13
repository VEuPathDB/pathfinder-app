// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("GET /api/v1/web-build", () => {
  it("answers the build this server runs, never from a cache", async () => {
    vi.stubEnv("STRATEGIST_WEB_BUILD", "77b0e5a91c3f");
    const { GET } = await import("./route");

    const response = GET();

    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toEqual({ build: "77b0e5a91c3f" });
  });
});
