/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { createTestWrapper } from "@/lib/query/testing";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockRefreshAuth = vi.hoisted(() => vi.fn());
const mockGetAuthStatus = vi.hoisted(() => vi.fn());
const mockInvalidateUserScopedQueries = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/veupathdb-auth", () => ({
  refreshAuth: mockRefreshAuth,
  getVeupathdbAuthStatus: mockGetAuthStatus,
  authStatusOptions: (siteId: string) => ({
    queryKey: ["auth", "status", siteId] as const,
    queryFn: () => mockGetAuthStatus(siteId),
    enabled: siteId !== "",
  }),
  authRefreshOptions: (siteId: string) => ({
    queryKey: ["auth", "refresh", siteId] as const,
    queryFn: async () => {
      await mockRefreshAuth(siteId);
      return { refreshed: true };
    },
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  }),
}));

vi.mock("@/lib/query/invalidateUserScoped", () => ({
  invalidateUserScopedQueries: mockInvalidateUserScopedQueries,
}));

describe("useAuthRefresh", () => {
  beforeEach(() => {
    mockRefreshAuth.mockReset();
    mockGetAuthStatus.mockReset();
    mockInvalidateUserScopedQueries.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function importAndRender() {
    const { useAuthRefresh } = await import("./useAuthRefresh");
    const { Wrapper } = createTestWrapper();
    return renderHook(() => useAuthRefresh("plasmodb"), { wrapper: Wrapper });
  }

  it("does not refresh when user is not signed in", async () => {
    mockGetAuthStatus.mockResolvedValue({ signedIn: false, name: null });

    const { result } = await importAndRender();

    await waitFor(() => {
      expect(mockGetAuthStatus).toHaveBeenCalled();
    });

    expect(mockRefreshAuth).not.toHaveBeenCalled();
    expect(result.current.authRefreshed).toBe(false);
  });

  it("refreshes auth when signed in and reports authRefreshed on success", async () => {
    mockGetAuthStatus.mockResolvedValue({ signedIn: true, name: "Jane" });
    mockRefreshAuth.mockResolvedValue({ success: true });

    const { result } = await importAndRender();

    await waitFor(() => {
      expect(mockRefreshAuth).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(result.current.authRefreshed).toBe(true);
    });
    expect(mockInvalidateUserScopedQueries).toHaveBeenCalledTimes(1);
  });

  it("reports authRefreshed even when the refresh call fails", async () => {
    mockGetAuthStatus.mockResolvedValue({ signedIn: true, name: "Jane" });
    mockRefreshAuth.mockRejectedValue(new Error("refresh failed"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = await importAndRender();

    await waitFor(() => {
      expect(mockRefreshAuth).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(result.current.authRefreshed).toBe(true);
    });
    expect(mockInvalidateUserScopedQueries).not.toHaveBeenCalled();

    consoleSpy.mockRestore();
  });
});
