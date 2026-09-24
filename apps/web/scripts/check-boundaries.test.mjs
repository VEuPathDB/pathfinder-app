import { test } from "node:test";
import assert from "node:assert/strict";

import { checkSource } from "./check-boundaries.mjs";

const rulesOf = (source, srcRelPath) =>
  checkSource(source, srcRelPath).map((v) => v.rule);

const imports = (...specifiers) =>
  specifiers.map((s) => `import { thing } from "${s}";`).join("\n");

test("an exception row admits the whole tree of the target feature", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/strategy/graph/serialize"),
      "features/conversation/rail/StrategyPanel.tsx",
    ),
    [],
  );
});

test("a cross-feature import with no exception row breaks rule 1", () => {
  const violations = checkSource(
    imports("@/features/eda/api/compute"),
    "features/conversation/rail/TasksPanel.tsx",
  );
  assert.deepEqual(
    violations.map((v) => v.rule),
    [1],
  );
  assert.match(violations[0].message, /Cross-feature import/);
  assert.equal(violations[0].line, 1);
});

test("an exception row admits one direction only", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/conversation/ChatView"),
      "features/strategy/graph/StrategyGraph.tsx",
    ),
    [1],
  );
});

test("a feature's own subtree is not a cross-feature edge", () => {
  assert.deepEqual(
    rulesOf(imports("@/features/eda/api/compute"), "features/eda/hooks/useCompute.ts"),
    [],
  );
});

test("an unlisted cross-feature import still breaks rule 1", () => {
  assert.deepEqual(
    rulesOf(imports("@/features/eda/EdaPanel"), "features/saved/SavedList.tsx"),
    [1],
  );
});

test("lib may not import a feature", () => {
  assert.deepEqual(
    rulesOf(imports("@/features/conversation/api/chat"), "lib/api/geneSets.ts"),
    [4],
  );
});

test("as any in production code breaks rule 2", () => {
  assert.deepEqual(
    rulesOf("const x = value as any;", "features/eda/utils/parse.ts"),
    [2],
  );
});

test("as any in a test file is left alone", () => {
  assert.deepEqual(
    rulesOf("const x = value as any;", "features/eda/utils/parse.test.ts"),
    [],
  );
});
