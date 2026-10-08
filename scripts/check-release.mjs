#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PYPROJECT = "apps/api/pyproject.toml";
const INIT = "apps/api/src/pathfinder/__init__.py";
const MCP_CONTEXT_FILES = [
  "docker-compose.yml",
  ".github/workflows/publish-images.yml",
];
const FILES = [PYPROJECT, INIT, ...MCP_CONTEXT_FILES];

const IDENTIFIER = String.raw`(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)`;
const SEMVER_TAG = new RegExp(
  String.raw`^v((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-${IDENTIFIER}(?:\.${IDENTIFIER})*)?)(\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$`,
);
const PEP440 =
  /^v?(\d+(?:\.\d+)*)(?:[-_.]?(a|alpha|b|beta|c|rc|pre|preview)[-_.]?(\d+)?)?$/i;
const PRE_RELEASE = new Map([
  ["a", "a"],
  ["alpha", "a"],
  ["b", "b"],
  ["beta", "b"],
  ["c", "rc"],
  ["rc", "rc"],
  ["pre", "rc"],
  ["preview", "rc"],
]);
const MCP_CONTEXT = /github\.com\/VEuPathDB\/ai-wdk-mcp\.git#([^\s"']+)/g;

export function tagVersion(tag) {
  const match = SEMVER_TAG.exec(tag);
  return match === null ? null : { version: match[1], metadata: match[2] ?? "" };
}

function parse(version) {
  const match = PEP440.exec(version);
  if (match === null) return null;
  const release = match[1].split(".").map(Number);
  const pre =
    match[2] === undefined
      ? ""
      : `${PRE_RELEASE.get(match[2].toLowerCase())}${Number(match[3] ?? 0)}`;
  return { release, pre };
}

export function pep440(version) {
  const parsed = parse(version);
  return parsed === null ? null : `${parsed.release.join(".")}${parsed.pre}`;
}

function samePep440(left, right) {
  const key = (parsed) =>
    parsed === null
      ? null
      : `${parsed.release.join(".").replace(/(\.0)+$/, "")}${parsed.pre}`;
  const a = key(parse(left));
  return a !== null && a === key(parse(right));
}

function section(toml, name) {
  const lines = toml.split("\n");
  const start = lines.findIndex((line) => line.trim() === `[${name}]`);
  if (start === -1) return "";
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => line.startsWith("["));
  return (end === -1 ? rest : rest.slice(0, end)).join("\n");
}

function tagOffences(tag, apiVersion) {
  const read = tagVersion(tag);
  if (read === null && tagVersion(`v${tag}`) !== null) {
    return [`tag ${tag} has no leading v; a release tag is v plus the semver version`];
  }
  if (read === null) {
    return [
      `tag ${tag} is not v plus a semver version, so the image build publishes nothing for it`,
    ];
  }
  if (read.metadata !== "") {
    return [`tag ${tag} carries build metadata, which no image tag can hold`];
  }
  const reading = pep440(read.version);
  if (reading === null)
    return [`tag ${tag} has a pre-release that is not an a, b or rc pre-release`];
  if (apiVersion !== null && !samePep440(reading, apiVersion)) {
    return [
      `tag ${tag} reads ${reading} under PEP 440, and ${PYPROJECT} says ${apiVersion}`,
    ];
  }
  return [];
}

export function offencesIn(texts, tag) {
  const offences = [];
  const pyproject = texts.get(PYPROJECT);
  const apiVersion =
    /^version\s*=\s*"([^"]+)"$/m.exec(section(pyproject, "project"))?.[1] ?? null;
  if (apiVersion === null) offences.push(`${PYPROJECT}: [project] names no version`);

  const reported = /^__version__\s*=\s*"([^"]+)"$/m.exec(texts.get(INIT))?.[1] ?? null;
  if (reported === null) {
    offences.push(`${INIT}: names no __version__`);
  } else if (apiVersion !== null && reported !== apiVersion) {
    offences.push(
      `${INIT}: __version__ is ${reported}, and ${PYPROJECT} says ${apiVersion}`,
    );
  }

  const pin =
    /^veupathdb-mcp\s*=\s*\{[^}\n]*\btag\s*=\s*"([^"]+)"/m.exec(
      section(pyproject, "tool.uv.sources"),
    )?.[1] ?? null;
  if (pin === null)
    offences.push(`${PYPROJECT}: [tool.uv.sources] pins no veupathdb-mcp tag`);

  for (const path of MCP_CONTEXT_FILES) {
    const refs = [...texts.get(path).matchAll(MCP_CONTEXT)].map((match) => match[1]);
    if (refs.length === 0) offences.push(`${path}: names no ai-wdk-mcp build context`);
    for (const ref of new Set(refs)) {
      if (pin !== null && ref !== pin) {
        offences.push(
          `${path}: builds ai-wdk-mcp at ${ref}, and ${PYPROJECT} pins ${pin}`,
        );
      }
    }
  }

  if (tag !== undefined) offences.push(...tagOffences(tag, apiVersion));
  return offences;
}

export function collect(tag, root = ROOT) {
  const texts = new Map(
    FILES.map((path) => [path, readFileSync(join(root, path), "utf8")]),
  );
  return offencesIn(texts, tag);
}

const invokedDirectly = process.argv[1]?.endsWith("check-release.mjs");
if (invokedDirectly) {
  const tag = process.argv[2];
  const offences = collect(tag);
  if (offences.length > 0) {
    console.error("check-release: FAILED");
    for (const offence of offences) console.error(`  ${offence}`);
    process.exit(1);
  }
  const subject =
    tag === undefined
      ? "the api version and the MCP pins agree"
      : `tag ${tag} names the api version, and the MCP pins agree`;
  console.log(`check-release: ${subject} (0 violations)`);
}
