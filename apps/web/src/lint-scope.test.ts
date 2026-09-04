import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { beforeAll, describe, expect, it } from "vitest";

const WEB_ROOT = fileURLToPath(new URL("..", import.meta.url));

const eslint = new ESLint({ cwd: WEB_ROOT });

const GENERATED_TREES = [
  ".stryker-tmp/sandbox-abcdef/src/state/strategy/reducer.ts",
  ".stryker-tmp/incremental.json",
  ".next/types/routes.ts",
  "coverage/lcov-report/index.html",
  "playwright-report/index.html",
  "test-results/results.json",
  "reports/mutation/index.html",
];

const LINTED_TREES = [
  "src/lib/utils/cn.ts",
  "e2e/feature/durable-verification.spec.ts",
  "scripts/check-boundaries.mjs",
];

const ignored = new Map<string, boolean>();

describe("the whole-directory lint program", () => {
  // The first isPathIgnored call resolves the flat config, which loads
  // typescript-eslint. The hook budget covers that one load, not an assertion.
  beforeAll(async () => {
    for (const path of [...GENERATED_TREES, ...LINTED_TREES]) {
      ignored.set(path, await eslint.isPathIgnored(path));
    }
  }, 120_000);

  it.each(GENERATED_TREES)("ignores %s", (path) => {
    expect(ignored.get(path)).toBe(true);
  });

  it.each(LINTED_TREES)("lints %s", (path) => {
    expect(ignored.get(path)).toBe(false);
  });
});
