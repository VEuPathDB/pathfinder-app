import { test } from "node:test";
import assert from "node:assert/strict";

import { promotion, withApiVersion, withImages } from "./release.mjs";

test("a version is written to the api files in its PEP 440 spelling", () => {
  const pyproject = '[project]\nname = "strategist-api"\nversion = "0.2.0b16"\n';
  const init = '"""x."""\n\n__version__ = "0.2.0b16"\n';
  assert.deepEqual(withApiVersion({ pyproject, init }, "0.9.0-b1"), {
    pyproject: '[project]\nname = "strategist-api"\nversion = "0.9.0b1"\n',
    init: '"""x."""\n\n__version__ = "0.9.0b1"\n',
  });
});

test("a version with no PEP 440 reading is refused", () => {
  assert.throws(
    () => withApiVersion({ pyproject: "", init: "" }, "0.9.0-qa1"),
    /0\.9\.0-qa1 is not a release version/,
  );
});

test("promoting adds both images when the stage lists neither", () => {
  assert.equal(
    withImages("service-eda: 1.16.0\n", "0.9.0-b1"),
    "service-eda: 1.16.0\npathfinder-api: 0.9.0-b1\npathfinder-web: 0.9.0-b1\n",
  );
});

test("promoting moves both images and leaves every other service", () => {
  const held =
    "pathfinder-api: 0.9.0-b1\nservice-eda: 1.16.0\npathfinder-web: 0.9.0-b1\n";
  assert.equal(
    withImages(held, "0.9.0-b2"),
    "pathfinder-api: 0.9.0-b2\nservice-eda: 1.16.0\npathfinder-web: 0.9.0-b2\n",
  );
});

test("qa and beta take a commit, and prod takes a pull request", () => {
  assert.deepEqual(promotion("qa"), { branch: "qa", review: false });
  assert.deepEqual(promotion("beta"), { branch: "beta", review: false });
  assert.deepEqual(promotion("prod"), { branch: "prod", review: true });
});

test("a stage the ladder does not name is refused", () => {
  assert.throws(() => promotion("staging"), /staging is not qa, beta or prod/);
});
