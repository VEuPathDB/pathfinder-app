import { test } from "node:test";
import assert from "node:assert/strict";

import { scanSource } from "./check-weak-assertions.mjs";

const wrap = (body) => `it("a test", () => {\n${body}\n});\n`;
const verdictOf = (body) => scanSource(wrap(body))[0]?.verdict ?? null;

test("a weak matcher on a plain value is an offender", () => {
  assert.equal(verdictOf(`expect(parse("x")).toBeTruthy();`), "only_weak_assertions");
});

test("a test with no expect at all is an offender", () => {
  assert.equal(verdictOf(`render(<Thing />);`), "no_assertions");
});

test("a strong matcher passes", () => {
  assert.equal(verdictOf(`expect(sum(1, 2)).toBe(3);`), null);
});

test("toBeEmptyDOMElement is a strong matcher", () => {
  assert.equal(verdictOf(`expect(container).toBeEmptyDOMElement();`), null);
});

test("a getBy query on a string literal is itself the assertion", () => {
  assert.equal(verdictOf(`expect(screen.getByText("3.48")).toBeTruthy();`), null);
});

test("a getBy query on a regex literal is itself the assertion", () => {
  assert.equal(verdictOf(`expect(screen.getByText(/3\\.48/)).toBeTruthy();`), null);
});

test("the query's later arguments do not have to be literals", () => {
  assert.equal(
    verdictOf(`expect(getByRole("button", { name: label })).toBeInTheDocument();`),
    null,
  );
});

test("getAllBy counts too, and so does a scoped query", () => {
  assert.equal(verdictOf(`expect(screen.getAllByRole("row")).toBeDefined();`), null);
  assert.equal(verdictOf(`expect(within(row).getByText("42")).toBeTruthy();`), null);
});

test("a query on a variable pins nothing the file states", () => {
  assert.equal(
    verdictOf(`expect(screen.getByText(expected)).toBeTruthy();`),
    "only_weak_assertions",
  );
});

test("queryBy returns null instead of throwing, so it stays weak", () => {
  assert.equal(
    verdictOf(`expect(screen.queryByText("3.48")).toBeTruthy();`),
    "only_weak_assertions",
  );
});

test("findBy returns a promise, so it stays weak", () => {
  assert.equal(
    verdictOf(`expect(await screen.findByText("3.48")).toBeTruthy();`),
    "only_weak_assertions",
  );
});

test("reading a property off a query is not the query", () => {
  assert.equal(
    verdictOf(`expect(screen.getByTestId("row").textContent).toBeTruthy();`),
    "only_weak_assertions",
  );
});

const nonEmptyLines = (body) =>
  scanSource(wrap(body))
    .filter((o) => o.verdict === "nonempty_check")
    .map((o) => o.line);

for (const check of [
  "expect(items.length).toBeGreaterThan(0);",
  "expect(items.length).toBeGreaterThanOrEqual(1);",
  "expect(items.length).not.toBe(0);",
  "expect(map.size).not.toEqual(0);",
  "expect(await rows.count()).toBeGreaterThan(0);",
  "expect(items).not.toHaveLength(0);",
  "expect(items).not.toEqual([]);",
  "await expect.poll(() => rows.count()).toBeGreaterThan(0);",
]) {
  test(`a non-empty check fails on its own line: ${check}`, () => {
    assert.deepEqual(nonEmptyLines(`expect(items[0]).toBe(1);\n${check}`), [3]);
  });
}

test("a non-empty check alone also leaves the test weak", () => {
  assert.equal(
    verdictOf(`expect(items.length).toBeGreaterThan(0);`),
    "only_weak_assertions",
  );
});

test("a justified non-empty check counts as strong", () => {
  const reason = "// weak-ok(nonempty): the site decides the count";
  assert.deepEqual(
    scanSource(wrap(`${reason}\nexpect(items.length).toBeGreaterThan(0);`)),
    [],
  );
  assert.deepEqual(
    scanSource(wrap(`expect(items.length).toBeGreaterThan(0); ${reason}`)),
    [],
  );
});

test("a marker without a reason justifies nothing", () => {
  assert.deepEqual(
    nonEmptyLines(`expect(items.length).toBeGreaterThan(0); // weak-ok(nonempty):`),
    [2],
  );
});

test("a count or a bound above one is not a non-empty check", () => {
  assert.deepEqual(nonEmptyLines(`expect(items.length).toBe(2);`), []);
  assert.deepEqual(nonEmptyLines(`expect(items.length).toBeGreaterThan(1);`), []);
  assert.deepEqual(nonEmptyLines(`expect(score).toBeGreaterThan(0);`), []);
  assert.deepEqual(nonEmptyLines(`expect(items).not.toEqual([1]);`), []);
});
