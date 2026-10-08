import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation",
  useSearchParams: () => new URLSearchParams(""),
}));

import { FrameLocationReporter } from "./FrameLocationReporter";

const ORIGIN = "https://muharram.veupathdb.org";

afterEach(() => vi.unstubAllGlobals());

describe("FrameLocationReporter on the server", () => {
  it("posts nothing from a server render, during it or after it", async () => {
    const postMessage = vi.fn();
    vi.stubGlobal("window", {
      location: { origin: ORIGIN },
      parent: { location: { origin: ORIGIN }, postMessage },
    });

    expect(renderToString(<FrameLocationReporter />)).toBe("");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(postMessage).not.toHaveBeenCalled();
  });
});
