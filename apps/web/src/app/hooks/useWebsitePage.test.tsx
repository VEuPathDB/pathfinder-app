// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook } from "@testing-library/react";

const goToWebsitePage = vi.hoisted(() => vi.fn());
vi.mock("@/lib/frameBridge", () => ({ goToWebsitePage }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/veupathdb/conversation/c1",
  useSearchParams: () => new URLSearchParams("step=2"),
}));

import { useWebsitePage } from "./useWebsitePage";

const SITE_PAGE = "https://muharram.veupathdb.org/eupathdb.amuharram/app/pathfinder";

afterEach(() => {
  cleanup();
  goToWebsitePage.mockReset();
});

describe("useWebsitePage", () => {
  it("offers the website page the address the tab shows, query included", () => {
    renderHook(() => useWebsitePage(SITE_PAGE));

    expect(goToWebsitePage.mock.calls).toEqual([
      [window, SITE_PAGE, "/veupathdb/conversation/c1?step=2"],
    ]);
  });
});
