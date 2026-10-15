/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { healthCheckQueryKey } from "@pathfinder/shared/generated/hooks/useHealthCheck";

import { createTestWrapper } from "@/lib/query/testing";

import { PathFinderMark } from "./PathFinderMark";

const HEALTH = {
  status: "healthy",
  version: "0.2.0b15",
  timestamp: "2026-10-15T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderMark() {
  const { queryClient, Wrapper } = createTestWrapper();
  render(<PathFinderMark />, { wrapper: Wrapper });
  return queryClient;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PathFinderMark", () => {
  it("shows the logo, which is neither a link nor a button", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(HEALTH)),
    );
    renderMark();

    const mark = screen.getByRole("img", { name: "PathFinder" });
    const sources = Array.from(mark.querySelectorAll("img")).map((img) =>
      img.getAttribute("src"),
    );
    expect(sources).toEqual([
      "/pathfinder/brand/pathfinder-mark-light.svg",
      "/pathfinder/brand/pathfinder-mark-dark.svg",
    ]);
    expect(screen.queryByRole("link", { name: "PathFinder" })).toBeNull();
    expect(screen.queryByRole("button", { name: "PathFinder" })).toBeNull();
  });

  it("names the release the api reports on hover", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(HEALTH)),
    );
    const queryClient = renderMark();
    await waitFor(() =>
      expect(queryClient.getQueryState(healthCheckQueryKey())?.status).toBe("success"),
    );

    await userEvent.hover(screen.getByRole("img", { name: "PathFinder" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "PathFinder v0.2.0b15",
    );
  });

  it("names the release on a touch tap", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(HEALTH)),
    );
    const queryClient = renderMark();
    await waitFor(() =>
      expect(queryClient.getQueryState(healthCheckQueryKey())?.status).toBe("success"),
    );

    await userEvent.pointer({
      keys: "[TouchA]",
      target: screen.getByRole("img", { name: "PathFinder" }),
    });

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "PathFinder v0.2.0b15",
    );
  });

  it("names the product alone when the api does not answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "down" }, 500)),
    );
    const queryClient = renderMark();
    await waitFor(() =>
      expect(queryClient.getQueryState(healthCheckQueryKey())?.status).toBe("error"),
    );

    await userEvent.hover(screen.getByRole("img", { name: "PathFinder" }));

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent(/^PathFinder$/);
  });
});
