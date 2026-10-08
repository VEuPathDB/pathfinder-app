import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

import { collect, offencesIn, pep440, tagVersion } from "./check-release.mjs";

const PYPROJECT = (version, mcpTag) => `[project]
name = "pathfinder-api"
version = "${version}"

[dependency-groups]
dev = ["pytest>=9"]

[tool.uv.sources]
assistant-core = { git = "https://github.com/VEuPathDB/ai-assistant-platform", subdirectory = "packages/assistant-core", tag = "v0.3.0b2" }
veupathdb-mcp = { git = "https://github.com/VEuPathDB/ai-wdk-mcp", tag = "${mcpTag}" }

[tool.ruff]
line-length = 88
`;

const INIT = (version) => `"""Pathfinder."""\n\n__version__ = "${version}"\n`;

const COMPOSE = (wdkTag, researchTag) => `services:
  wdk-mcp:
    build:
      context: https://github.com/VEuPathDB/ai-wdk-mcp.git#${wdkTag}
  research-mcp:
    build:
      context: https://github.com/VEuPathDB/ai-wdk-mcp.git#${researchTag}
      target: research
`;

const WORKFLOW = (tag) => `jobs:
  publish:
    strategy:
      matrix:
        include:
          - image: pathfinder-wdk-mcp
            context: https://github.com/VEuPathDB/ai-wdk-mcp.git#${tag}
          - image: pathfinder-research-mcp
            context: https://github.com/VEuPathDB/ai-wdk-mcp.git#${tag}
            target: research
`;

const files = ({
  version = "0.2.0b5",
  init = version,
  mcpTag = "v0.2.0b3",
  wdk = mcpTag,
  research = mcpTag,
  workflow = mcpTag,
} = {}) =>
  new Map([
    ["apps/api/pyproject.toml", PYPROJECT(version, mcpTag)],
    ["apps/api/src/pathfinder/__init__.py", INIT(init)],
    ["docker-compose.yml", COMPOSE(wdk, research)],
    [".github/workflows/publish-images.yml", WORKFLOW(workflow)],
  ]);

test("a semver tag whose PEP 440 reading is the api version passes", () => {
  assert.deepEqual(offencesIn(files({ version: "0.2.0b5" }), "v0.2.0-b5"), []);
});

test("a PEP 440 tag is refused, because the image build publishes nothing for it", () => {
  assert.deepEqual(offencesIn(files({ version: "0.2.0b5" }), "v0.2.0b5"), [
    "tag v0.2.0b5 is not v plus a semver version, so the image build publishes nothing for it",
  ]);
});

test("a semver tag without its v is refused, though the image build would publish it", () => {
  assert.deepEqual(offencesIn(files({ version: "0.2.0b5" }), "0.2.0-b5"), [
    "tag 0.2.0-b5 has no leading v; a release tag is v plus the semver version",
  ]);
});

test("a tag that names another version than the api is refused", () => {
  assert.deepEqual(offencesIn(files({ version: "0.2.0b4" }), "v0.2.0-b5"), [
    "tag v0.2.0-b5 reads 0.2.0b5 under PEP 440, and apps/api/pyproject.toml says 0.2.0b4",
  ]);
});

test("a compose context that names another MCP release is refused", () => {
  assert.deepEqual(
    offencesIn(files({ mcpTag: "v0.2.0b3", research: "v0.2.0b2" }), "v0.2.0-b5"),
    [
      "docker-compose.yml: builds ai-wdk-mcp at v0.2.0b2, and apps/api/pyproject.toml pins v0.2.0b3",
    ],
  );
});

test("the publish workflow is held to the same MCP release", () => {
  assert.deepEqual(offencesIn(files({ workflow: "v0.2.0b2" })), [
    ".github/workflows/publish-images.yml: builds ai-wdk-mcp at v0.2.0b2, and apps/api/pyproject.toml pins v0.2.0b3",
  ]);
});

test("a file that names no MCP build context is refused", () => {
  const texts = files();
  texts.set("docker-compose.yml", "services:\n  api:\n    build: .\n");

  assert.deepEqual(offencesIn(texts), [
    "docker-compose.yml: names no ai-wdk-mcp build context",
  ]);
});

test("without a tag only the pins are read", () => {
  assert.deepEqual(offencesIn(files()), []);
});

test("the version the api reports must be the version it is built as", () => {
  assert.deepEqual(offencesIn(files({ version: "0.2.0b5", init: "0.2.0b4" })), [
    "apps/api/src/pathfinder/__init__.py: __version__ is 0.2.0b4, and apps/api/pyproject.toml says 0.2.0b5",
  ]);
});

test("a pyproject with no MCP pin is refused", () => {
  const texts = files();
  texts.set(
    "apps/api/pyproject.toml",
    texts.get("apps/api/pyproject.toml").replace(/^veupathdb-mcp = .*\n/m, ""),
  );

  assert.deepEqual(offencesIn(texts), [
    "apps/api/pyproject.toml: [tool.uv.sources] pins no veupathdb-mcp tag",
  ]);
});

test("a tag with build metadata is refused, because a docker tag cannot hold a plus sign", () => {
  assert.deepEqual(offencesIn(files({ version: "0.2.0b5" }), "v0.2.0-b5+abc"), [
    "tag v0.2.0-b5+abc carries build metadata, which no image tag can hold",
  ]);
});

test("a pre-release that is not a, b or rc is refused", () => {
  assert.deepEqual(offencesIn(files(), "v0.2.0-nightly"), [
    "tag v0.2.0-nightly has a pre-release that is not an a, b or rc pre-release",
  ]);
});

test("a release tag reads as the semver version after its v", () => {
  assert.equal(tagVersion("v1.4.0")?.version, "1.4.0");
  assert.equal(tagVersion("v0.2.0-a12")?.version, "0.2.0-a12");
  assert.equal(tagVersion("v0.2.0b5"), null);
  assert.equal(tagVersion("0.2.0-b5"), null);
  assert.equal(tagVersion("v01.2.0"), null);
});

test("PEP 440 reads every spelling of a pre-release the same way", () => {
  for (const spelling of [
    "0.2.0b5",
    "0.2.0-b5",
    "0.2.0.b5",
    "0.2.0-b.5",
    "0.2.0beta5",
    "0.2.0B5",
  ]) {
    assert.equal(pep440(spelling), "0.2.0b5", spelling);
  }
  assert.equal(pep440("0.2.0-a12"), "0.2.0a12");
  assert.equal(pep440("1.0.0-rc.1"), "1.0.0rc1");
  assert.equal(pep440("1.0.0-c1"), "1.0.0rc1");
  assert.equal(pep440("1.0.0-preview1"), "1.0.0rc1");
  assert.equal(pep440("1.0.0b"), "1.0.0b0");
  assert.equal(pep440("01.02.003"), "1.2.3");
});

test("a post, dev, epoch or local segment has no reading here", () => {
  for (const version of [
    "1.0.0.post1",
    "1.0.0.dev3",
    "1.0.0+local",
    "1!1.0.0",
    "1.0.0-nightly",
  ]) {
    assert.equal(pep440(version), null, version);
  }
});

test("a release equals its zero-padded spelling", () => {
  assert.deepEqual(offencesIn(files({ version: "1.0" }), "v1.0.0"), []);
});

test("the repository's own pins agree", () => {
  assert.deepEqual(collect(), []);
});

test("the command names each offence and exits non-zero", () => {
  const run = spawnSync(process.execPath, ["scripts/check-release.mjs", "v0.2.0b5"], {
    encoding: "utf8",
  });

  assert.equal(run.status, 1);
  assert.match(run.stderr, /check-release: FAILED/);
  assert.match(run.stderr, /tag v0\.2\.0b5 is not v plus a semver version/);
});

test("the command passes the repository with no tag", () => {
  const run = spawnSync(process.execPath, ["scripts/check-release.mjs"], {
    encoding: "utf8",
  });

  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /check-release: /);
});
