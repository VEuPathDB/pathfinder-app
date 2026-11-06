import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { composite, contrast, hslToRgb, type Rgb } from "@/lib/color/contrast";

const CSS = readFileSync(
  fileURLToPath(new URL("./globals.css", import.meta.url)),
  "utf8",
);

const DARK_OPENER = ':root[data-theme="dark"] {';

const THEMES = {
  light: CSS.slice(0, CSS.indexOf(DARK_OPENER)),
  dark: CSS.slice(CSS.indexOf(DARK_OPENER)),
};

function readToken(source: string, name: string): Rgb {
  const match = source.match(
    new RegExp(`--${name}:\\s*([\\d.]+)\\s+([\\d.]+)%\\s+([\\d.]+)%\\s*;`),
  );
  const [, h, s, l] = match ?? [];
  if (h === undefined || s === undefined || l === undefined) {
    throw new Error(`token --${name} is not an "H S% L%" triple`);
  }
  return hslToRgb(Number(h), Number(s), Number(l));
}

function ruleBody(selector: string): string {
  const start = CSS.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`globals.css has no ${selector} rule`);
  return CSS.slice(start, CSS.indexOf("}", start));
}

function thumbAlpha(selector: string): number {
  const match = ruleBody(selector).match(
    /background:\s*hsl\(var\(--muted-foreground\)\s*\/\s*([\d.]+)\)/,
  );
  if (match?.[1] === undefined) {
    throw new Error(`${selector} is not --muted-foreground at an alpha`);
  }
  return Number(match[1]);
}

const AA_TEXT = 4.5;
const AA_NON_TEXT = 3;
const SCROLL_SURFACES = ["background", "card", "sidebar", "muted"] as const;

describe("the root text size", () => {
  it("sets the body text in rem, so the text size setting scales it", () => {
    expect(ruleBody("\n\n  body")).toMatch(/font-size:\s*0\.875rem;/);
  });
});

describe("scrollbars", () => {
  const rest = thumbAlpha("  ::-webkit-scrollbar-thumb");
  const hover = thumbAlpha("  ::-webkit-scrollbar-thumb:hover");

  it("darkens the thumb under the pointer", () => {
    expect(hover).toBeGreaterThan(rest);
  });

  for (const [theme, source] of Object.entries(THEMES)) {
    for (const surface of SCROLL_SURFACES) {
      it(`shows the resting thumb on --${surface} in the ${theme} theme`, () => {
        const ground = readToken(source, surface);
        const thumb = composite(readToken(source, "muted-foreground"), ground, rest);
        expect(contrast(thumb, ground)).toBeGreaterThanOrEqual(AA_NON_TEXT);
      });
    }
  }

  it("gives Firefox a visible thumb through the standard properties", () => {
    const start = CSS.indexOf("@supports not selector(::-webkit-scrollbar)");
    expect(start).toBeGreaterThan(-1);
    const block = CSS.slice(start, CSS.indexOf("}\n", start));
    expect(block).toMatch(
      /scrollbar-color:\s*hsl\(var\(--muted-foreground\)\s*\/\s*[\d.]+\)\s+transparent;/,
    );
    expect(block).toMatch(/scrollbar-width:\s*thin;/);
  });

  it("keeps the utility that hides a scrollbar on purpose", () => {
    const utility = CSS.slice(CSS.indexOf("@utility no-scrollbar {"));
    expect(utility).toMatch(/scrollbar-width:\s*none;/);
    expect(utility).toMatch(/&::-webkit-scrollbar\s*\{\s*display:\s*none;/);
  });
});

describe("the rail's progress tabs", () => {
  for (const [theme, source] of Object.entries(THEMES)) {
    const ground = readToken(source, "background");
    const hoverFill = composite(readToken(source, "muted"), ground, 0.6);

    it(`reads the active tab in --foreground in the ${theme} theme`, () => {
      expect(contrast(readToken(source, "foreground"), ground)).toBeGreaterThanOrEqual(
        AA_TEXT,
      );
    });

    it(`reads an inactive tab in --muted-foreground in the ${theme} theme`, () => {
      const inactive = readToken(source, "muted-foreground");
      expect(contrast(inactive, ground)).toBeGreaterThanOrEqual(AA_TEXT);
      expect(
        contrast(readToken(source, "foreground"), hoverFill),
      ).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it(`sets the active underline apart from the ground in the ${theme} theme`, () => {
      expect(contrast(readToken(source, "primary"), ground)).toBeGreaterThanOrEqual(
        AA_NON_TEXT,
      );
    });
  }
});
