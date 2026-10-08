/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";

const mockInvalidateUserScopedQueries = vi.hoisted(() => vi.fn());

vi.mock("@/lib/query/invalidateUserScoped", () => ({
  invalidateUserScopedQueries: mockInvalidateUserScopedQueries,
}));

import { useAuthRefresh } from "./useAuthRefresh";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Answers the status with `signedIn` and the refresh with `refresh`, and counts refreshes. */
function website(signedIn: boolean, refresh: () => Response) {
  const refreshes: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const path = new URL(input, "http://localhost").pathname;
      if (path.endsWith("/auth/status")) return Promise.resolve(json({ signedIn }));
      if (path.endsWith("/auth/refresh") && init?.method === "POST") {
        refreshes.push(path);
        return Promise.resolve(refresh());
      }
      return new Promise<Response>(() => {});
    }),
  );
  return refreshes;
}

function renderRefresh() {
  const { queryClient, Wrapper } = createTestWrapper();
  const view = renderHook(() => useAuthRefresh("plasmodb"), { wrapper: Wrapper });
  return { ...view, queryClient };
}

describe("useAuthRefresh", () => {
  beforeEach(() => {
    mockInvalidateUserScopedQueries.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not refresh when user is not signed in", async () => {
    const refreshes = website(false, () => json({ success: true }));

    const { result, queryClient } = renderRefresh();

    await waitFor(() =>
      expect(queryClient.getQueryData(authStatusOptions("plasmodb").queryKey)).toEqual({
        signedIn: false,
      }),
    );
    await act(async () => {});
    expect(refreshes).toEqual([]);
    expect(result.current.authRefreshed).toBe(false);
  });

  it("refreshes auth when signed in and reports authRefreshed on success", async () => {
    const refreshes = website(true, () => json({ success: true }));

    const { result } = renderRefresh();

    await waitFor(() => expect(result.current.authRefreshed).toBe(true));
    expect(refreshes).toHaveLength(1);
    expect(mockInvalidateUserScopedQueries).toHaveBeenCalledTimes(1);
  });

  it("reports authRefreshed even when the refresh call fails", async () => {
    const refreshes = website(true, () =>
      json({ title: "Unauthorized", status: 401, detail: "no session" }, 401),
    );

    const { result } = renderRefresh();

    await waitFor(() => expect(result.current.authRefreshed).toBe(true));
    expect(refreshes).toHaveLength(1);
    expect(mockInvalidateUserScopedQueries).not.toHaveBeenCalled();
  });
});
