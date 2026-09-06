// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import { composite, contrast, hslToRgb, type Rgb } from "@/lib/color/contrast";

import { applySiteTheme, SITE_IDS } from "./siteTheme";

const WRITTEN = [
  "--primary",
  "--primary-foreground",
  "--ring",
  "--secondary",
  "--accent",
  "--muted",
];

const WHITE: Rgb = [1, 1, 1];
const AA_NORMAL_TEXT = 4.5;

/** `hover:bg-primary/90` on the default button variant. */
const HOVER_ALPHA = 0.9;

const DARK_GROUND: Rgb = hslToRgb(215, 28, 9);

/** plasmodb's brand hex #634697 is hsl(261 37% 43%). */
const PLASMODB_BRAND_LIGHTNESS = 43;

function parseHsl(value: string): [number, number, number] {
  const match = /^(\d+(?:\.\d+)?) (\d+(?:\.\d+)?)% (\d+(?:\.\d+)?)%$/.exec(
    value.trim(),
  );
  if (match === null) throw new Error(`unexpected --primary format: "${value}"`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function written(name: string): [number, number, number] {
  return parseHsl(document.documentElement.style.getPropertyValue(name));
}

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  for (const name of WRITTEN) {
    document.documentElement.style.removeProperty(name);
  }
});

describe("applySiteTheme on the light ground", () => {
  it.each(SITE_IDS)(
    "sets a --primary that meets WCAG AA white-text contrast for %s",
    (siteId) => {
      applySiteTheme(siteId);
      const [h, s, l] = written("--primary");
      expect(contrast(WHITE, hslToRgb(h, s, l))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    },
  );

  it("preserves the brand hue while darkening for contrast (toxodb green)", () => {
    applySiteTheme("toxodb");
    const [h] = written("--primary");
    expect(h).toBeGreaterThan(90);
    expect(h).toBeLessThan(150);
  });

  it.each(SITE_IDS)(
    "keeps white legible on the hover:bg-primary/90 composite for %s",
    (siteId) => {
      applySiteTheme(siteId);
      const [h, s, l] = written("--primary");
      const hover = composite(hslToRgb(h, s, l), WHITE, HOVER_ALPHA);
      expect(contrast(WHITE, hover)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    },
  );

  it("writes a white primary foreground and near-white tinted surfaces", () => {
    applySiteTheme("plasmodb");
    expect(written("--primary-foreground")).toEqual([0, 0, 100]);
    expect(written("--secondary")[2]).toBe(95);
    expect(written("--accent")[2]).toBe(93);
    expect(written("--muted")[2]).toBe(96);
  });
});

describe("applySiteTheme on the dark ground", () => {
  it("raises the brand lightness instead of lowering it", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    applySiteTheme("plasmodb");
    const [, , l] = written("--primary");
    expect(l).toBeGreaterThan(PLASMODB_BRAND_LIGHTNESS);
  });

  it("keeps the brand hue while lightening (plasmodb purple)", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    applySiteTheme("plasmodb");
    const [h] = written("--primary");
    expect(h).toBeGreaterThan(240);
    expect(h).toBeLessThan(290);
  });

  it("writes a dark primary foreground that reads on the brand fill", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    applySiteTheme("plasmodb");
    const foreground = written("--primary-foreground");
    const primary = written("--primary");
    expect(foreground).toEqual([215, 28, 9]);
    expect(
      contrast(hslToRgb(...foreground), hslToRgb(...primary)),
    ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it("writes dark tinted surfaces, not near-white ones", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    applySiteTheme("plasmodb");
    expect(written("--secondary")[2]).toBe(16);
    expect(written("--accent")[2]).toBe(18);
    expect(written("--muted")[2]).toBe(15);
  });

  it.each(SITE_IDS)("keeps the dark foreground legible on %s", (siteId) => {
    document.documentElement.setAttribute("data-theme", "dark");
    applySiteTheme(siteId);
    const primary = written("--primary");
    const foreground = written("--primary-foreground");
    expect(
      contrast(hslToRgb(...foreground), hslToRgb(...primary)),
    ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it.each(SITE_IDS)(
    "keeps the dark foreground legible on the hover:bg-primary/90 composite for %s",
    (siteId) => {
      document.documentElement.setAttribute("data-theme", "dark");
      applySiteTheme(siteId);
      const [h, s, l] = written("--primary");
      const hover = composite(hslToRgb(h, s, l), DARK_GROUND, HOVER_ALPHA);
      expect(contrast(DARK_GROUND, hover)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    },
  );

  it("points --ring at the same value as --primary", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    applySiteTheme("plasmodb");
    expect(written("--ring")).toEqual(written("--primary"));
  });
});
