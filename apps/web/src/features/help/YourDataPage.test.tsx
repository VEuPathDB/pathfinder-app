/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { YourDataPage } from "./YourDataPage";
import { YOUR_DATA_IN_BRIEF } from "./yourDataBrief";

afterEach(cleanup);

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

    expect(container.textContent.split(/\s+/).length).toBeLessThan(1150);
  });

  it("names audits among what PathFinder keeps", () => {
    const { container } = render(<YourDataPage />);

    expect(container.querySelector("section#kept")).toHaveTextContent(
      "your gene sets, control sets, scored runs, audits, memories and ratings",
    );
  });

  it("says deleting a conversation keeps its audits and where they are deleted", () => {
    const { container } = render(<YourDataPage />);

    expect(container.querySelector("section#deleting")).toHaveTextContent(
      "Delete permanently removes it with any copy waiting for review, but not its audits.",
    );
    expect(container.querySelector("section#deleting")).toHaveTextContent(
      "Settings deletes memories, provider keys and everything at once, audits included, on its Memory, Provider keys and Data tabs.",
    );
  });

  it("gives the help address as a mail link", () => {
    render(<YourDataPage />);

    expect(screen.getByRole("link", { name: "help@veupathdb.org" })).toHaveAttribute(
      "href",
      "mailto:help@veupathdb.org",
    );
  });
});
