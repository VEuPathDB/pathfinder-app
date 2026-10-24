/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import Markdown from "react-markdown";
import { render } from "@testing-library/react";
import remarkGfm from "remark-gfm";
import { describe, expect, it } from "vitest";

import { renderChatMarkdown } from "../slash/registryUtils";

const FIRST =
  "The review kept it[^n1a2b3c4d-1].\n\n[^n1a2b3c4d-1]: review verdict: error";
const SECOND =
  "The second review rejected it[^n5e6f7a8b-1].\n\n[^n5e6f7a8b-1]: review verdict: no error";

const BACK_LINK = String.fromCharCode(0x21a9);

function notesOf(container: HTMLElement): string[] {
  const calls = Array.from(
    container.querySelectorAll<HTMLAnchorElement>("a[data-footnote-ref]"),
  );
  return calls.map((call) => {
    const id = decodeURIComponent(call.getAttribute("href")?.slice(1) ?? "");
    const target = container.ownerDocument.getElementById(id);
    return target?.textContent.replace(BACK_LINK, "").trim() ?? "";
  });
}

describe("a reply's notes", () => {
  it("resolve to their own reply's values when two replies share the thread", () => {
    const { container } = render(
      <div>
        <Markdown remarkPlugins={[remarkGfm]}>{FIRST}</Markdown>
        <Markdown remarkPlugins={[remarkGfm]}>{SECOND}</Markdown>
      </div>,
    );

    expect(notesOf(container)).toEqual([
      "review verdict: error",
      "review verdict: no error",
    ]);
  });

  it("resolve to their own reply's values in the exported conversation", () => {
    const messages: UIMessage[] = [
      { id: "m1", role: "assistant", parts: [{ type: "text", text: FIRST }] },
      { id: "m2", role: "assistant", parts: [{ type: "text", text: SECOND }] },
    ];

    const { container } = render(
      <Markdown remarkPlugins={[remarkGfm]}>{renderChatMarkdown(messages)}</Markdown>,
    );

    expect(notesOf(container)).toEqual([
      "review verdict: error",
      "review verdict: no error",
    ]);
  });
});
