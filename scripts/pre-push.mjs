#!/usr/bin/env node
import { execFileSync, spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export const CONFIG = ".pre-commit-config.yaml";
export const FIRST = ["shared-ts-openapi"];
const CHANGED = "--diff-filter=ACMRTUXB";

export function manualHooks(text) {
  return text
    .split(/^\s*- id: /m)
    .slice(1)
    .filter((block) => /^\s*stages: \[manual\]\s*$/m.test(block))
    .map((block) => block.split("\n")[0].trim());
}

export function phases(hooks) {
  return [
    FIRST.filter((hook) => hooks.includes(hook)),
    hooks.filter((hook) => !FIRST.includes(hook)),
  ];
}

export function pushedFiles(env, git) {
  const from = env.PRE_COMMIT_FROM_REF;
  const to = env.PRE_COMMIT_TO_REF;
  const listed =
    from && to
      ? git(["diff", "--name-only", "--no-ext-diff", CHANGED, `${from}...${to}`])
      : git(["ls-files"]);
  return listed.split("\n").filter(Boolean);
}

function preCommit() {
  const installed = join(homedir(), ".local", "bin", "pre-commit");
  return existsSync(installed) ? installed : "pre-commit";
}

function runHook(hook, files) {
  const started = Date.now();
  return new Promise((done) => {
    const child = spawn(
      preCommit(),
      ["run", hook, "--hook-stage", "manual", "--files", ...files],
      { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] },
    );
    const output = [];
    child.stdout.on("data", (chunk) => output.push(chunk));
    child.stderr.on("data", (chunk) => output.push(chunk));
    child.on("close", (code) => {
      const seconds = ((Date.now() - started) / 1000).toFixed(1);
      process.stdout.write(`--- ${hook} (${seconds} s)\n${Buffer.concat(output)}`);
      done({ hook, passed: code === 0 });
    });
  });
}

async function runPhase(hooks, files) {
  const results = await Promise.all(hooks.map((hook) => runHook(hook, files)));
  return results.filter((result) => !result.passed).map((result) => result.hook);
}

const invokedDirectly = process.argv[1]?.endsWith("pre-push.mjs");
if (invokedDirectly) {
  const git = (args) => execFileSync("git", args, { cwd: ROOT, encoding: "utf8" });
  const files = pushedFiles(process.env, git);
  if (files.length === 0) {
    console.log("pre-push: the push changes no file");
    process.exit(0);
  }
  const started = Date.now();
  const failed = [];
  for (const hooks of phases(manualHooks(readFileSync(join(ROOT, CONFIG), "utf8")))) {
    failed.push(...(await runPhase(hooks, files)));
    if (failed.length > 0) break;
  }
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  if (failed.length > 0) {
    console.error(`pre-push: FAILED in ${seconds} s: ${failed.join(", ")}`);
    process.exit(1);
  }
  console.log(`pre-push: every gate passed in ${seconds} s`);
}
