#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { pep440, tagVersion } from "./check-release.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PYPROJECT = "apps/api/pyproject.toml";
const INIT = "apps/api/src/pathfinder/__init__.py";
const IMAGES = ["pathfinder-api", "pathfinder-web"];
const TAGGER = "git@github.com:VEuPathDB/tagger.git";
const STAGES = new Map([
  ["qa", false],
  ["beta", false],
  ["prod", true],
]);

export function withApiVersion({ pyproject, init }, version) {
  const reading = tagVersion(`v${version}`) === null ? null : pep440(version);
  if (reading === null) throw new Error(`${version} is not a release version`);
  return {
    pyproject: pyproject.replace(/^version = "[^"]+"$/m, `version = "${reading}"`),
    init: init.replace(/^__version__ = "[^"]+"$/m, `__version__ = "${reading}"`),
  };
}

export function withImages(versions, version) {
  const body = versions.endsWith("\n") ? versions : `${versions}\n`;
  return IMAGES.reduce((text, image) => {
    const line = new RegExp(`^${image}:.*$`, "m");
    const entry = `${image}: ${version}`;
    return line.test(text) ? text.replace(line, entry) : `${text}${entry}\n`;
  }, body);
}

export function promotion(stage) {
  if (!STAGES.has(stage)) throw new Error(`${stage} is not qa, beta or prod`);
  return { branch: stage, review: STAGES.get(stage) };
}

function run(command, args, cwd = ROOT) {
  const done = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (done.status !== 0) throw new Error(`${command} ${args[0]} failed`);
}

function bump(version) {
  const read = (path) => readFileSync(join(ROOT, path), "utf8");
  const next = withApiVersion(
    { pyproject: read(PYPROJECT), init: read(INIT) },
    version,
  );
  writeFileSync(join(ROOT, PYPROJECT), next.pyproject);
  writeFileSync(join(ROOT, INIT), next.init);
  run("uv", ["lock"], join(ROOT, "apps/api"));
  run("corepack", ["yarn", "generate:types"]);
}

function tag(version) {
  run("node", ["scripts/check-release.mjs", `v${version}`]);
  run("git", ["tag", `v${version}`]);
  run("git", ["push", "origin", `v${version}`]);
}

async function requireImages(version) {
  for (const image of IMAGES) {
    const url = `https://hub.docker.com/v2/repositories/veupathdb/${image}/tags/${version}`;
    const answer = await fetch(url);
    if (!answer.ok) throw new Error(`${image}:${version} is not published yet`);
  }
}

async function promote(stage, version, push) {
  const { branch, review } = promotion(stage);
  await requireImages(version);
  const clone = mkdtempSync(join(tmpdir(), "tagger-"));
  run("git", ["clone", "--quiet", "--branch", branch, TAGGER, clone], ROOT);
  const file = join(clone, "versions.yml");
  writeFileSync(file, withImages(readFileSync(file, "utf8"), version));
  const proposal = `pathfinder-${version}`;
  if (review) run("git", ["switch", "--quiet", "-c", proposal], clone);
  run("git", ["commit", "--quiet", "-am", `Update pathfinder version to ${version}`], clone);
  run("git", ["show", "--stat", "--format=%s", "HEAD"], clone);
  if (!push) {
    console.log(`release: nothing pushed; add --push to move ${stage} to ${version}`);
    return;
  }
  run("git", ["push", "origin", review ? proposal : branch], clone);
  if (review) {
    run(
      "gh",
      ["pr", "create", "--base", branch, "--fill", "--head", proposal],
      clone,
    );
  }
}

async function main([action, first, second, flag]) {
  switch (action) {
    case "bump":
      return bump(first);
    case "tag":
      return tag(first);
    case "promote":
      return promote(first, second, flag === "--push");
    default:
      throw new Error(
        "usage: release.mjs bump <version> | tag <version> | promote <stage> <version> [--push]",
      );
  }
}

if (process.argv[1]?.endsWith("release.mjs")) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(`release: ${error.message}`);
    process.exit(1);
  });
}
