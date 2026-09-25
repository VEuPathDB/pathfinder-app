// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

let pathnameMock = "/plasmodb/conversation/conv-1";
vi.mock("next/navigation", () => ({
  usePathname: () => pathnameMock,
}));

import { chatRoot } from "@/lib/routes";
import { EmbeddedToolbar } from "./EmbeddedToolbar";

function renderToolbar() {
  return render(<EmbeddedToolbar siteId="plasmodb" onOpenSettings={vi.fn()} />);
}

describe("EmbeddedToolbar", () => {
  afterEach(() => {
    cleanup();
    pathnameMock = "/plasmodb/conversation/conv-1";
  });

  it("points the chat link at the site's chat root, and links nothing else", () => {
    renderToolbar();
    expect(screen.getByLabelText("Go to conversation")).toHaveAttribute(
      "href",
      chatRoot("plasmodb"),
    );
    expect(
      screen.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual(["/plasmodb/conversation"]);
  });

  it("marks chat as the current page anywhere under the chat root", () => {
    renderToolbar();
    expect(screen.getByLabelText("Go to conversation")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("does not mark chat as current on another site's chat", () => {
    pathnameMock = "/toxodb/conversation/conv-1";
    renderToolbar();
    expect(screen.getByLabelText("Go to conversation")).not.toHaveAttribute(
      "aria-current",
    );
  });
});
