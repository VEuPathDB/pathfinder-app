/**
 * Flag Vitest / Playwright tests whose only `expect(...)` chains are weak.
 *
 * Weak matchers — survive almost any mutation to the function under test:
 *   toBeTruthy, toBeFalsy, toBeDefined, toBeUndefined, toBeNull, toBeNaN,
 *   toBeInstanceOf
 * Plus tests with no expect at all.
 *
 * Strong matchers (any in the chain → test passes) — pin a value, error, or
 * structural shape:
 *   toBe, toEqual, toStrictEqual, toMatch, toMatchObject, toMatchSnapshot,
 *   toMatchInlineSnapshot, toHaveLength, toThrow, toThrowError,
 *   toHaveBeenCalled*, toContain*, toHaveProperty, toHaveTextContent,
 *   toBeVisible/Hidden, toHaveValue, toHaveAttribute, toHaveClass,
 *   toBeChecked, toBeDisabled, toBeEnabled, toBeFocused, toBeInTheDocument,
 *   toBeEmptyDOMElement, toBeGreater/Less*, toBeCloseTo, toBeOneOf,
 *   toContainText, toHaveURL, toHaveTitle, toHaveCount, rejects/resolves
 *   chains.
 *
 * A throwing query is itself a value assertion. `getBy*` and `getAllBy*`
 * throw when nothing matches, so `expect(screen.getByText("3.48"))` already
 * pins "3.48" and the matcher after it may be weak. The rule needs the
 * query's first argument to be a string or regex literal: a variable pins
 * whatever the test computed, which is not a value the file states.
 * `queryBy*` returns null and `findBy*` returns a promise, so neither
 * asserts anything on its own and both stay weak.
 *
 * A non-empty check (`expect(x.length).toBeGreaterThan(0)`,
 * `.toBeGreaterThanOrEqual(1)`, `.not.toBe(0)`, `.not.toHaveLength(0)`,
 * `.not.toEqual([])`) fails on its own line, whatever else the test asserts,
 * unless that line or the comment line above it carries
 * `// weak-ok(nonempty): <why the count itself is the behavior>`.
 *
 * Usage:
 *   node scripts/check-weak-assertions.mjs
 */

import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = path.resolve(process.cwd());
const SCAN_ROOTS = [path.join(ROOT, "src"), path.join(ROOT, "e2e")];

const WEAK_MATCHERS = new Set([
  "toBeTruthy",
  "toBeFalsy",
  "toBeDefined",
  "toBeUndefined",
  "toBeNull",
  "toBeNaN",
  "toBeInstanceOf",
]);

const STRONG_MATCHERS = new Set([
  "toBe",
  "toEqual",
  "toStrictEqual",
  "toMatch",
  "toMatchObject",
  "toMatchSnapshot",
  "toMatchInlineSnapshot",
  "toMatchFileSnapshot",
  "toHaveLength",
  "toThrow",
  "toThrowError",
  "toHaveBeenCalled",
  "toHaveBeenCalledTimes",
  "toHaveBeenCalledWith",
  "toHaveBeenLastCalledWith",
  "toHaveBeenNthCalledWith",
  "toContain",
  "toContainEqual",
  "toContainText",
  "toHaveProperty",
  "toHaveTextContent",
  "toBeVisible",
  "toBeHidden",
  "toBeAttached",
  "toHaveValue",
  "toHaveAttribute",
  "toHaveClass",
  "toBeChecked",
  "toBeDisabled",
  "toBeEnabled",
  "toBeFocused",
  "toBeInTheDocument",
  "toBeEmptyDOMElement",
  "toBeGreaterThan",
  "toBeGreaterThanOrEqual",
  "toBeLessThan",
  "toBeLessThanOrEqual",
  "toBeCloseTo",
  "toBeOneOf",
  "toHaveURL",
  "toHaveTitle",
  "toHaveCount",
  "toHaveScreenshot",
]);

const TEST_FN_NAMES = new Set(["it", "test"]);
const NONEMPTY_MARKER = "weak-ok(nonempty):";
const LENGTH_NAMES = new Set(["length", "size"]);

function* walkFiles(dir) {
  if (!fs.existsSync(dir)) return;
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name === "node_modules" || ent.name.startsWith(".")) continue;
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      yield* walkFiles(full);
    } else if (/\.(test|spec)\.(ts|tsx|mts)$/.test(ent.name)) {
      yield full;
    }
  }
}

const THROWING_QUERY = /^get(All)?By[A-Z]/;

function calleeName(node) {
  if (ts.isPropertyAccessExpression(node)) {
    return node.name.escapedText?.toString() ?? "";
  }
  if (ts.isIdentifier(node)) return node.escapedText?.toString() ?? "";
  return "";
}

/**
 * True for `screen.getByText("x")`, `within(row).getAllByRole(/x/)` and the
 * destructured `getByTestId("x")`: a query that throws on absence, given a
 * literal to look for.
 */
function isThrowingQueryOnALiteral(node) {
  if (node === undefined || !ts.isCallExpression(node)) return false;
  if (!THROWING_QUERY.test(calleeName(node.expression))) return false;
  const first = node.arguments[0];
  if (first === undefined) return false;
  return ts.isStringLiteralLike(first) || ts.isRegularExpressionLiteral(first);
}

function isLiteral(node, value) {
  return node !== undefined && ts.isNumericLiteral(node) && Number(node.text) === value;
}

function isEmptyArray(node) {
  return (
    node !== undefined &&
    ts.isArrayLiteralExpression(node) &&
    node.elements.length === 0
  );
}

function isLengthLike(node) {
  if (node === undefined) return false;
  if (ts.isAwaitExpression(node) || ts.isParenthesizedExpression(node)) {
    return isLengthLike(node.expression);
  }
  if (ts.isArrowFunction(node))
    return !ts.isBlock(node.body) && isLengthLike(node.body);
  if (ts.isPropertyAccessExpression(node)) {
    return LENGTH_NAMES.has(node.name.escapedText?.toString() ?? "");
  }
  return ts.isCallExpression(node) && calleeName(node.expression) === "count";
}

function isNonEmptyCheck(matcher, negated, matcherArgs, subject) {
  const [bound] = matcherArgs;
  if (negated) {
    if (matcher === "toHaveLength") return isLiteral(bound, 0);
    if (matcher === "toEqual" || matcher === "toStrictEqual") {
      return isEmptyArray(bound) || (isLiteral(bound, 0) && isLengthLike(subject));
    }
    return matcher === "toBe" && isLiteral(bound, 0) && isLengthLike(subject);
  }
  if (matcher === "toBeGreaterThan")
    return isLiteral(bound, 0) && isLengthLike(subject);
  return (
    matcher === "toBeGreaterThanOrEqual" && isLiteral(bound, 1) && isLengthLike(subject)
  );
}

/** Pull the matcher name off an `expect(x).chain.<matcher>(...)` call. */
function classifyExpectCall(expr) {
  // expr: CallExpression at the tail of an expect chain
  let node = expr.expression;
  let lastMatcher = null;
  let sawStrong = false;
  let sawWeak = false;
  let chainDepth = 0;
  let expectCall = null;
  let negated = false;

  while (ts.isPropertyAccessExpression(node) || ts.isCallExpression(node)) {
    if (ts.isPropertyAccessExpression(node)) {
      const name = node.name.escapedText?.toString() ?? "";
      if (name === "not") negated = true;
      if (name === "rejects" || name === "resolves") {
        sawStrong = true;
      } else if (name && name !== "not") {
        if (lastMatcher === null) lastMatcher = name;
        if (STRONG_MATCHERS.has(name)) sawStrong = true;
        if (WEAK_MATCHERS.has(name)) sawWeak = true;
      }
      node = node.expression;
    } else if (ts.isCallExpression(node)) {
      expectCall = node;
      node = node.expression;
      chainDepth++;
      if (chainDepth > 50) break;
    }
  }

  if (
    !ts.isIdentifier(node) ||
    (node.escapedText !== "expect" && node.escapedText !== "expectAsync")
  ) {
    return null;
  }
  if (expectCall !== null && isThrowingQueryOnALiteral(expectCall.arguments[0])) {
    sawStrong = true;
  }
  const nonEmpty = isNonEmptyCheck(
    lastMatcher,
    negated,
    expr.arguments,
    expectCall?.arguments[0],
  );
  return { sawStrong: sawStrong && !nonEmpty, sawWeak, lastMatcher, nonEmpty };
}

function justified(sourceFile, node) {
  const lines = sourceFile.text.split("\n");
  const first = sourceFile.getLineAndCharacterOfPosition(node.getStart()).line;
  const last = sourceFile.getLineAndCharacterOfPosition(node.getEnd()).line;
  const candidates = lines.slice(first, last + 1);
  const above = first > 0 ? lines[first - 1].trim() : "";
  if (above.startsWith("//")) candidates.push(above);
  return candidates.some((line) => {
    const at = line.indexOf(NONEMPTY_MARKER);
    return at >= 0 && line.slice(at + NONEMPTY_MARKER.length).trim() !== "";
  });
}

function findTestFunctions(sourceFile) {
  const tests = [];
  function visit(node) {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      TEST_FN_NAMES.has(node.expression.escapedText?.toString()) &&
      node.arguments.length >= 2
    ) {
      const titleArg = node.arguments[0];
      const bodyArg = node.arguments[node.arguments.length - 1];
      if (
        ts.isStringLiteralLike(titleArg) &&
        (ts.isFunctionExpression(bodyArg) || ts.isArrowFunction(bodyArg))
      ) {
        tests.push({ title: titleArg.text, body: bodyArg, node });
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return tests;
}

const HELPER_PREFIX = /^(expect|assert|verify|check)([A-Z_]|$)/;

function isDelegatedAssertion(callExpr) {
  // Calls like `chatPage.expectSendDisabled()` or `helpers.assertX(...)` —
  // method name signals an assertion the helper performs internally.
  const fn = callExpr.expression;
  if (ts.isPropertyAccessExpression(fn)) {
    const name = fn.name.escapedText?.toString() ?? "";
    if (HELPER_PREFIX.test(name)) return true;
  }
  if (ts.isIdentifier(fn) && HELPER_PREFIX.test(fn.escapedText?.toString() ?? "")) {
    return true;
  }
  return false;
}

function classifyTest(testNode, sourceFile) {
  let strong = 0;
  let weak = 0;
  let expects = 0;
  const nonEmpty = [];
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const result = classifyExpectCall(node);
      if (result?.nonEmpty && justified(sourceFile, node)) {
        expects++;
        strong++;
      } else if (result?.nonEmpty) {
        expects++;
        weak++;
        nonEmpty.push(
          sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1,
        );
      } else if (result) {
        expects++;
        if (result.sawStrong) strong++;
        else if (result.sawWeak) weak++;
      } else if (isDelegatedAssertion(node)) {
        expects++;
        strong++;
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(testNode.body);
  if (expects === 0) return { verdict: "no_assertions", nonEmpty };
  if (strong === 0) return { verdict: "only_weak_assertions", nonEmpty };
  return { verdict: null, nonEmpty };
}

/** Classify every test in one source text. Exported so the checker has tests. */
export function scanSource(source, filePath = "test.tsx") {
  const sf = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true);
  const offenders = [];
  for (const t of findTestFunctions(sf)) {
    const { verdict, nonEmpty } = classifyTest(t, sf);
    const file = path.relative(ROOT, filePath);
    if (verdict) {
      const { line } = sf.getLineAndCharacterOfPosition(t.node.getStart());
      offenders.push({ file, line: line + 1, title: t.title, verdict });
    }
    for (const line of nonEmpty) {
      offenders.push({ file, line, title: t.title, verdict: "nonempty_check" });
    }
  }
  return offenders;
}

function scanFile(filePath) {
  return scanSource(fs.readFileSync(filePath, "utf8"), filePath);
}

function main() {
  const offenders = [];
  for (const root of SCAN_ROOTS) {
    for (const file of walkFiles(root)) {
      offenders.push(...scanFile(file));
    }
  }

  if (offenders.length > 0) {
    console.log(
      `\n${offenders.length} test(s) with weak-only or missing expectations:\n`,
    );
    for (const o of offenders) {
      console.log(`  ${o.file}:${o.line}  "${o.title}"  [${o.verdict}]`);
    }
    console.log(
      "\nFix by adding at least one strong matcher: toEqual, toBe (with a literal), " +
        "toMatchObject, toThrow, toHaveBeenCalledWith, toBeVisible, toHaveValue, " +
        "toHaveTextContent, toHaveLength, etc. A non-empty check states the " +
        `exact count or items instead, or carries '// ${NONEMPTY_MARKER} <reason>' ` +
        "where the count itself is the behavior.",
    );
    return 1;
  }

  console.log("weak-assertion check passed: every test states a value.");
  return 0;
}

const invokedDirectly = process.argv[1]?.endsWith("check-weak-assertions.mjs");
if (invokedDirectly) process.exit(main());
