/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createTestWrapper } from "@/lib/query/testing";

const reloadPage = vi.hoisted(() => vi.fn());
vi.mock("./reloadPage", () => ({ reloadPage }));

function serving(build: string, requested: string[]) {
  return vi.fn((input: string) => {
    requested.push(new URL(input).pathname);
    return Promise.resolve(Response.json({ build }));
  });
}

async function renderBanner() {
  const { NewReleaseBanner } = await import("./NewReleaseBanner");
  const { Wrapper } = createTestWrapper();
  return render(
    <Wrapper>
      <NewReleaseBanner />
      <div data-testid="app" />
    </Wrapper>,
  );
}

describe("NewReleaseBanner", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
    reloadPage.mockReset();
  });

  it("offers a reload when the server runs a newer build", async () => {
    vi.stubEnv("PATHFINDER_WEB_BUILD", "3f9a1c0be2d4");
    const requested: string[] = [];
    vi.stubGlobal("fetch", serving("77b0e5a91c3f", requested));

    await renderBanner();

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("PathFinder has been updated.");
    expect(requested).toEqual(["/pathfinder/api/v1/web-build"]);
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(reloadPage).toHaveBeenCalledTimes(1);
  });

  it("shows nothing while the tab runs the served build", async () => {
    vi.stubEnv("PATHFINDER_WEB_BUILD", "3f9a1c0be2d4");
    const requested: string[] = [];
    vi.stubGlobal("fetch", serving("3f9a1c0be2d4", requested));

    await renderBanner();

    await waitFor(() => {
      expect(requested).toEqual(["/pathfinder/api/v1/web-build"]);
    });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("asks nothing in a build that names no build id", async () => {
    vi.stubEnv("PATHFINDER_WEB_BUILD", "");
    const requested: string[] = [];
    vi.stubGlobal("fetch", serving("77b0e5a91c3f", requested));

    await renderBanner();

    expect(screen.getByTestId("app")).toBeInTheDocument();
    expect(requested).toEqual([]);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
