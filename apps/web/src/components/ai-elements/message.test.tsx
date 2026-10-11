/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Message, MessageAction, MessageContent, MessageResponse } from "./message";

describe("a message's blocks", () => {
  it("are spaced by the one paragraph gap the content container owns", () => {
    const { container } = render(
      <MessageContent>
        <p>a block</p>
      </MessageContent>,
    );
    const body = container.firstElementChild;
    if (!(body instanceof HTMLElement)) throw new Error("the content drew nothing");
    const tokens = body.className.split(/\s+/);
    expect(tokens).toContain("gap-3");
    expect(tokens.filter((token) => token.startsWith("gap-"))).toEqual(["gap-3"]);
  });

  it("share that gap with the message's own action bar", () => {
    const { container } = render(
      <Message from="assistant">
        <p>a block</p>
      </Message>,
    );
    const root = container.firstElementChild;
    if (!(root instanceof HTMLElement)) throw new Error("the message drew nothing");
    expect(root.className.split(/\s+/)).toContain("gap-3");
  });
});

describe("a message action button", () => {
  it("carries the tooltip as its accessible name", () => {
    render(
      <MessageAction tooltip="Copy response">
        <svg aria-hidden />
      </MessageAction>,
    );
    const button = screen.getByRole("button", { name: "Copy response" });
    expect(button.getAttribute("aria-label")).toBe("Copy response");
  });

  it("prefers an explicit label over the tooltip", () => {
    render(
      <MessageAction tooltip="Branch to a new chat from here" label="Branch">
        <svg aria-hidden />
      </MessageAction>,
    );
    expect(screen.getByRole("button", { name: "Branch" })).toBeDefined();
  });

  it("names a button that has no tooltip", () => {
    render(
      <MessageAction label="Regenerate">
        <svg aria-hidden />
      </MessageAction>,
    );
    expect(
      screen.getByRole("button", { name: "Regenerate" }).getAttribute("aria-label"),
    ).toBe("Regenerate");
  });
});

describe("a response with math", () => {
  it("renders inline math as KaTeX with its MathML", async () => {
    const { container } = render(
      <MessageResponse>{"The fold change is $x^2$."}</MessageResponse>,
    );
    await screen.findByText("The fold change is", { exact: false });
    const math = container.querySelector(".katex math");
    if (!(math instanceof Element)) throw new Error("the math drew no KaTeX markup");
    expect(math.querySelector("msup")?.textContent).toBe("x2");
  });
});
