import { test } from "node:test";
import assert from "node:assert/strict";

import {
  findingsIn,
  parseLexicon,
  pythonStrings,
  toolNamesIn,
  webRawValues,
  webStrings,
} from "./check-vocabulary.mjs";

const LEXICON = `---
type: Convention
title: t
description: d
---

# The lexicon

| Concept | Name | Banned synonyms | Scope | Reason |
|---|---|---|---|---|
| A thread's saved findings | notes | scratchpad, \`notebook\` | all | one word |
| A WDK strategy | strategy | search tree | researcher | WDK's word |

# Exemptions

| Synonym | Path | Reason |
|---|---|---|
| notebook | apps/web/src/x.tsx | the icon's own name |

# Raw values

| Identifier | Name | Reason |
|---|---|---|
| \`siteId\` | \`siteShortName(siteId)\` | a researcher reads the site's name |
`;

const texts = (found) => found.map((one) => one.text);

test("the lexicon yields one row per concept and one entry per exemption", () => {
  const { rows, exemptions } = parseLexicon(LEXICON);

  assert.deepEqual(rows, [
    {
      concept: "A thread's saved findings",
      name: "notes",
      banned: ["scratchpad", "notebook"],
      scope: "all",
    },
    {
      concept: "A WDK strategy",
      name: "strategy",
      banned: ["search tree"],
      scope: "researcher",
    },
  ]);
  assert.deepEqual(exemptions, [
    { synonym: "notebook", path: "apps/web/src/x.tsx", reason: "the icon's own name" },
  ]);
});

test("a lexicon with no banned column is refused", () => {
  assert.throws(
    () => parseLexicon("# The lexicon\n\n| a | b |\n|---|---|\n"),
    /lexicon table/,
  );
});

test("a scope other than all or researcher is refused", () => {
  const bad = LEXICON.replace("| all |", "| everyone |");

  assert.throws(() => parseLexicon(bad), /scope "everyone"/);
});

test("JSX text and a single-word label are copy", () => {
  const source = `export const A = () => (
  <Shell title="Scratchpad">
    <p>No notes yet.</p>
  </Shell>
);`;

  assert.deepEqual(texts(webStrings(source, "a.tsx")), ["Scratchpad", "No notes yet."]);
});

test("a ternary inside a copy attribute is copy, and its line is its own", () => {
  const source = `const b = <button\n  aria-label={pinned ? "Unpin" : "Pin"}\n/>;`;

  assert.deepEqual(webStrings(source, "b.tsx"), [
    { line: 2, text: "Unpin", audience: "researcher" },
    { line: 2, text: "Pin", audience: "researcher" },
  ]);
});

test("a label property and a toast argument are copy", () => {
  const source = `const TABS = [{ id: "scratchpad", label: "Scratchpad" }];
toast.error("Scratchpad failed");
toast("Saved");`;

  assert.deepEqual(texts(webStrings(source, "c.ts")), [
    "Scratchpad",
    "Scratchpad failed",
    "Saved",
  ]);
});

test("a table column's head is copy", () => {
  const source = `const COLUMNS = [{ head: "Criterion" }, { head: "Genes", numeric: true }];`;

  assert.deepEqual(texts(webStrings(source, "e.tsx")), ["Criterion", "Genes"]);
});

test("a prose literal anywhere is copy, and a one-word literal outside a copy slot is not", () => {
  const source = `const EMPTY = "Nothing in the scratchpad";
const KEY = "scratchpad";
const t = \`Open the \${name} scratchpad\`;`;

  assert.deepEqual(texts(webStrings(source, "d.ts")), [
    "Nothing in the scratchpad",
    "Open the ",
    " scratchpad",
  ]);
});

test("class names, test ids, imports and console lines are not copy", () => {
  const source = `import { X } from "./scratchpad panel";
const e = <div className="scratchpad text-xs" data-testid="scratchpad empty" />;
const f = cn("scratchpad base", other);
console.warn("scratchpad failed to load");`;

  assert.deepEqual(webStrings(source, "e.tsx"), []);
});

test("a tool's docstring is model-facing and a helper's is not", () => {
  const source = `"""Module about the scratchpad."""


def note(title: str) -> str:
    """Save a scratchpad note."""
    return title


async def _helper() -> None:
    """Read the scratchpad."""
`;

  assert.deepEqual(pythonStrings(source, { toolNames: new Set(["note"]) }), [
    { line: 5, text: "Save a scratchpad note.", audience: "model" },
  ]);
});

test("a prose value is model-facing, a key and a log line are not", () => {
  const source = `GUIDE = (
    "Call note(...) to save "  # a comment with scratchpad
    'findings to the scratchpad.'
)
KIND = "scratchpad"
logger.warning("scratchpad compaction failed", exc_info=True)
`;

  assert.deepEqual(texts(pythonStrings(source, { toolNames: new Set() })), [
    "Call note(...) to save ",
    "findings to the scratchpad.",
  ]);
});

test("an f-string keeps its literal parts, nested quotes included", () => {
  const source = `x = f"{total} notes in the {"big" if a else 'small'} scratchpad"\n`;

  assert.deepEqual(texts(pythonStrings(source, { toolNames: new Set() })), [
    "{} notes in the {} scratchpad",
  ]);
});

test("a triple-quoted constant is read whole, with its first line", () => {
  const source = `RULE = """\\\nKeep the scratchpad short.
Pin what matters."""\n`;

  assert.deepEqual(pythonStrings(source, { toolNames: new Set() }), [
    {
      line: 1,
      text: "\\\nKeep the scratchpad short.\nPin what matters.",
      audience: "model",
    },
  ]);
});

test("the detail scope reads only detail= and title= arguments", () => {
  const source = `raise AppError(
    code="scratchpad_missing",
    title="Scratchpad missing",
    detail="The scratchpad " "is gone.",
)
MESSAGE = "The scratchpad is elsewhere."
`;

  const found = pythonStrings(source, { scope: "detail" });

  assert.deepEqual(texts(found), ["Scratchpad missing", "The scratchpad ", "is gone."]);
  assert.deepEqual(new Set(found.map((one) => one.audience)), new Set(["researcher"]));
});

test("a summary a trace row shows is read by both the model and the researcher", () => {
  const source = `return with_summary(
    payload,
    f"{n} notes in the scratchpad",
    extra=[cleared_chunk(reason="the user cleared the strategy")],
)
RETRY = "Call list_notes before you pin one."
`;

  assert.deepEqual(
    pythonStrings(source, { toolNames: new Set() }).map((one) => one.audience),
    ["both", "model", "model"],
  );
});

test("the tool names are read from Tool(...) and a FunctionToolset list", () => {
  const source = `base = FunctionToolset(
    max_retries=3,
    tools=[get_record_types, search_for_searches],
)
extra = [Tool(delete_step, requires_approval=True), Tool(think)]
`;

  assert.deepEqual([...toolNamesIn(source)].sort(), [
    "delete_step",
    "get_record_types",
    "search_for_searches",
    "think",
  ]);
});

const R = "researcher";

test("a banned word is found whole, in any case, singular or plural", () => {
  const { rows } = parseLexicon(LEXICON);
  const strings = [
    { line: 1, text: "Open the Scratchpad", audience: R },
    { line: 2, text: "two scratchpads", audience: R },
    { line: 3, text: "data-scratchpad-updated and list_scratchpad", audience: R },
    { line: 4, text: "the search\ntree view", audience: R },
  ];

  assert.deepEqual(findingsIn(strings, rows, "a.tsx", []), [
    { path: "a.tsx", line: 1, synonym: "scratchpad", name: "notes" },
    { path: "a.tsx", line: 2, synonym: "scratchpad", name: "notes" },
    { path: "a.tsx", line: 4, synonym: "search tree", name: "strategy" },
  ]);
});

test("a hit on a later line of a multi-line string reports that line", () => {
  const { rows } = parseLexicon(LEXICON);

  assert.deepEqual(
    findingsIn(
      [{ line: 3, text: "one\ntwo\nthe scratchpad", audience: "model" }],
      rows,
      "p.py",
      [],
    ),
    [{ path: "p.py", line: 5, synonym: "scratchpad", name: "notes" }],
  );
});

test("an exemption excuses its synonym in its file only", () => {
  const { rows, exemptions } = parseLexicon(LEXICON);
  const strings = [{ line: 1, text: "the notebook and the scratchpad", audience: R }];

  assert.deepEqual(
    findingsIn(strings, rows, "apps/web/src/x.tsx", exemptions).map((f) => f.synonym),
    ["scratchpad"],
  );
  assert.deepEqual(
    findingsIn(strings, rows, "apps/web/src/y.tsx", exemptions).map((f) => f.synonym),
    ["notebook", "scratchpad"],
  );
});

test("a researcher-scoped row does not read what only the model reads", () => {
  const { rows } = parseLexicon(LEXICON);
  const strings = [
    { line: 1, text: "the search tree", audience: "model" },
    { line: 2, text: "the search tree", audience: "both" },
    { line: 3, text: "the search tree", audience: "researcher" },
  ];

  assert.deepEqual(
    findingsIn(strings, rows, "a.py", []).map((one) => one.line),
    [2, 3],
  );
});

test("the lexicon yields one entry per raw value", () => {
  const { rawValues } = parseLexicon(LEXICON);

  assert.deepEqual(rawValues, [
    {
      identifier: "siteId",
      name: "siteShortName(siteId)",
      reason: "a researcher reads the site's name",
    },
  ]);
});

test("a raw value interpolated into copy is found, by name or as a property", () => {
  const source = `const a = \`No study on \${siteId} matches \${query}.\`;
const b = <Card caption={\`\${n} genes on \${data.siteId}\`} />;
const c = <p>Open {siteId}</p>;
const d = <a aria-label={analysis.siteId} />;`;

  assert.deepEqual(webRawValues(source, "a.tsx", new Set(["siteId"])), [
    { line: 1, identifier: "siteId" },
    { line: 2, identifier: "siteId" },
    { line: 3, identifier: "siteId" },
    { line: 4, identifier: "siteId" },
  ]);
});

test("a raw value in a path, a key, a test id or a helper call is not copy", () => {
  const source = `const u = \`/api/v1/sites/\${siteId}/searches\`;
const e = <Row key={siteId} data-testid={\`site-\${siteId}\`} />;
const f = <p>{\`No study on \${siteShortName(siteId)}.\`}</p>;
const g = { siteId };
const h = siteId.length;`;

  assert.deepEqual(webRawValues(source, "b.tsx", new Set(["siteId"])), []);
});
