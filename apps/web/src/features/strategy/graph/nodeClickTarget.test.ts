/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { isNodeToolbarOrMenuTarget } from "./nodeClickTarget";

function wrap(attrs: Record<string, string>, child: HTMLElement): HTMLElement {
  const parent = document.createElement("div");
  for (const [k, v] of Object.entries(attrs)) parent.setAttribute(k, v);
  parent.appendChild(child);
  return child;
}

function leaf(attrs: Record<string, string> = {}): HTMLElement {
  const el = document.createElement("div");
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

describe("isNodeToolbarOrMenuTarget", () => {
  it("is true for a click inside the node hover toolbar", () => {
    expect(isNodeToolbarOrMenuTarget(wrap({ "data-node-toolbar": "" }, leaf()))).toBe(
      true,
    );
  });

  it("is true for a click on a portaled dropdown menu item", () => {
    // The kebab DropdownMenuContent portals to <body>, but React events still
    // bubble to onNodeClick - the guard must catch the menuitem by role.
    expect(
      isNodeToolbarOrMenuTarget(wrap({ role: "menu" }, leaf({ role: "menuitem" }))),
    ).toBe(true);
  });

  it("is false for a click on the node body", () => {
    expect(isNodeToolbarOrMenuTarget(leaf())).toBe(false);
  });

  it("is false for a non-element target", () => {
    expect(isNodeToolbarOrMenuTarget(null)).toBe(false);
  });
});
