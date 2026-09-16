import { test } from "node:test";
import assert from "node:assert/strict";

import { offencesIn } from "./check-punctuation.mjs";

const EM_DASH = String.fromCharCode(0x2014);
const CURLY = String.fromCharCode(0x2019);
const ELLIPSIS = String.fromCharCode(0x2026);
const ARROW = String.fromCharCode(0x2192);

test("a line of plain ASCII punctuation is accepted", () => {
  assert.deepEqual(offencesIn("a - b, 'c', \"d\", e... f -> g", "x.ts"), []);
});

test("an em-dash is named with its line", () => {
  const found = offencesIn(`one\ntwo ${EM_DASH} three`, "x.py");

  assert.deepEqual(found, [{ path: "x.py", line: 2, glyph: "em-dash" }]);
});

test("every kind the rule covers is reported", () => {
  const found = offencesIn(`${CURLY}${ELLIPSIS}${ARROW}`, "x.tsx");

  assert.deepEqual(
    found.map((one) => one.glyph),
    ["curly quote", "unicode ellipsis", "arrow"],
  );
});

test("two marks on one line are two offences", () => {
  const found = offencesIn(`a ${EM_DASH} b ${EM_DASH} c`, "x.ts");

  assert.equal(found.length, 2);
});

test("an accented proper noun is not punctuation", () => {
  assert.deepEqual(offencesIn("Plasmodium falcipar\u00fam", "x.py"), []);
});
