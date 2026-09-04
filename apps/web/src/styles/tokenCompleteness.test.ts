import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(
  fileURLToPath(new URL("./globals.css", import.meta.url)),
  "utf8",
);

const LIGHT_OPENER = ":root {";
const DARK_OPENER = ':root[data-theme="dark"] {';

const CHART_TOKENS = [
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  "--chart-6",
  "--chart-positive",
  "--chart-negative",
];

/**
 * A value that paints. A translucent `hsl(var(--x) / a)` counts too, so a
 * token defined in one ground only is still caught.
 */
const PAINTS =
  /^(?:[\d.]+ [\d.]+% [\d.]+%|rgba?\(.+\)|hsla?\(.+\)|oklch\(.+\)|#[0-9a-fA-F]{3,8})$/;

const DECLARATION = /^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);\s*$/;

const PAINTED_PROPERTY =
  /color|background|border|--(chart|kind|primary|accent|muted|success|warning|destructive|foreground|card|popover|sidebar|ring|input)/;

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** The text between an opener's braces, matched by depth. */
function bodyAfter(source: string, opener: string, from = 0): string {
  const start = source.indexOf(opener, from);
  if (start < 0) throw new Error(`globals.css has no "${opener}"`);
  let depth = 1;
  let index = start + opener.length;
  while (index < source.length && depth > 0) {
    const char = source[index];
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    index += 1;
  }
  if (depth !== 0) throw new Error(`"${opener}" is never closed`);
  return source.slice(start + opener.length, index - 1);
}

/** Every custom property in a block whose value paints, name to value. */
function paintedTokens(body: string): Map<string, string> {
  const found = new Map<string, string>();
  for (const line of body.split("\n")) {
    const match = DECLARATION.exec(line);
    if (match === null) continue;
    const [, name, value] = match;
    if (name === undefined || value === undefined) continue;
    const trimmed = value.trim();
    if (!PAINTS.test(trimmed)) continue;
    found.set(name, trimmed);
  }
  return found;
}

function mediaBodies(): string[] {
  const source = withoutComments(CSS);
  const bodies: string[] = [];
  for (const match of source.matchAll(/@media[^{]*\{/g)) {
    bodies.push(bodyAfter(source, match[0], match.index));
  }
  return bodies;
}

function significantLines(): string[] {
  return CSS.split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

const light = paintedTokens(bodyAfter(withoutComments(CSS), LIGHT_OPENER));
const dark = paintedTokens(bodyAfter(withoutComments(CSS), DARK_OPENER));

describe("the token layer defines every color on both grounds", () => {
  it("gives every light color token a dark value", () => {
    const missing = [...light.keys()].filter((name) => !dark.has(name)).sort();
    expect(missing).toEqual([]);
  });

  it("adds no dark color token that the light ground does not have", () => {
    const extra = [...dark.keys()].filter((name) => !light.has(name)).sort();
    expect(extra).toEqual([]);
    expect(dark.size).toBeGreaterThan(0);
  });

  it("declares the eight chart tokens on the dark ground", () => {
    const missing = CHART_TOKENS.filter((name) => !dark.has(name));
    expect(missing).toEqual([]);
  });

  it("repaints, rather than repeats, every color it carries to the dark ground", () => {
    const identical = [...light.entries()]
      .filter(([name, value]) => dark.get(name) === value)
      .map(([name]) => name);
    expect(identical).toEqual([]);
  });
});

describe("the dark ground is an attribute, not an operating system setting", () => {
  it("declares the dark utility variant right after the plugin", () => {
    expect(significantLines().slice(0, 4)).toEqual([
      '@import "tailwindcss";',
      '@import "tw-animate-css";',
      '@plugin "@tailwindcss/typography";',
      '@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));',
    ]);
  });

  it("has no .dark selector left", () => {
    const offenders = CSS.split("\n").filter((line) => /(^|\s)\.dark\b/.test(line));
    expect(offenders).toEqual([]);
  });

  it("puts the dark block after :root, so the light WCAG gate stays on light", () => {
    expect(CSS.indexOf(DARK_OPENER)).toBeGreaterThan(CSS.indexOf(LIGHT_OPENER));
  });

  it("paints nothing inside a media query", () => {
    const painted: string[] = [];
    for (const body of mediaBodies()) {
      for (const match of body.matchAll(/(^|[{;\s])(--[a-z0-9-]+|[a-z-]+)\s*:/g)) {
        const name = match[2];
        if (name === undefined) continue;
        if (PAINTED_PROPERTY.test(name)) painted.push(name);
      }
    }
    expect(painted).toEqual([]);
  });
});
