/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { OpenInSiteLink } from "./OpenInSiteLink";

describe("OpenInSiteLink", () => {
  it("is a plain link with no button type", () => {
    render(<OpenInSiteLink href="https://vectorbase.org/a" siteId="vectorbase" />);
    const link = screen.getByRole("link", { name: "Open in VectorBase" });
    expect(link).toHaveAttribute("aria-label", "Open in VectorBase");
    expect(link).toHaveAttribute("href", "https://vectorbase.org/a");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).not.toHaveAttribute("type");
  });

  it("calls onOpen when the reader follows the link", () => {
    const onOpen = vi.fn();
    render(
      <OpenInSiteLink
        href="https://vectorbase.org/a"
        siteId="vectorbase"
        onOpen={onOpen}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "Open in VectorBase" }));

    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
