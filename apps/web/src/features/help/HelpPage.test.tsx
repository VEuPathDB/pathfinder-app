/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { HelpPage } from "./HelpPage";

afterEach(cleanup);

const HEADINGS = [
  "What PathFinder does",
  "Signing in and choosing a site",
  "How a conversation works",
  "What to check",
  "Models",
  "When a model declines",
  "Saving and exporting",
  "Your data",
];

describe("HelpPage", () => {
  it("shows its title and every section heading, in order", () => {
    render(<HelpPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent),
    ).toEqual(HEADINGS);
  });

  it("links to the data statement from its own section", () => {
    render(<HelpPage />);

    expect(
      screen.getByRole("link", { name: "Your data in PathFinder" }),
    ).toHaveAttribute("href", "/help/your-data");
  });

  it("links a declined request to the section that explains it", () => {
    render(<HelpPage />);

    expect(
      screen.getByRole("link", { name: "what PathFinder does when a model declines" }),
    ).toHaveAttribute("href", "/help/your-data#declined");
  });

  it("leads back to the app", () => {
    render(<HelpPage />);

    expect(screen.getByRole("link", { name: "Back to PathFinder" })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
