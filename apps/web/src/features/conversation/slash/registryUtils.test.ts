import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { renderChatMarkdown } from "./registryUtils";

const MESSAGES: UIMessage[] = [
  {
    id: "m1",
    role: "user",
    parts: [{ type: "text", text: "Which kinases have a signal peptide?" }],
  },
  {
    id: "m2",
    role: "assistant",
    parts: [
      { type: "reasoning", text: "hidden" },
      { type: "text", text: "3 genes." },
    ],
  },
];

describe("renderChatMarkdown", () => {
  it("writes one section per message and keeps only the text parts", () => {
    expect(renderChatMarkdown(MESSAGES)).toBe(
      [
        "# PathFinder conversation export",
        "",
        "## user",
        "Which kinases have a signal peptide?",
        "",
        "---",
        "",
        "## assistant",
        "3 genes.",
        "",
        "---",
        "",
      ].join("\n"),
    );
  });

  it("writes the header alone for an empty transcript", () => {
    expect(renderChatMarkdown([])).toBe("# PathFinder conversation export\n");
  });
});
