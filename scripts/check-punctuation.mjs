/**
 * No source file carries smart punctuation.
 *
 * `check-knowledge.mjs` holds every `.md` in the knowledge bundle to plain
 * ASCII punctuation. Source drifted because nothing held it to the same rule:
 * an em-dash in a string a researcher reads is the same defect as one in a
 * document. Only punctuation is flagged, never other non-ASCII, because an
 * accented proper noun is not a mistake.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TREES = ["apps/api/src", "apps/web/src", "packages/shared-ts/src", "scripts"];
const EXTENSIONS = [".py", ".ts", ".tsx", ".mjs", ".js"];
// Generated files are written by a tool this rule cannot reach, and a vendored
// tree is somebody else's source.
const SKIPPED = new Set([
  "node_modules",
  "__pycache__",
  ".next",
  "generated",
  "dist",
  "coverage",
]);
// Code points, not literal glyphs: the file must obey the rule it enforces,
// and one curly quote against the other is not a difference anyone reviews by
// eye.
const PUNCTUATION = new Map([
  [String.fromCharCode(0x2013), "en-dash"],
  [String.fromCharCode(0x2014), "em-dash"],
  [String.fromCharCode(0x2018), "curly quote"],
  [String.fromCharCode(0x2019), "curly quote"],
  [String.fromCharCode(0x201c), "curly quote"],
  [String.fromCharCode(0x201d), "curly quote"],
  [String.fromCharCode(0x2026), "unicode ellipsis"],
  [String.fromCharCode(0x2192), "arrow"],
]);
const PUNCTUATION_RE = new RegExp(`[${[...PUNCTUATION.keys()].join("")}]`, "g");

// An escape produces the same glyph a reader sees, so it breaks the same rule.
const ESCAPE_RE = /\\u(2013|2014|2018|2019|201[cCdD]|2026|2192)/g;

export function offencesIn(text, path) {
  return text.split("\n").flatMap((line, index) => {
    const glyphs = [...line.matchAll(PUNCTUATION_RE)].map((match) =>
      PUNCTUATION.get(match[0]),
    );
    const escaped = [...line.matchAll(ESCAPE_RE)].map((match) =>
      PUNCTUATION.get(String.fromCharCode(parseInt(match[1], 16))),
    );
    return [...glyphs, ...escaped].map((glyph) => ({
      path,
      line: index + 1,
      glyph,
    }));
  });
}

function sourceFilesUnder(dir) {
  return readdirSync(dir).flatMap((name) => {
    if (SKIPPED.has(name)) return [];
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFilesUnder(full);
    return EXTENSIONS.some((ext) => name.endsWith(ext)) ? [full] : [];
  });
}

function main() {
  const offences = TREES.flatMap((tree) => {
    const dir = join(ROOT, tree);
    return sourceFilesUnder(dir).flatMap((file) =>
      offencesIn(readFileSync(file, "utf8"), relative(ROOT, file)),
    );
  });
  if (offences.length > 0) {
    for (const { path, line, glyph } of offences.slice(0, 40)) {
      console.error(`${path}:${line}: ${glyph}`);
    }
    const hidden = offences.length - Math.min(offences.length, 40);
    if (hidden > 0) console.error(`... and ${hidden} more`);
    console.error(
      `\ncheck-punctuation: ${offences.length} smart punctuation mark(s) in source.`,
    );
    console.error("Use plain ASCII: - for a dash, ' and \" for quotes, ... for an ellipsis.");
    process.exit(1);
  }
  console.log("check-punctuation: source is plain ASCII punctuation.");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
