/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { Suspense } from "react";
import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { useSiteAccess } from "./useSiteAccess";

const PLASMODB: SiteResponse = {
  id: "plasmodb",
  name: "PlasmoDB",
  displayName: "PlasmoDB (Plasmodium)",
  baseUrl: "https://plasmodb.org/plasmo",
  projectId: "PlasmoDB",
  isPortal: false,
  available: true,
  unavailableReason: null,
};

const REFUSAL = {
  title: "Cannot reach the site",
  status: 503,
  detail: "Could not connect to plasmodb (ReadTimeout).",
  code: "SITE_UNAVAILABLE",
};

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Answers the sign-in status with each answer in turn; every other read stays pending. */
function answerStatusWith(...answers: Array<() => Promise<Response>>): string[] {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) => {
      if (!input.includes("/api/v1/veupathdb/auth/status")) {
        return new Promise<Response>(() => {});
      }
      const answer = answers[Math.min(calls.length, answers.length - 1)]!;
      calls.push(input);
      return answer();
    }),
  );
  return calls;
}

function renderAccess(siteId: string, sites: SiteResponse[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(sitesOptions().queryKey, sites);
  const view = renderHook(() => useSiteAccess(siteId), {
    wrapper: ({ children }) => (
      <Wrapper>
        <Suspense fallback={null}>{children}</Suspense>
      </Wrapper>
    ),
  });
  return { queryClient, ...view };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useSiteAccess", () => {
  it("is down for a site the list reports as down, without a sign-in read", () => {
    answerStatusWith(() => new Promise<Response>(() => {}));

    const { result } = renderAccess("plasmodb", [{ ...PLASMODB, available: false }]);

    expect(result.current).toEqual({ kind: "down" });
  });

  it("is up with the sign-in state for a site the list does not name", () => {
    answerStatusWith(() => new Promise<Response>(() => {}));
    const { queryClient, Wrapper } = createTestWrapper();
    queryClient.setQueryData(sitesOptions().queryKey, [PLASMODB]);
    queryClient.setQueryData(authStatusOptions("orthomcl").queryKey, {
      signedIn: true,
    });

    const { result } = renderHook(() => useSiteAccess("orthomcl"), {
      wrapper: Wrapper,
    });

    expect(result.current).toEqual({ kind: "up", signedIn: true });
  });

  it("is pending until the first sign-in status arrives", () => {
    answerStatusWith(() => new Promise<Response>(() => {}));

    const { result } = renderAccess("plasmodb", [PLASMODB]);

    expect(result.current).toEqual({ kind: "pending" });
  });

  it("asks again on the site retry interval after a SITE_UNAVAILABLE refusal", async () => {
    vi.useFakeTimers();
    const calls = answerStatusWith(
      () => Promise.resolve(json(REFUSAL, 503)),
      () => new Promise<Response>(() => {}),
    );

    const { result } = renderAccess("plasmodb", [PLASMODB]);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(result.current).toEqual({ kind: "down" });
    expect(calls).toHaveLength(1);

    await act(() => vi.advanceTimersByTimeAsync(60_000));

    expect(calls).toHaveLength(2);
  });

  it("stays down while it asks again after a refusal", async () => {
    answerStatusWith(
      () => Promise.resolve(json(REFUSAL, 503)),
      () => new Promise<Response>(() => {}),
    );
    const { result, queryClient } = renderAccess("plasmodb", [PLASMODB]);
    await waitFor(() => expect(result.current).toEqual({ kind: "down" }));

    act(() => {
      void queryClient.refetchQueries({
        queryKey: authStatusOptions("plasmodb").queryKey,
      });
    });

    await waitFor(() =>
      expect(
        queryClient.getQueryState(authStatusOptions("plasmodb").queryKey),
      ).toMatchObject({
        fetchStatus: "fetching",
      }),
    );
    expect(result.current).toEqual({ kind: "down" });
  });
});
