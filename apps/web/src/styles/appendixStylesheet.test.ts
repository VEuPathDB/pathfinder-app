import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const globals = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "globals.css"),
  "utf8",
);

function ruleFor(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(globals);
  if (found?.[1] === undefined) throw new Error(`no rule for ${selector}`);
  return found[1];
}

function layerOf(selector: string): string | null {
  const at = globals.indexOf(`\n${selector}`);
  const before = globals.slice(0, at);
  const opened = before.lastIndexOf("@layer");
  if (opened === -1) return null;
  const depth = [...before.slice(opened)].reduce(
    (level, char) => level + (char === "{" ? 1 : char === "}" ? -1 : 0),
    0,
  );
  return depth > 0 ? before.slice(opened) : null;
}

describe("the turn appendix's type", () => {
  it("sets one size for every body text of every section", () => {
    expect(ruleFor(".turn-appendix-body *")).toMatch(/font-size:\s*0\.8125rem/);
  });

  it("sets one size for every section heading", () => {
    expect(ruleFor(".turn-appendix-body h3,\n.turn-appendix-body h3 *")).toMatch(
      /font-size:\s*0\.875rem/,
    );
  });

  it("sits outside every layer, so it wins over a card's own size classes", () => {
    expect(layerOf(".turn-appendix-body *")).toBe(null);
  });
});
