import { describe, expect, it } from "vitest";

import { geneSetLibraryState } from "./geneSetLibraryState";

describe("geneSetLibraryState", () => {
  it("reports a signed-out reader before it reports an empty library", () => {
    expect(geneSetLibraryState({ signedIn: false, isFetched: false, count: 0 })).toBe(
      "signed-out",
    );
  });

  it("stays signed-out even when a stale list is still in the cache", () => {
    expect(geneSetLibraryState({ signedIn: false, isFetched: true, count: 286 })).toBe(
      "signed-out",
    );
  });

  it("reports loading while the first read is in flight", () => {
    expect(geneSetLibraryState({ signedIn: true, isFetched: false, count: 0 })).toBe(
      "loading",
    );
  });

  it("reports an empty library only after the read answered", () => {
    expect(geneSetLibraryState({ signedIn: true, isFetched: true, count: 0 })).toBe(
      "empty",
    );
  });

  it("reports a populated library", () => {
    expect(geneSetLibraryState({ signedIn: true, isFetched: true, count: 286 })).toBe(
      "populated",
    );
  });
});
