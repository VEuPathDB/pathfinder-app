import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { CONFIG, FIRST, manualHooks, phases, pushedFiles } from "./pre-push.mjs";

const SAMPLE = `default_stages: [pre-commit]
repos:
  - repo: local
    hooks:
      - id: ruff-check
        files: ^apps/api/
      - id: mypy-api
        entry: mypy src
        stages: [manual]
      - id: shared-ts-openapi
        entry: yarn check:generated
        stages: [manual]
      - id: pre-push-gates
        entry: node scripts/pre-push.mjs
        stages: [pre-push]
`;

test("only the manual-stage hooks are pre-push gates", () => {
  assert.deepEqual(manualHooks(SAMPLE), ["mypy-api", "shared-ts-openapi"]);
});

test("the type generation runs alone before every other gate", () => {
  assert.deepEqual(phases(["mypy-api", "shared-ts-openapi", "vitest-web"]), [
    ["shared-ts-openapi"],
    ["mypy-api", "vitest-web"],
  ]);
});

test("the committed config holds every first-phase hook as a manual gate", () => {
  const hooks = manualHooks(readFileSync(new URL(`../${CONFIG}`, import.meta.url), "utf8"));
  assert.deepEqual(
    FIRST.filter((hook) => hooks.includes(hook)),
    FIRST,
  );
  assert.ok(hooks.length >= 20, `found ${hooks.length} manual hooks`);
});

test("a push with a range reads the files the range changes", () => {
  const calls = [];
  const git = (args) => {
    calls.push(args);
    return "apps/api/a.py\napps/web/b.ts\n";
  };
  const files = pushedFiles({ PRE_COMMIT_FROM_REF: "abc", PRE_COMMIT_TO_REF: "def" }, git);
  assert.deepEqual(files, ["apps/api/a.py", "apps/web/b.ts"]);
  assert.deepEqual(calls, [
    ["diff", "--name-only", "--no-ext-diff", "--diff-filter=ACMRTUXB", "abc...def"],
  ]);
});

test("a push with no range reads every tracked file", () => {
  const calls = [];
  const git = (args) => {
    calls.push(args);
    return "README.md\n";
  };
  assert.deepEqual(pushedFiles({}, git), ["README.md"]);
  assert.deepEqual(calls, [["ls-files"]]);
});
