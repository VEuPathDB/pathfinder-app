/**
 * @vitest-environment jsdom
 */
import { render } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { describe, expect, it } from "vitest";

import { modelMarkdownComponents } from "@/lib/markdown/modelImage";

import type { StructuralPart } from "../parts";
import { VouchedLink, VouchedLinks, vouchedLinksOf } from "./vouchedLinks";

const RECORD = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100";
const PAPER = "https://doi.org/10.1371/journal.ppat.1";

function renderReply(markdown: string) {
  return render(
    <VouchedLinks value={new Set([RECORD, PAPER])}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ ...modelMarkdownComponents, a: VouchedLink }}
      >
        {markdown}
      </ReactMarkdown>
    </VouchedLinks>,
  );
}

function hrefs(container: HTMLElement): (string | null)[] {
  return [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
}

describe("vouchedLinksOf", () => {
  it("reads the links the reply's part vouches for", () => {
    const content = [
      { type: "text", text: "hi" },
      { type: "data-reply-links", data: { links: [RECORD, PAPER] } },
    ] as unknown as StructuralPart[];

    expect([...vouchedLinksOf(content)]).toEqual([RECORD, PAPER]);
  });

  it("vouches for nothing when the reply carries no links part", () => {
    const content = [{ type: "text", text: "hi" }] as unknown as StructuralPart[];

    expect(vouchedLinksOf(content).size).toBe(0);
  });
});

describe("a reply's links", () => {
  it("links a record and a source the turn vouched for, in a new tab", () => {
    const { container } = renderReply(
      `See [PF3D7_1315100](${RECORD}) and [the paper](${PAPER}).`,
    );

    expect(hrefs(container)).toEqual([RECORD, PAPER]);
    for (const anchor of container.querySelectorAll("a")) {
      expect([anchor.target, anchor.rel]).toEqual(["_blank", "noopener noreferrer"]);
    }
  });

  it.each([
    "[x](http://evil.example)",
    "[x][r]\n\n[r]: http://evil.example",
    "Run javascript:alert(1) now.",
    '<a href="https://evil.example">x</a>',
    "![chart](https://evil.example/c.png)",
    "Write to <mailto:curator@example.org> or www.evil.example.",
    "Visit https://evil.example/?q=leak now.",
    `[the paper](${PAPER}?q=leak)`,
  ])("writes no link and no image for %j", (markdown) => {
    const { container } = renderReply(markdown);

    expect(hrefs(container)).toEqual([]);
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("keeps the words of a link it does not vouch for", () => {
    const { container } = renderReply("Read [the review](http://evil.example).");

    expect(container.textContent).toBe("Read the review.");
  });

  it("renders the markdown the model wrote", () => {
    const { container } = renderReply(
      "## Reading\n\n- **SignalP 6.0**\n- `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |",
    );

    expect(
      ["h2", "li", "strong", "code", "table"].map(
        (tag) => container.querySelectorAll(tag).length,
      ),
    ).toEqual([1, 2, 1, 1, 1]);
  });
});
