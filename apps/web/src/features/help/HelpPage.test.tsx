/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { SiteFrame } from "@/lib/sites/currentSite";
import { useSettingsModalStore } from "@/state/useSettingsModalStore";

import { HelpPage } from "./HelpPage";

afterEach(() => {
  cleanup();
  useSettingsModalStore.setState({ isOpen: false, tab: "model" });
});

const HEADINGS = [
  "What PathFinder does",
  "Signing in and choosing a site",
  "How a conversation works",
  "What to check",
  "Memory",
  "Models",
  "When a model declines",
  "Saving and exporting",
  "Your data",
];

const LOCKED: SiteFrame = { kind: "locked", siteId: "plasmodb" };
const SWITCHABLE: SiteFrame = { kind: "switchable" };
const UNKNOWN: SiteFrame = { kind: "unknown" };

function section(container: HTMLElement, id: string): HTMLElement {
  const found = container.querySelector<HTMLElement>(`section#${id}`);
  if (found === null) throw new Error(`no section ${id}`);
  return found;
}

describe("HelpPage", () => {
  it("shows its title and every section heading, in order", () => {
    render(<HelpPage site={LOCKED} />);

    expect(screen.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent),
    ).toEqual(HEADINGS);
  });

  it("names what PathFinder can do beyond building a strategy", () => {
    const { container } = render(<HelpPage site={LOCKED} />);

    expect(
      [...section(container, "what").querySelectorAll("li")].map(
        (item) => item.textContent.split(".")[0],
      ),
    ).toEqual([
      "Check a strategy against genes you already know",
      "Look for searches that separate your known genes",
      "Try other settings for one search and score each setting against your known genes",
      "Explore study data",
      "Remember useful results from one conversation to the next",
    ]);
  });

  it("names the site a component site's website locks, and no site switch", () => {
    const { container } = render(<HelpPage site={LOCKED} />);

    expect(section(container, "sign-in")).toHaveTextContent(
      "Here, PathFinder works on PlasmoDB.",
    );
    expect(container).not.toHaveTextContent("Switch site");
  });

  it("names Switch site where the website offers it", () => {
    const { container } = render(<HelpPage site={SWITCHABLE} />);

    expect(section(container, "sign-in")).toHaveTextContent(
      "To start a conversation on another site, choose Switch site at the bottom of the left bar and pick the site.",
    );
  });

  it("names neither the site nor the switch before the site is known", () => {
    const { container } = render(<HelpPage site={UNKNOWN} />);

    expect(section(container, "sign-in")).toHaveTextContent(
      "Each conversation stays on the site where you started it.",
    );
    expect(container).not.toHaveTextContent("Switch site");
    expect(container).not.toHaveTextContent("Here, PathFinder works on");
  });

  it("names the answers each card waits for and the stop control", () => {
    const { container } = render(<HelpPage site={LOCKED} />);

    const conversation = section(container, "conversation");
    expect(conversation).toHaveTextContent("choose Yes or No");
    expect(conversation).toHaveTextContent("it asks you to Approve or Deny");
    expect(conversation).toHaveTextContent(
      "To stop a reply while it is being written, choose Stop in the message box.",
    );
  });

  it("links to the data statement from its own section", () => {
    render(<HelpPage site={LOCKED} />);

    expect(
      screen.getByRole("link", { name: "Your data in PathFinder" }),
    ).toHaveAttribute("href", "/help/your-data");
  });

  it("links a declined request to the section that explains it", () => {
    render(<HelpPage site={LOCKED} />);

    expect(
      screen.getByRole("link", { name: "what PathFinder does when a model declines" }),
    ).toHaveAttribute("href", "/help/your-data#declined");
  });

  it("leads back to the app", () => {
    render(<HelpPage site={LOCKED} />);

    expect(screen.getByRole("link", { name: "Back to PathFinder" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it.each([
    ["Memory", "memory"],
    ["Model", "model"],
    ["Provider keys", "keys"],
  ] as const)("opens Settings on the %s tab from its mention", async (name, tab) => {
    useSettingsModalStore.setState({ isOpen: false, tab: "advanced" });
    render(<HelpPage site={LOCKED} />);

    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("href", "/conversation");
    await userEvent.click(link);

    expect(useSettingsModalStore.getState()).toMatchObject({ isOpen: true, tab });
  });

  it("names Settings as the only way to the model", () => {
    const { container } = render(<HelpPage site={LOCKED} />);

    expect(section(container, "models")).toHaveTextContent(
      "To change it, open Settings and the Model tab.",
    );
  });
});
