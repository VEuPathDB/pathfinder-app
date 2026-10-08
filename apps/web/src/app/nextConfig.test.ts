import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "../../next.config";

describe("the Next config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  /**
   * The dev-tools indicator button renders in a page corner and takes the
   * pointer events of anything under it.
   */
  it("ships no dev-tools indicator", () => {
    expect(nextConfig.devIndicators).toBe(false);
  });

  it("serves the app under /pathfinder", () => {
    expect(nextConfig.basePath).toBe("/pathfinder");
  });

  it("proxies only the health and API routes to the api", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api:8000");
    const rewrites = await nextConfig.rewrites?.();
    const routes =
      rewrites !== undefined && !Array.isArray(rewrites)
        ? (rewrites.afterFiles ?? [])
        : [];

    expect(routes.map((route) => route.source)).toEqual([
      "/health/:path*",
      "/api/:path*",
    ]);
  });
});
