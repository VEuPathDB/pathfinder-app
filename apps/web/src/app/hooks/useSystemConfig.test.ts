/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { createSuspenseWrapper } from "@/lib/query/testing";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetSystemConfig = vi.hoisted(() => vi.fn());

vi.mock("@pathfinder/shared/generated/hooks/useSystemConfig", () => ({
  systemConfig: mockGetSystemConfig,
  systemConfigQueryOptions: () => ({
    queryKey: ["config", "system"] as const,
    queryFn: mockGetSystemConfig,
    staleTime: Infinity,
  }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** A fully-populated SystemConfigResponse matching the real Zod schema. */
function makeConfigResponse(overrides: { llmConfigured: boolean }) {
  return {
    chatProvider: "anthropic",
    llmConfigured: overrides.llmConfigured,
    providers: {
      openai: false,
      anthropic: overrides.llmConfigured,
      google: false,
      ollama: false,
    },
  };
}

async function importAndRender() {
  const { useSystemConfig } = await import("./useSystemConfig");
  const { Wrapper } = createSuspenseWrapper();
  return renderHook(() => useSystemConfig(), { wrapper: Wrapper });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useSystemConfig", () => {
  beforeEach(() => {
    vi.resetModules();
    mockGetSystemConfig.mockReset();
  });

  it("suspends until config resolves, then returns setupRequired=false when LLM is configured", async () => {
    mockGetSystemConfig.mockResolvedValue(makeConfigResponse({ llmConfigured: true }));

    const { result } = await importAndRender();

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    expect(result.current.setupRequired).toBe(false);
  });

  it("returns setupRequired=true when LLM is NOT configured", async () => {
    mockGetSystemConfig.mockResolvedValue(makeConfigResponse({ llmConfigured: false }));

    const { result } = await importAndRender();

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    expect(result.current.setupRequired).toBe(true);
  });

  it("retry() triggers a refetch after initial success", async () => {
    mockGetSystemConfig
      .mockResolvedValueOnce(makeConfigResponse({ llmConfigured: false }))
      .mockResolvedValueOnce(makeConfigResponse({ llmConfigured: true }));

    const { result } = await importAndRender();

    await waitFor(() => {
      expect(result.current).not.toBeNull();
    });

    // First response: llmConfigured=false -> setupRequired=true
    expect(result.current.setupRequired).toBe(true);
    expect(mockGetSystemConfig).toHaveBeenCalledTimes(1);

    // Trigger retry
    result.current.retry();

    await waitFor(() => {
      expect(mockGetSystemConfig).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      // Second response: llmConfigured=true -> setupRequired=false
      expect(result.current.setupRequired).toBe(false);
    });
  });
});
