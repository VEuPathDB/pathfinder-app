import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/** Directories whose components draw inside a message, relative to this file. */
const THREAD_CONTENT = ["./content", "./thread"];

const SYMMETRIC_MARGIN = /\bmy-[\d.]+\b/g;
const DIVIDER = /\bborder-[tb]\b/g;

function sourcesUnder(dir: string): { path: string; text: string }[] {
  const root = fileURLToPath(new URL(dir, import.meta.url));
  const found: { path: string; text: string }[] = [];
  for (const entry of readdirSync(root, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".tsx")) continue;
    if (entry.name.includes(".test.")) continue;
    const path = join(entry.parentPath, entry.name);
    found.push({ path, text: readFileSync(path, "utf8") });
  }
  return found;
}

const SOURCES = THREAD_CONTENT.flatMap(sourcesUnder);

/** A table rules its own head and body; the guard is about rules drawn
 * between one block of a message and the next. */
const TABLE = "ExhibitTable.tsx";

function hits(pattern: RegExp, exempt: string[] = []): string[] {
  return SOURCES.filter(
    ({ path }) => !exempt.some((name) => path.endsWith(name)),
  ).flatMap(({ path, text }) =>
    [...text.matchAll(pattern)].map((match) => `${path}: ${match[0]}`),
  );
}

describe("the thread's vertical rhythm", () => {
  it("reads more than a handful of components", () => {
    expect(SOURCES.length).toBeGreaterThan(20);
  });

  it("leaves every block's outer spacing to its container", () => {
    expect(hits(SYMMETRIC_MARGIN)).toEqual([]);
  });

  it("draws no rule between one block and the next", () => {
    expect(hits(DIVIDER, [TABLE])).toEqual([]);
  });
});
