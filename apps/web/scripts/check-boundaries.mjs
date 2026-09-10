/**
 * Boundary enforcement script for the web app.
 *
 * Rules:
 *   1. No cross-feature imports - files in src/features/X/ must NOT import
 *      from src/features/Y/ (X != Y), unless CROSS_FEATURE_EXCEPTIONS says so.
 *
 *   2. No `as any` in production code - files in src/ (excluding .test. files
 *      and __fixtures__/) must not contain `as any`.
 *
 *   3. Features may only import from: @/lib/, @/state/, @pathfinder/shared,
 *      third-party packages, and their own feature directory.
 *
 *   4. src/lib/ is pure: it may not import @/features/, @/state/ or @/app/.
 *
 *   5. src/state/ owns global stores: it may not import @/features/ or @/app/.
 *
 *   6. A feature that publishes entry paths (FEATURE_ENTRYPOINTS) is reachable
 *      through them and nothing else. Naming one is the permission, so rule 1
 *      needs no exception row for such a target; naming a file inside it fails.
 *
 * Exit code 1 on violations, 0 if clean.
 */

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd());
const SRC = path.join(ROOT, "src");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Recursively collect all files under `dir`. */
function walk(dir) {
  const out = [];
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name === "node_modules" || ent.name.startsWith(".")) continue;
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      out.push(...walk(full));
    } else {
      out.push(full);
    }
  }
  return out;
}

function isTsLike(filePath) {
  return /\.(ts|tsx|mts|cts)$/.test(filePath);
}

function isTestOrFixture(srcRelPath) {
  return srcRelPath.includes(".test.") || srcRelPath.includes("__fixtures__/");
}

/**
 * Given a path relative to src/, return the feature name for a file under
 * features/<name>/. Returns null outside a feature directory.
 */
function featureOf(srcRelPath) {
  const parts = srcRelPath.split("/");
  if (parts[0] === "features" && parts.length >= 2) {
    return parts[1];
  }
  return null;
}

const AS_ANY_RE = /\bas\s+any\b/g;

/**
 * Extract all import/re-export specifiers with their line numbers from source.
 */
function extractImports(source) {
  const results = [];
  const lines = source.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Match: import ... from "specifier"  or  export ... from "specifier"
    const m =
      line.match(/from\s+["']([^"']+)["']/) ||
      line.match(/import\s*\(\s*["']([^"']+)["']\s*\)/);
    if (m) {
      results.push({ specifier: m[1], lineNum: i + 1 });
    }
  }
  return results;
}

/** Allowed import prefixes for feature files (rule 3). */
const ALLOWED_PREFIXES = [
  "@/lib/",
  "@/state/",
  "@pathfinder/shared",
  "@veupathdb/assistant-client",
  // Vendored shadcn / AI Elements primitives — installed via shadcn CLI,
  // treated as third-party. Lives under src/components/{ui,ai-elements}/.
  "@/components/ui/",
  "@/components/ai-elements/",
];

/**
 * Check whether an import specifier is allowed from within a feature directory.
 *
 * Allowed:
 *   - Relative imports (always resolve within the same feature — we check
 *     cross-feature separately for @/features/ imports)
 *   - @/lib/...
 *   - @/state/...
 *   - @pathfinder/shared (or @pathfinder/shared/...)
 *   - Own feature: @/features/<self>/...
 *   - Third-party packages (no @ prefix other than scoped npm, and not @/)
 */
function isAllowedFeatureImport(specifier, selfFeature) {
  // Relative imports — fine (within own feature tree)
  if (specifier.startsWith(".")) return true;

  // Own feature
  if (
    specifier.startsWith(`@/features/${selfFeature}/`) ||
    specifier === `@/features/${selfFeature}`
  ) {
    return true;
  }

  // Allowed shared paths
  for (const prefix of ALLOWED_PREFIXES) {
    if (specifier === prefix || specifier.startsWith(prefix)) return true;
  }

  // Another feature — NOT allowed (handled by rule 1 as well, but rule 3
  // catches any stray pattern)
  if (specifier.startsWith("@/features/")) return false;

  // Any other @/ import that isn't lib/state/features (e.g. @/app/) — disallow
  if (specifier.startsWith("@/")) return false;

  // Third-party packages (react, zustand, @radix-ui/..., etc.)
  return true;
}

// `conversation` is the app shell: it owns the rail, the thread, the composer
// and the slash commands, so it reaches into the surfaces it hosts. Rule 1 does
// not constrain it, and this map says so. An exception admits the whole tree of
// the target, which is why a feature with an API belongs in FEATURE_ENTRYPOINTS
// instead.
const CROSS_FEATURE_EXCEPTIONS = new Map([
  ["conversation", new Set(["settings", "strategy", "saved"])],
  // sidebar awaits pending strategy pushes before it switches conversations.
  ["sidebar", new Set(["strategy"])],
]);

// The paths a feature publishes. Naming one of them is the permission, and the
// only permission: any feature may import an entry path, and no feature may
// import anything else of a feature that publishes. A feature absent from this
// map is closed by rule 1 unless an exception row above admits it.
const FEATURE_ENTRYPOINTS = new Map([
  ["workbench", new Set(["api/geneSets", "analysis"])],
]);

/** Layers that may not import a higher layer, keyed by src/ subdirectory. */
const LAYER_BANS = new Map([
  ["lib", { rule: 4, banned: ["@/features/", "@/state/", "@/app/"] }],
  ["state", { rule: 5, banned: ["@/features/", "@/app/"] }],
]);

function layerOf(srcRelPath) {
  return srcRelPath.split("/")[0];
}

/**
 * Check one source text. `srcRelPath` is the file's path relative to src/.
 * Returns the violations it holds, each as { rule, line, message }.
 * Exported so the checker has tests.
 */
export function checkSource(source, srcRelPath) {
  const violations = [];
  const add = (rule, line, message) => violations.push({ rule, line, message });

  const selfFeature = featureOf(srcRelPath);
  const isProduction = !isTestOrFixture(srcRelPath);
  const imports = extractImports(source);

  // ------ Rules 1, 3 & 6: cross-feature imports + allowed imports ------
  if (selfFeature) {
    const allowedCrossTargets = CROSS_FEATURE_EXCEPTIONS.get(selfFeature) ?? new Set();

    for (const { specifier, lineNum } of imports) {
      // Rule 1: cross-feature via @/features/
      const crossMatch = specifier.match(/^@\/features\/([^/]+)/);
      if (crossMatch) {
        const targetFeature = crossMatch[1];
        if (targetFeature === selfFeature) continue;
        const entryPaths = FEATURE_ENTRYPOINTS.get(targetFeature);
        if (entryPaths) {
          // Rule 6: a feature that publishes is reachable through its entry
          // paths and nothing else.
          const entry = specifier.slice(`@/features/${targetFeature}/`.length);
          if (!entryPaths.has(entry)) {
            add(
              6,
              lineNum,
              `Not an entry path: features/${selfFeature} imports "${specifier}"; features/${targetFeature} publishes ${[
                ...entryPaths,
              ]
                .map((p) => `@/features/${targetFeature}/${p}`)
                .join(", ")}`,
            );
          }
          continue;
        }
        if (!allowedCrossTargets.has(targetFeature)) {
          add(
            1,
            lineNum,
            `Cross-feature import: features/${selfFeature} imports from features/${targetFeature} ("${specifier}")`,
          );
        }
        continue;
      }

      // Rule 3: only allowed import sources (production code only)
      if (isProduction && !isAllowedFeatureImport(specifier, selfFeature)) {
        add(
          3,
          lineNum,
          `Disallowed import source: "${specifier}" (features may only import from @/lib/, @/state/, @pathfinder/shared, own feature, or third-party)`,
        );
      }
    }
  }

  // ------ Rules 4 & 5: layer purity ------
  const ban = LAYER_BANS.get(layerOf(srcRelPath));
  if (ban) {
    for (const { specifier, lineNum } of imports) {
      const hit = ban.banned.find((p) => specifier.startsWith(p));
      if (hit) {
        add(
          ban.rule,
          lineNum,
          `src/${layerOf(srcRelPath)}/ may not import ${hit} ("${specifier}")`,
        );
      }
    }
  }

  // ------ Rule 2: no `as any` in production code ------
  if (isProduction) {
    const lines = source.split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (AS_ANY_RE.test(lines[i])) {
        add(2, i + 1, `\`as any\` in production code`);
      }
      // Reset lastIndex since we reuse the regex
      AS_ANY_RE.lastIndex = 0;
    }
  }

  return violations;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const RULE_NAMES = {
  1: "No cross-feature imports",
  2: 'No "as any" in production code',
  3: "Features: allowed import sources only",
  4: "lib/ is pure (no features, state or app)",
  5: "state/ may not import features or app",
  6: "A cross-feature import names an entry path",
};

function main() {
  const violations = [];
  for (const filePath of walk(SRC).filter(isTsLike)) {
    const srcRel = path.relative(SRC, filePath).split(path.sep).join("/");
    const source = fs.readFileSync(filePath, "utf8");
    for (const v of checkSource(source, srcRel)) {
      violations.push({ ...v, file: path.relative(ROOT, filePath) });
    }
  }

  if (violations.length === 0) {
    console.log("check-boundaries: all clear (0 violations)");
    return 0;
  }

  console.error(`\nBoundary violations found: ${violations.length}\n`);

  const byRule = new Map();
  for (const v of violations) {
    if (!byRule.has(v.rule)) byRule.set(v.rule, []);
    byRule.get(v.rule).push(v);
  }

  for (const [rule, items] of [...byRule.entries()].sort((a, b) => a[0] - b[0])) {
    console.error(
      `--- Rule ${rule}: ${RULE_NAMES[rule]} (${items.length} violation${items.length > 1 ? "s" : ""}) ---`,
    );
    for (const v of items) {
      console.error(`  ${v.file}:${v.line}  ${v.message}`);
    }
    console.error();
  }

  console.error(`Total: ${violations.length} violation(s)`);
  return 1;
}

const invokedDirectly = process.argv[1]?.endsWith("check-boundaries.mjs");
if (invokedDirectly) process.exit(main());
