import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const RAIL = fileURLToPath(new URL(".", import.meta.url));
const COMPACT = fileURLToPath(
  new URL("../../strategy/graph/components/", import.meta.url),
);
const MONO_ALLOWED = new Set(["SpotCheck.tsx"]);

function sources(): { name: string; text: string }[] {
  const rail = readdirSync(RAIL, { recursive: true, encoding: "utf8" })
    .filter((path) => path.endsWith(".tsx") && !path.endsWith(".test.tsx"))
    .map((path) => join(RAIL, path));
  const compact = readdirSync(COMPACT)
    .filter(
      (name) =>
        name.startsWith("Compact") &&
        name.endsWith(".tsx") &&
        !name.endsWith(".test.tsx"),
    )
    .map((name) => join(COMPACT, name));
  return [...rail, ...compact].map((path) => ({
    name: path.split("/").at(-1) ?? path,
    text: readFileSync(path, "utf8"),
  }));
}

describe("the rail's type rules", () => {
  it("sets no text under 12px", () => {
    expect(
      sources()
        .filter((s) => /text-\[0\.[56]/.test(s.text))
        .map((s) => s.name),
    ).toEqual([]);
  });

  it("sets no uppercase labels", () => {
    expect(
      sources()
        .filter((s) => /\buppercase\b/.test(s.text))
        .map((s) => s.name),
    ).toEqual([]);
  });

  it("keeps monospace for record IDs only", () => {
    expect(
      sources()
        .filter((s) => s.text.includes("font-mono") && !MONO_ALLOWED.has(s.name))
        .map((s) => s.name),
    ).toEqual([]);
  });
});
