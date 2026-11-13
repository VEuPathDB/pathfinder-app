/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useSettingsModalStore } from "@/state/useSettingsModalStore";

import { HelpPage } from "./HelpPage";

afterEach(() => {
  cleanup();
  useSettingsModalStore.setState({ isOpen: false, tab: "model" });
});

const HEADINGS = [
  "What Strategist does",
  "Signing in and your site",
  "How a conversation works",
  "What to check",
  "Memory",
  "Models",
  "When a model declines",
  "Saving and exporting",
  "Your data",
];

function section(container: HTMLElement, id: string): HTMLElement {
  const found = container.querySelector<HTMLElement>(`section#${id}`);
  if (found === null) throw new Error(`no section ${id}`);
  return found;
}

describe("HelpPage", () => {
  it("shows its title and every section heading, in order", () => {
    render(<HelpPage siteId="plasmodb" />);

    expect(screen.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent),
    ).toEqual(HEADINGS);
  });

  it("names what Strategist can do beyond building a strategy", () => {
    const { container } = render(<HelpPage siteId="plasmodb" />);

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

  it("names the site it works on, and no site switch", () => {
    const { container } = render(<HelpPage siteId="plasmodb" />);

    expect(section(container, "sign-in")).toHaveTextContent(
      "Here, Strategist works on PlasmoDB.",
    );
    expect(container).not.toHaveTextContent("Switch site");
  });

  it("names no site before the site is known", () => {
    const { container } = render(<HelpPage siteId={null} />);

    expect(section(container, "sign-in")).toHaveTextContent(
      "Each conversation stays on the site where you started it.",
    );
    expect(container).not.toHaveTextContent("Here, Strategist works on");
  });

  it("names the answers each card waits for and the stop control", () => {
    const { container } = render(<HelpPage siteId="plasmodb" />);

    const conversation = section(container, "conversation");
    expect(conversation).toHaveTextContent("choose Yes or No");
    expect(conversation).toHaveTextContent("it asks you to Approve or Deny");
    expect(conversation).toHaveTextContent(
      "To stop a reply while it is being written, choose Stop in the message box.",
    );
  });

  it("links to the data statement from its own section", () => {
    render(<HelpPage siteId="plasmodb" />);

    expect(
      screen.getByRole("link", { name: "Your data in Strategist" }),
    ).toHaveAttribute("href", "/help/your-data");
  });

  it("links a declined request to the section that explains it", () => {
    render(<HelpPage siteId="plasmodb" />);

    expect(
      screen.getByRole("link", { name: "what Strategist does when a model declines" }),
    ).toHaveAttribute("href", "/help/your-data#declined");
  });

  it("leads back to the app", () => {
    render(<HelpPage siteId="plasmodb" />);

    expect(screen.getByRole("link", { name: "Back to Strategist" })).toHaveAttribute(
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
    render(<HelpPage siteId="plasmodb" />);

    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("href", "/conversation");
    await userEvent.click(link);

    expect(useSettingsModalStore.getState()).toMatchObject({ isOpen: true, tab });
  });

  it("names Settings as the only way to the model", () => {
    const { container } = render(<HelpPage siteId="plasmodb" />);

    expect(section(container, "models")).toHaveTextContent(
      "To change it, open Settings and the Model tab.",
    );
  });
});
