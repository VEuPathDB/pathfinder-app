#!/usr/bin/env node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export const QA_SITES = "deploy/sites/qa.yml";
export const TEST_SITES = "e2e-sites.yaml";
export const E2E_COMPOSE = "docker-compose.e2e.yml";
export const WORKFLOWS = ".github/workflows";
export const PYPROJECT = "apps/api/pyproject.toml";
export const WORKFLOW_SITES = "${{ github.workspace }}/deploy/sites/qa.yml";
export const EXCLUDED = new Set([
  "docs",
  "fixtures-production-backup-2026-10-09",
  "thesis",
  "node_modules",
  "__pycache__",
  "_build",
  "playwright-report",
  "test-results",
  "blob-report",
  "apps/api/data/catalogs",
  "apps/api/wdk-hidden-defaults.json",
  "apps/api/wdk-live-summary.json",
]);
const BINARY = /\.(png|jpe?g|gif|webp|ico|pdf|gz|zip|woff2?|ttf|otf|pyc|sqlite|db)$/i;
const SECRET_ENV = /^\.env(\..+)?$/;
const SITES_VARIABLE = "VEUPATHDB_SITES_CONFIG";
const LIVE_RUN = /-m\s+live_wdk\b|-m\s+veupathdb_mcp\b|veupathdb\.devtools\.fixtures\s+record\b/;
const SITE_SERVICES = ["api", "worker"];

const SITE_DOMAINS = [
  "veupathdb",
  "plasmodb",
  "toxodb",
  "cryptodb",
  "giardiadb",
  "amoebadb",
  "microsporidiadb",
  "piroplasmadb",
  "tritrypdb",
  "trichdb",
  "fungidb",
  "vectorbase",
  "hostdb",
  "orthomcl",
];
const HOST = new RegExp(
  String.raw`(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]+\.)*)(${SITE_DOMAINS.join("|")})\.org\b`,
  "gi",
);
const PRODUCTION_PREFIX = /^(?:|www\.|beta\.|auth\.|w\d+\.)$/i;

function isMailbox(line, at) {
  if (line[at - 1] !== "@") return false;
  const token = /\S*$/.exec(line.slice(0, at - 1))[0];
  return !token.includes("://");
}

export function productionHosts(text) {
  const found = [];
  text.split("\n").forEach((line, index) => {
    for (const match of line.matchAll(HOST)) {
      if (PRODUCTION_PREFIX.test(match[1]) && !isMailbox(line, match.index)) {
        found.push({ line: index + 1, host: match[0].toLowerCase() });
      }
    }
  });
  return found;
}

export function siteEntries(text) {
  const entries = new Map();
  let inSites = false;
  let current = null;
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\s+#.*$/, "").replace(/^#.*$/, "");
    if (line.trim() === "") continue;
    if (/^\S/.test(line)) {
      inSites = line.trim() === "sites:";
      current = null;
      continue;
    }
    if (!inSites) continue;
    const id = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(line);
    if (id !== null) {
      current = new Map();
      entries.set(id[1], current);
      continue;
    }
    const field = /^ {4}([A-Za-z0-9_]+):\s*(.*)$/.exec(line);
    if (field !== null && current !== null) current.set(field[1], field[2].trim());
  }
  return entries;
}

function topLevelBlock(text, key) {
  const lines = text.split("\n");
  const start = lines.findIndex((line) => line === `${key}:`);
  if (start === -1) return [];
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => /^\S/.test(line));
  return end === -1 ? rest : rest.slice(0, end);
}

export function composeServices(text) {
  const services = new Map();
  let current = null;
  let inVolumes = false;
  for (const line of topLevelBlock(text, "services")) {
    const name = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(line);
    if (name !== null) {
      current = { sitesConfig: null, mounts: new Map() };
      services.set(name[1], current);
      inVolumes = false;
      continue;
    }
    if (current === null) continue;
    if (/^ {4}\S/.test(line)) inVolumes = /^ {4}volumes:/.test(line);
    const variable = new RegExp(String.raw`^\s+${SITES_VARIABLE}:\s*(\S+)`).exec(line);
    if (variable !== null) current.sitesConfig = variable[1];
    const mount = /^\s+-\s+"?\.\/([^:"]+):([^:"]+)/.exec(line);
    if (inVolumes && mount !== null) current.mounts.set(mount[2], mount[1]);
  }
  return services;
}

export function mountedFiles(composeText) {
  const files = new Set();
  for (const service of composeServices(composeText).values()) {
    for (const source of service.mounts.values()) files.add(source);
  }
  return [...files];
}

function workflowSites(text) {
  for (const line of topLevelBlock(text, "env")) {
    const variable = new RegExp(String.raw`^\s+${SITES_VARIABLE}:\s*(.+?)\s*$`).exec(line);
    if (variable !== null) return variable[1].replace(/^"(.*)"$/, "$1");
  }
  return null;
}

function e2eSites(text) {
  const listed = /^\s+E2E_SITES:\s*(\S+)/m.exec(text);
  return listed === null ? [] : listed[1].split(",").map((site) => site.trim());
}

export function offencesIn(texts) {
  const offences = [];
  for (const [path, text] of texts) {
    for (const { line, host } of productionHosts(text)) {
      offences.push(`${path}:${line}: names the production host ${host}`);
    }
  }

  const qa = siteEntries(texts.get(QA_SITES) ?? "");
  const listed = siteEntries(texts.get(TEST_SITES) ?? "");
  if (listed.size === 0) offences.push(`${TEST_SITES}: lists no site`);
  for (const [id, fields] of listed) {
    const copy = qa.get(id);
    if (copy === undefined) {
      offences.push(`${TEST_SITES}: ${id} is not in ${QA_SITES}`);
      continue;
    }
    for (const key of new Set([...fields.keys(), ...copy.keys()])) {
      if (fields.get(key) !== copy.get(key)) {
        offences.push(
          `${TEST_SITES}: ${id}.${key} is ${fields.get(key) ?? "absent"}, and ${QA_SITES} says ${copy.get(key) ?? "absent"}`,
        );
      }
    }
  }

  const services = composeServices(texts.get(E2E_COMPOSE) ?? "");
  for (const name of SITE_SERVICES) {
    const service = services.get(name);
    if (service?.sitesConfig == null) {
      offences.push(`${E2E_COMPOSE}: ${name} does not set ${SITES_VARIABLE}`);
      continue;
    }
    const source = service.mounts.get(service.sitesConfig);
    if (source !== TEST_SITES) {
      offences.push(
        `${E2E_COMPOSE}: ${name} reads ${service.sitesConfig}, which is not a mount of ${TEST_SITES}`,
      );
    }
  }

  for (const [path, text] of texts) {
    if (!path.startsWith(`${WORKFLOWS}/`)) continue;
    if (LIVE_RUN.test(text)) {
      const named = workflowSites(text);
      if (named !== WORKFLOW_SITES) {
        offences.push(
          `${path}: reaches a live site, and its top-level env sets ${SITES_VARIABLE} to ${named ?? "nothing"}, not ${WORKFLOW_SITES}`,
        );
      }
    }
    for (const site of e2eSites(text)) {
      if (!listed.has(site)) offences.push(`${path}: E2E_SITES names ${site}, which ${TEST_SITES} does not list`);
    }
  }
  return offences;
}

function scanned(name, path, root) {
  if (EXCLUDED.has(name) || EXCLUDED.has(relative(root, path))) return false;
  if (name.startsWith(".")) return name === ".github" || name === ".env.example" || !SECRET_ENV.test(name) && !statSync(path).isDirectory();
  return true;
}

function filesUnder(dir, root) {
  const found = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (!scanned(name, path, root)) continue;
    if (statSync(path).isDirectory()) found.push(...filesUnder(path, root));
    else if (!BINARY.test(name)) found.push(relative(root, path));
  }
  return found;
}

export function scannedPaths(root = ROOT) {
  const compose = readFileSync(join(root, E2E_COMPOSE), "utf8");
  return [...new Set([...mountedFiles(compose), ...filesUnder(root, root)])];
}

export function collect(root = ROOT) {
  const texts = new Map(
    scannedPaths(root).map((path) => [
      path,
      readFileSync(join(root, path), "utf8"),
    ]),
  );
  return { offences: offencesIn(texts), files: texts.size };
}

const invokedDirectly = process.argv[1]?.endsWith("check-test-sites.mjs");
if (invokedDirectly) {
  const { offences, files } = collect();
  if (offences.length > 0) {
    console.error("check-test-sites: FAILED");
    for (const offence of offences) console.error(`  ${offence}`);
    process.exit(1);
  }
  console.log(`check-test-sites: ${files} files outside docs and the backup name only QA sites (0 violations)`);
}
