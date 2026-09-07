/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("@/app/components/SystemReadyGate", () => ({
  SystemReadyGate: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="system-ready-gate">{children}</div>
  ),
}));

import SiteLayout from "./layout";

afterEach(cleanup);

describe("SiteLayout", () => {
  it("gates the site subtree on the process being ready and nothing else", () => {
    render(<SiteLayout>{<div data-testid="site-children" />}</SiteLayout>);

    const gate = screen.getByTestId("system-ready-gate");
    expect(gate.contains(screen.getByTestId("site-children"))).toBe(true);
    expect(screen.queryByTestId("site-unavailable-notice")).not.toBeInTheDocument();
  });
});
