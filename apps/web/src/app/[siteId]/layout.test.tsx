/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("@/app/components/SystemReadyGate", () => ({
  SystemReadyGate: ({
    siteId,
    children,
  }: {
    siteId: string;
    children: React.ReactNode;
  }) => (
    <div data-testid="system-ready-gate" data-site-id={siteId}>
      {children}
    </div>
  ),
}));

import SiteLayout from "./layout";

afterEach(cleanup);

describe("SiteLayout", () => {
  it("gates the site subtree on the process being ready and nothing else", async () => {
    render(
      await SiteLayout({
        children: <div data-testid="site-children" />,
        params: Promise.resolve({ siteId: "plasmodb" }),
      }),
    );

    const gate = screen.getByTestId("system-ready-gate");
    expect(gate).toHaveAttribute("data-site-id", "plasmodb");
    expect(gate.contains(screen.getByTestId("site-children"))).toBe(true);
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
  });
});
