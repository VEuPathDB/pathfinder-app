/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { OpenInSiteLink } from "./OpenInSiteLink";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OpenInSiteLink", () => {
  it("opens a new tab inside the website page", () => {
    vi.spyOn(window, "top", "get").mockReturnValue(null);
    render(<OpenInSiteLink href="https://qa.vectorbase.org/a" siteId="vectorbase" />);
    const link = screen.getByRole("link", { name: "Open in VectorBase" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("is a plain link with no button type", () => {
    render(<OpenInSiteLink href="https://qa.vectorbase.org/a" siteId="vectorbase" />);
    const link = screen.getByRole("link", { name: "Open in VectorBase" });
    expect(link).toHaveAttribute("aria-label", "Open in VectorBase");
    expect(link).toHaveAttribute("href", "https://qa.vectorbase.org/a");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).not.toHaveAttribute("type");
  });

  it("calls onOpen when the reader follows the link", () => {
    const onOpen = vi.fn();
    render(
      <OpenInSiteLink
        href="https://qa.vectorbase.org/a"
        siteId="vectorbase"
        onOpen={onOpen}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "Open in VectorBase" }));

    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
