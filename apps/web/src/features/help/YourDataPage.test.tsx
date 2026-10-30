/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useSettingsModalStore } from "@/state/useSettingsModalStore";

import { YourDataPage } from "./YourDataPage";
import { YOUR_DATA_IN_BRIEF } from "./yourDataBrief";

afterEach(() => {
  cleanup();
  useSettingsModalStore.setState({ isOpen: false, tab: "model" });
});

const HEADINGS = [
  "In brief",
  "What goes to AI model providers",
  "Other services",
  "What PathFinder keeps, and who can see it",
  "Deleting your data",
  "Learning from your strategies",
  "Using your own key",
  "When a model declines",
  "Questions or concerns",
];

describe("YourDataPage", () => {
  it("shows its title and the date it was last updated", () => {
    render(<YourDataPage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Your data in PathFinder" }),
    ).toBeVisible();
    expect(screen.getByText("Last updated: October 9, 2026")).toBeVisible();
  });

  it("shows the PathFinder logo above its title", () => {
    render(<YourDataPage />);

    const logo = screen.getByRole("img", { name: "PathFinder" });
    const title = screen.getByRole("heading", { level: 1 });
    expect(logo.compareDocumentPosition(title)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("gives the logo a line of its own under the back link", () => {
    render(<YourDataPage />);

    const logo = screen.getByRole("img", { name: "PathFinder" });
    const back = screen.getByRole("link", { name: "Back to PathFinder" });
    expect(logo.parentElement?.tagName).toBe("DIV");
    expect(logo.parentElement?.children).toHaveLength(1);
    expect(back.compareDocumentPosition(logo)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(logo).toHaveStyle({ width: "168px", height: "168px" });
  });

  it("pulls the logo left by its drawn margin so it lines up with the text", () => {
    render(<YourDataPage />);

    const wrapper = screen.getByRole("img", { name: "PathFinder" }).parentElement;
    expect(wrapper?.style.marginLeft).toBe("-18.2px");
  });

  it("sets the title as a large heading", () => {
    render(<YourDataPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveClass("mt-6", "text-3xl");
  });

  it("opens with the same points the sign-in notice shows", () => {
    const { container } = render(<YourDataPage />);

    const brief = container.querySelector("section#in-brief");
    expect(
      [...(brief?.querySelectorAll("li") ?? [])].map((li) => li.textContent),
    ).toEqual([...YOUR_DATA_IN_BRIEF]);
  });

  it("shows every section heading, in order", () => {
    render(<YourDataPage />);

    expect(
      screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent),
    ).toEqual(HEADINGS);
  });

  it("gives the sections the anchors other pages link to", () => {
    const { container } = render(<YourDataPage />);

    const ids = [...container.querySelectorAll("section")].map((s) => s.id);
    expect(ids).toEqual([
      "in-brief",
      "sent",
      "other-services",
      "kept",
      "deleting",
      "learning",
      "your-key",
      "declined",
      "contact",
    ]);
  });

  it("opens every outside page in a new tab that cannot reach back", () => {
    render(<YourDataPage />);

    const outside = screen
      .getAllByRole("link")
      .filter((link) => link.getAttribute("href")?.startsWith("https://"));
    expect(outside.map((link) => link.getAttribute("href"))).toEqual([
      "https://openai.com/enterprise-privacy/",
      "https://www.anthropic.com/legal/commercial-terms",
      "https://www.anthropic.com/legal/privacy",
      "https://ai.google.dev/gemini-api/terms",
    ]);
    for (const link of outside) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("stays short enough to read in a few minutes", () => {
    const { container } = render(<YourDataPage />);

    expect(container.textContent.split(/\s+/).length).toBeLessThan(1350);
  });

  it("names audits among what PathFinder keeps", () => {
    const { container } = render(<YourDataPage />);

    expect(container.querySelector("section#kept")).toHaveTextContent(
      "your gene sets, control sets, scored runs, audits, memories and ratings",
    );
  });

  it("says what deleting a conversation removes and what it keeps", () => {
    const { container } = render(<YourDataPage />);

    const deleting = container.querySelector("section#deleting");
    expect(deleting).toHaveTextContent(
      "It moves to Recently deleted, where you can restore it. Delete permanently, in Recently deleted, removes its messages, files, notes, strategy history, ratings and any copy waiting for review.",
    );
    expect(deleting).toHaveTextContent(
      "It keeps the gene sets, control sets and audits made in the conversation, your memories, and the strategy in your VEuPathDB account.",
    );
  });

  it("says a deleted memory is not saved again on its own", () => {
    const { container } = render(<YourDataPage />);

    expect(container.querySelector("section#deleting")).toHaveTextContent(
      "A deleted memory leaves a fingerprint of its content, so that PathFinder does not save it again on its own.",
    );
  });

  it("names every request that goes to OpenAI whichever model is picked", () => {
    const { container } = render(<YourDataPage />);

    const sent = container.querySelector("section#sent");
    expect(
      [...(sent?.querySelectorAll("li") ?? [])].map((li) => li.textContent),
    ).toEqual([
      "a check of your message, and of what the assistant's tools read, for hidden instructions, unless the deployment turns it off;",
      "conversation titles and summaries of long notes;",
      "matching what the assistant looks for to the site's searches and parameter values;",
      "turning memories and search words into numbers for search, with the text-embedding-3-large model.",
    ]);
  });

  it("says a key is opened only for the reply it pays for", () => {
    const { container } = render(<YourDataPage />);

    expect(container.querySelector("section#your-key")).toHaveTextContent(
      "It opens the key only when a reply starts, in the part of PathFinder that runs the assistant, and only for that reply.",
    );
  });

  it("gives the help address as a mail link", () => {
    render(<YourDataPage />);

    expect(screen.getByRole("link", { name: "help@veupathdb.org" })).toHaveAttribute(
      "href",
      "mailto:help@veupathdb.org",
    );
  });

  it.each([
    ["deleting", "Memory", "memory"],
    ["deleting", "Provider keys", "keys"],
    ["deleting", "Data", "data"],
    ["learning", "Privacy", "privacy"],
    ["your-key", "Provider keys", "keys"],
  ] as const)(
    "opens Settings from the %s section on the %s tab",
    async (section, name, tab) => {
      useSettingsModalStore.setState({ isOpen: false, tab: "advanced" });
      const { container } = render(<YourDataPage />);
      const body = container.querySelector<HTMLElement>(`section#${section}`);
      if (body === null) throw new Error(`no section ${section}`);

      const link = within(body).getByRole("link", { name });
      expect(link).toHaveAttribute("href", "/conversation");
      await userEvent.click(link);

      expect(useSettingsModalStore.getState()).toMatchObject({ isOpen: true, tab });
    },
  );
});
