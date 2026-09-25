// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { EditorFooter } from "./EditorFooter";

const props = {
  syncState: "idle" as const,
  changeCount: 0,
  isSaving: false,
  onSave: vi.fn(),
  onDiscard: vi.fn(),
  count: 132,
  recordType: "transcript",
  wdkUrl: "https://plasmodb.org/plasmo/app/workspace/strategies/1",
};

describe("the link to the host site", () => {
  afterEach(cleanup);

  // The footer takes the site the strategy belongs to, not a pre-formatted
  // name, so a caller cannot label a PlasmoDB strategy with another site.
  it("names the site the strategy belongs to", () => {
    render(<EditorFooter {...props} siteId="plasmodb" />);

    const link = screen.getByRole("link", { name: "Open in PlasmoDB" });
    expect(link).toHaveAttribute("aria-label", "Open in PlasmoDB");
    expect(link.textContent).toBe("Open in PlasmoDB");
  });

  it("names a different site when the strategy is on one", () => {
    render(<EditorFooter {...props} siteId="toxodb" />);

    expect(screen.getByRole("link").textContent).toContain("ToxoDB");
  });

  it("leaves the organism parenthetical off the label", () => {
    render(<EditorFooter {...props} siteId="plasmodb" />);

    expect(screen.getByRole("link").textContent).not.toContain("(");
  });

  it("points at the url it was given", () => {
    render(<EditorFooter {...props} siteId="plasmodb" />);

    expect(screen.getByRole("link").getAttribute("href")).toBe(props.wdkUrl);
  });

  it("says VEuPathDB when the site is unknown", () => {
    render(<EditorFooter {...props} siteId="" />);

    expect(screen.getByRole("link", { name: "Open in VEuPathDB" })).toBeVisible();
  });

  it("renders no link without a url", () => {
    render(<EditorFooter {...props} wdkUrl={null} siteId="plasmodb" />);

    expect(screen.queryByRole("link")).toBe(null);
  });
});

describe("the step count", () => {
  afterEach(cleanup);

  it("counts a transcript step in genes", () => {
    render(<EditorFooter {...props} siteId="plasmodb" />);

    expect(screen.getByText("132 genes")).toBeInTheDocument();
  });
});
