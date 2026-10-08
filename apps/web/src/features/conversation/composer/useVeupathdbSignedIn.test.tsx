/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";

import { useVeupathdbSignedIn } from "./useVeupathdbSignedIn";

function setup(signedIn: boolean | null) {
  const { queryClient, Wrapper } = createTestWrapper();
  const siteId = useSessionStore.getState().selectedSite;
  if (signedIn !== null) {
    queryClient.setQueryData(authStatusOptions(siteId).queryKey, { signedIn });
  }
  return { Wrapper };
}

describe("useVeupathdbSignedIn", () => {
  it("is true only when the auth status says so", () => {
    const signedIn = setup(true);
    expect(
      renderHook(() => useVeupathdbSignedIn(), { wrapper: signedIn.Wrapper }).result
        .current,
    ).toBe(true);

    const signedOut = setup(false);
    expect(
      renderHook(() => useVeupathdbSignedIn(), { wrapper: signedOut.Wrapper }).result
        .current,
    ).toBe(false);
  });

  it("treats an unresolved auth status as signed out", () => {
    const unknown = setup(null);
    expect(
      renderHook(() => useVeupathdbSignedIn(), { wrapper: unknown.Wrapper }).result
        .current,
    ).toBe(false);
  });
});
