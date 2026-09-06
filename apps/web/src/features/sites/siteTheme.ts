import {
  composite,
  contrast,
  hslToRgb,
  relativeLuminance,
  type Rgb,
} from "@/lib/color/contrast";
import { hslTriple } from "@/lib/color/hsl";

/** Each site's primary brand hex color, from VEuPathDB's official CSS. */
const SITE_COLORS: Record<string, string> = {
  veupathdb: "#2e537b",
  plasmodb: "#634697",
  toxodb: "#569551",
  cryptodb: "#274f94",
  giardiadb: "#3b4da0",
  amoebadb: "#5a9e83",
  microsporidiadb: "#3a7ca5",
  piroplasmadb: "#3a8c9f",
  tritrypdb: "#c06530",
  fungidb: "#0e8298",
  hostdb: "#0c7eb5",
  vectorbase: "#b74630",
  orthomcl: "#316e9f",
  schistodb: "#346079",
  trichdb: "#6e8446",
};

/** Every site the brand map paints; the theme suite iterates it. */
export const SITE_IDS = Object.keys(SITE_COLORS);

const DEFAULT_COLOR = "#2596b3";

function hexToHsl(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;

  if (max === min) return [0, 0, Math.round(l * 100)];

  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  else if (max === g) h = ((b - r) / d + 2) / 6;
  else h = ((r - g) / d + 4) / 6;

  return [Math.round(h * 360), Math.round(s * 100), Math.round(l * 100)];
}

/**
 * Returns the HSL CSS value string for a given site's brand color.
 *
 * :param siteId: The VEuPathDB site identifier.
 * :returns: HSL values as "H S% L%" (without the hsl() wrapper, compatible
 *     with the CSS variable format used by shadcn/tailwind).
 */
function getSiteHslParts(siteId: string): [number, number, number] {
  const hex = SITE_COLORS[siteId] ?? DEFAULT_COLOR;
  return hexToHsl(hex);
}

/** The tinted surfaces and the button text a brand color is painted against. */
interface Ground {
  readonly foreground: readonly [number, number, number];
  readonly secondary: readonly [number, number];
  readonly accent: readonly [number, number];
  readonly muted: readonly [number, number];
}

/** Saturation and lightness for the tinted surfaces; the hue is the brand's. */
const LIGHT_GROUND: Ground = {
  foreground: [0, 0, 100],
  secondary: [25, 95],
  accent: [25, 93],
  muted: [20, 96],
};

const DARK_GROUND: Ground = {
  foreground: [215, 28, 9],
  secondary: [22, 16],
  accent: [22, 18],
  muted: [20, 15],
};

/** WCAG AA for normal text, with a small margin. */
const AA_WITH_MARGIN = 4.6;

/** Above this luminance a foreground reads as light, so the fill must darken. */
const LIGHT_FOREGROUND_LUMINANCE = 0.1791;

/** The alpha `hover:bg-primary/90` paints the fill at. */
const HOVER_ALPHA = 0.9;

/**
 * Moves a brand color's lightness until its foreground text is legible on the
 * weakest fill the button paints: the hover state, where the fill fades toward
 * the ground the label is cut from. The resting fill then clears by more. Hue
 * and saturation are untouched, so the brand survives.
 */
function clampLightnessForForeground(
  h: number,
  s: number,
  l: number,
  foreground: Rgb,
): number {
  const step = relativeLuminance(foreground) > LIGHT_FOREGROUND_LUMINANCE ? -1 : 1;
  let out = l;
  while (
    out > 0 &&
    out < 100 &&
    contrast(foreground, composite(hslToRgb(h, s, out), foreground, HOVER_ALPHA)) <
      AA_WITH_MARGIN
  ) {
    out += step;
  }
  return out;
}

function currentGround(): Ground {
  return document.documentElement.getAttribute("data-theme") === "dark"
    ? DARK_GROUND
    : LIGHT_GROUND;
}

/**
 * Applies the site's brand palette to CSS custom properties on the document
 * root, against the ground the document is on. Derives a coherent
 * secondary/accent from the primary hue so every theme token tracks the site
 * brand instead of falling back to the default neutral.
 */
export function applySiteTheme(siteId: string): void {
  const [h, s, l] = getSiteHslParts(siteId);
  const ground = currentGround();
  const foreground = hslToRgb(...ground.foreground);
  const primary = hslTriple(h, s, clampLightnessForForeground(h, s, l, foreground));
  const root = document.documentElement;
  root.style.setProperty("--primary", primary);
  root.style.setProperty("--primary-foreground", hslTriple(...ground.foreground));
  root.style.setProperty("--ring", primary);
  root.style.setProperty("--secondary", hslTriple(h, ...ground.secondary));
  root.style.setProperty("--accent", hslTriple(h, ...ground.accent));
  root.style.setProperty("--muted", hslTriple(h, ...ground.muted));
}
