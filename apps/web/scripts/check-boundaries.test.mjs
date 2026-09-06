import { test } from "node:test";
import assert from "node:assert/strict";

import { checkSource } from "./check-boundaries.mjs";

const rulesOf = (source, srcRelPath) =>
  checkSource(source, srcRelPath).map((v) => v.rule);

const imports = (...specifiers) =>
  specifiers.map((s) => `import { thing } from "${s}";`).join("\n");

test("an entry path is the permission: no exception row admits the workbench", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/workbench/api/geneSets"),
      "features/conversation/slash/commandsIO.tsx",
    ),
    [],
  );
  assert.deepEqual(
    rulesOf(
      imports("@/features/workbench/api/geneSets"),
      "features/sidebar/GeneSetCount.tsx",
    ),
    [],
  );
});

test("the analysis barrel is a workbench entry path", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/workbench/analysis"),
      "features/conversation/content/parts/DataEnrichmentResults.tsx",
    ),
    [],
  );
});

test("a deep file in a feature that publishes entry paths breaks rule 6", () => {
  const violations = checkSource(
    imports("@/features/workbench/components/panels/BatchPanel"),
    "features/conversation/rail/TasksPanel.tsx",
  );
  assert.deepEqual(
    violations.map((v) => v.rule),
    [6],
  );
  assert.match(violations[0].message, /entry path/);
  assert.equal(violations[0].line, 1);
});

test("a deep import of an entry path's own subtree breaks rule 6", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/workbench/analysis/components/ResultsTable"),
      "features/conversation/content/parts/DataEnrichmentResults.tsx",
    ),
    [6],
  );
});

test("rule 6 stays silent for a target feature that declares no entry paths", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/strategy/graph/serialize"),
      "features/conversation/rail/StrategyPanel.tsx",
    ),
    [],
  );
});

test("a feature that publishes nothing is still closed by rule 1", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/eda/api/compute"),
      "features/workbench/components/panels/EdaPanel.tsx",
    ),
    [1],
  );
});

test("the workbench may not import the conversation", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/conversation/ChatView"),
      "features/workbench/components/WorkbenchMain.tsx",
    ),
    [1],
  );
});

test("the analysis subtree is the workbench's own feature, not a cross-feature edge", () => {
  assert.deepEqual(
    rulesOf(
      imports("@/features/workbench/analysis/api/stepResults"),
      "features/workbench/analysis/hooks/useDistributionData.ts",
    ),
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
    rulesOf(imports("@/features/workbench/api/geneSets"), "lib/api/geneSets.ts"),
    [4],
  );
});

test("as any in production code breaks rule 2", () => {
  assert.deepEqual(
    rulesOf("const x = value as any;", "features/workbench/utils/parse.ts"),
    [2],
  );
});

test("as any in a test file is left alone", () => {
  assert.deepEqual(
    rulesOf("const x = value as any;", "features/workbench/utils/parse.test.ts"),
    [],
  );
});
