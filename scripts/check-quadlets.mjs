#!/usr/bin/env node
/**
 * The quadlet units this repository ships describe the cedar deployment.
 *
 * Podman's own generator is the authority, and it runs on Linux only, so this
 * check is what holds the units on a developer machine and in CI: every file
 * parses as systemd INI, every image is the registry image at the one tag
 * placeholder the installer substitutes, only the web and the api publish a
 * port and both bind the loopback address, and the api and the worker name
 * both MCP servers by container.
 *
 * `offencesIn` takes the unit texts and the installer text and returns what it
 * found, so the suite can drive it over strings. The CLI wrapper at the bottom
 * owns every console call and every exit code.
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const UNITS = join(ROOT, "quadlets");
const INSTALLER = join(ROOT, "deploy/cedar/install.sh");

// The installer replaces this with the release tag the operator names.
export const TAG_PLACEHOLDER = "__PATHFINDER_TAG__";
const REGISTRY = "ghcr.io/veupathdb";

// The image each unit runs. The worker runs the api image with a command of
// its own, as compose does.
const REGISTRY_IMAGES = new Map([
  ["pathfinder-api.container", "pathfinder-api"],
  ["pathfinder-worker.container", "pathfinder-api"],
  ["pathfinder-web.container", "pathfinder-web"],
  ["pathfinder-wdk-mcp.container", "pathfinder-wdk-mcp"],
  ["pathfinder-research-mcp.container", "pathfinder-research-mcp"],
]);
// The two units that run somebody else's image, each at a pinned tag.
const UPSTREAM_IMAGES = new Map([
  ["pathfinder-db.container", "docker.io/pgvector/pgvector:pg16"],
  ["pathfinder-searxng.container", "docker.io/searxng/searxng:"],
]);
// The host ports the deployment publishes, both on the loopback interface.
// Every other unit is reached by container name on the podman network.
const PUBLISHED = new Map([
  ["pathfinder-web.container", "127.0.0.1:3010:3000"],
  ["pathfinder-api.container", "127.0.0.1:8010:8000"],
]);
// The endpoints an assistant's declaration resolves to. A compose service name
// does not resolve on the podman network, so both units state them.
const MCP_URLS = new Map([
  ["PATHFINDER_WDK_MCP_URL", "http://pathfinder-wdk-mcp:8100/mcp"],
  ["PATHFINDER_RESEARCH_MCP_URL", "http://pathfinder-research-mcp:8110/mcp"],
]);
const MCP_CLIENTS = ["pathfinder-api.container", "pathfinder-worker.container"];
// The units that read the deployment's secrets. The database reads none.
const SECRET_READERS = [
  "pathfinder-api.container",
  "pathfinder-worker.container",
  "pathfinder-wdk-mcp.container",
  "pathfinder-research-mcp.container",
  "pathfinder-searxng.container",
];
const ENVIRONMENT_FILE = "%h/.config/pathfinder/.env";

/**
 * A systemd unit as sections of key and value pairs. A line that ends with a
 * backslash continues on the next one.
 */
export function parseUnit(text, path = "unit") {
  const errors = [];
  const sections = new Map();
  let section = null;
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    let line = lines[index].trim();
    let number = index + 1;
    while (line.endsWith("\\") && index + 1 < lines.length) {
      index += 1;
      line = `${line.slice(0, -1).trim()} ${lines[index].trim()}`;
    }
    if (line === "" || line.startsWith("#") || line.startsWith(";")) continue;
    if (line.startsWith("[")) {
      if (!line.endsWith("]") || line.length < 3) {
        errors.push(`${path}:${number}: not a section header -> ${line}`);
        continue;
      }
      section = line.slice(1, -1);
      if (!sections.has(section)) sections.set(section, []);
      continue;
    }
    const split = line.indexOf("=");
    if (split < 1) {
      errors.push(`${path}:${number}: not a key and a value -> ${line}`);
      continue;
    }
    if (section === null) {
      errors.push(`${path}:${number}: key outside a section -> ${line}`);
      continue;
    }
    sections
      .get(section)
      .push([line.slice(0, split).trim(), line.slice(split + 1).trim()]);
  }
  return { sections, errors };
}

/** Every value of one key in one section, in file order. */
function valuesOf(parsed, section, key) {
  return (parsed.sections.get(section) ?? [])
    .filter(([name]) => name === key)
    .map(([, value]) => value);
}

/** The value of one `Environment=NAME=value` entry, or undefined. */
function environmentValue(parsed, name) {
  const prefix = `${name}=`;
  const found = valuesOf(parsed, "Container", "Environment").find((value) =>
    value.startsWith(prefix),
  );
  return found === undefined ? undefined : found.slice(prefix.length);
}

function checkImage(name, parsed, report) {
  const images = valuesOf(parsed, "Container", "Image");
  if (images.length !== 1) {
    report(`${name}: expected one Image, found ${images.length}`);
    return;
  }
  const [image] = images;
  const registryImage = REGISTRY_IMAGES.get(name);
  const upstream = UPSTREAM_IMAGES.get(name);
  if (registryImage !== undefined) {
    const expected = `${REGISTRY}/${registryImage}:${TAG_PLACEHOLDER}`;
    if (image !== expected) {
      report(`${name}: image is ${image}, expected ${expected}`);
    }
  } else if (upstream !== undefined) {
    if (!image.startsWith(upstream)) {
      report(`${name}: image is ${image}, expected ${upstream}...`);
    }
  } else {
    report(`${name}: no image is declared for this unit`);
  }
  if (image.endsWith(":latest")) {
    report(`${name}: image runs :latest, which names no release`);
  }
}

function checkPublishedPorts(name, parsed, report) {
  const ports = valuesOf(parsed, "Container", "PublishPort");
  const expected = PUBLISHED.get(name);
  if (expected === undefined) {
    if (ports.length > 0) {
      report(`${name}: publishes ${ports.join(", ")}, expected no host port`);
    }
    return;
  }
  if (ports.length !== 1 || ports[0] !== expected) {
    report(`${name}: publishes ${ports.join(", ") || "nothing"}, expected ${expected}`);
  }
}

function checkEnvironment(name, parsed, report) {
  if (MCP_CLIENTS.includes(name)) {
    for (const [variable, url] of MCP_URLS) {
      const value = environmentValue(parsed, variable);
      if (value !== url) {
        report(`${name}: ${variable} is ${value ?? "unset"}, expected ${url}`);
      }
    }
  }
  if (name === "pathfinder-api.container") {
    const allowed = environmentValue(parsed, "FORWARDED_ALLOW_IPS");
    if (allowed !== "*") {
      report(`${name}: FORWARDED_ALLOW_IPS is ${allowed ?? "unset"}, expected *`);
    }
  }
  if (name === "pathfinder-web.container") {
    // The value is baked into the image at build time, so a runtime one is inert.
    if (environmentValue(parsed, "NEXT_PUBLIC_API_URL") !== undefined) {
      report(`${name}: NEXT_PUBLIC_API_URL is read at build time, not at run time`);
    }
  }
  const files = valuesOf(parsed, "Container", "EnvironmentFile");
  if (SECRET_READERS.includes(name)) {
    if (!files.includes(ENVIRONMENT_FILE)) {
      report(`${name}: no EnvironmentFile=${ENVIRONMENT_FILE}`);
    }
  } else if (files.length > 0) {
    report(`${name}: reads ${files.join(", ")}, expected no EnvironmentFile`);
  }
}

/**
 * `units` maps a file name to its text; `installer` is the text of
 * `deploy/cedar/install.sh`.
 */
export function offencesIn(units, installer) {
  const offences = [];
  const report = (message) => offences.push(message);
  const expected = [...REGISTRY_IMAGES.keys(), ...UPSTREAM_IMAGES.keys()].sort();
  const found = [...units.keys()].sort();
  if (found.join(" ") !== expected.join(" ")) {
    report(`quadlets hold ${found.join(", ")}, expected ${expected.join(", ")}`);
  }
  for (const [name, text] of units) {
    const parsed = parseUnit(text, name);
    for (const error of parsed.errors) report(error);
    if (!parsed.sections.has("Container")) {
      report(`${name}: no [Container] section`);
      continue;
    }
    checkImage(name, parsed, report);
    checkPublishedPorts(name, parsed, report);
    checkEnvironment(name, parsed, report);
    if (!valuesOf(parsed, "Container", "Network").includes("pathfinder.network")) {
      report(`${name}: not on pathfinder.network`);
    }
    if (!valuesOf(parsed, "Install", "WantedBy").includes("default.target")) {
      report(`${name}: no [Install] WantedBy=default.target`);
    }
    // The installer starts and reports every unit, so a new one is not missed.
    const service = `${name.replace(/\.container$/, "")}.service`;
    if (!installer.includes(service)) {
      report(`deploy/cedar/install.sh: does not name ${service}`);
    }
  }
  if (!installer.includes(TAG_PLACEHOLDER)) {
    report(`deploy/cedar/install.sh: does not substitute ${TAG_PLACEHOLDER}`);
  }
  return offences;
}

export function collect(unitsDir = UNITS, installerPath = INSTALLER) {
  const units = new Map(
    readdirSync(unitsDir)
      .filter((name) => name.endsWith(".container"))
      .map((name) => [name, readFileSync(join(unitsDir, name), "utf8")]),
  );
  return offencesIn(units, readFileSync(installerPath, "utf8"));
}

const invokedDirectly = process.argv[1]?.endsWith("check-quadlets.mjs");
if (invokedDirectly) {
  const offences = collect();
  if (offences.length > 0) {
    console.error("check-quadlets: FAILED");
    for (const offence of offences) console.error(`  ${offence}`);
    process.exit(1);
  }
  console.log(
    `check-quadlets: ${REGISTRY_IMAGES.size + UPSTREAM_IMAGES.size} units conform (0 violations)`,
  );
}
