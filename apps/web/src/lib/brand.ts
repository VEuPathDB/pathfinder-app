import type { Metadata } from "next";

import { withBasePath } from "@/lib/basePath";

export const BRAND = {
  markLight: "/brand/pathfinder-mark-light.svg",
  markDark: "/brand/pathfinder-mark-dark.svg",
  favicon: "/brand/favicon.svg",
  faviconIco: "/brand/favicon.ico",
  appleTouchIcon: "/brand/apple-touch-icon.png",
} as const;

export const MARK_LEFT_INSET = 26 / 240;

export const BRAND_ICONS: Metadata["icons"] = {
  icon: [
    { url: withBasePath(BRAND.favicon), type: "image/svg+xml" },
    { url: withBasePath(BRAND.faviconIco), sizes: "16x16 32x32 48x48" },
  ],
  apple: withBasePath(BRAND.appleTouchIcon),
};
