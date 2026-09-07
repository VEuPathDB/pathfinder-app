import { describe, expect, it } from "vitest";

import { sitesOptions } from "./sites";

describe("sitesOptions", () => {
  it("refetches on the interval the api retries a degraded site on", () => {
    const options = sitesOptions();

    expect(options.refetchInterval).toBe(60_000);
    expect(options.staleTime).toBe(60_000);
  });
});
