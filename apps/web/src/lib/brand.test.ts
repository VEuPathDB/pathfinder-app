import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { BRAND, BRAND_ICONS } from "./brand";

const publicDir = fileURLToPath(new URL("../../public", import.meta.url));
const kitDir = fileURLToPath(new URL("../../../../assets/brand", import.meta.url));

describe("BRAND", () => {
  it.each(Object.values(BRAND))(
    "serves %s exactly as the brand kit ships it",
    (served) => {
      const copy = readFileSync(`${publicDir}${served}`);
      const original = readFileSync(`${kitDir}/${basename(served)}`);

      expect(copy.equals(original)).toBe(true);
    },
  );

  it("points the browser at the favicons and the iOS icon under the base path", () => {
    expect(BRAND_ICONS).toEqual({
      icon: [
        { url: "/pathfinder/brand/favicon.svg", type: "image/svg+xml" },
        { url: "/pathfinder/brand/favicon.ico", sizes: "16x16 32x32 48x48" },
      ],
      apple: "/pathfinder/brand/apple-touch-icon.png",
    });
  });
});
