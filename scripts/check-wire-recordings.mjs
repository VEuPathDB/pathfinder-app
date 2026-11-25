#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export const WIRE_DIR = "apps/web/e2e/wire";
export const OVERLAY = "docker-compose.e2e.yml";
export const TEST_SITES = "e2e-sites.yaml";
export const CAP_BYTES = 40 * 1024 * 1024;
export const ALWAYS_FENCED = ["api.openai.com"];

const TOKEN = /eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\./;
const PASSWORD = /password/i;
const MEGABYTE = 1024 * 1024;

function files(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

function escaped(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function emailPattern(email) {
  const [local, domain] = email.split("@");
  return new RegExp(`${escaped(local)}(?:@|%40|\\\\u0040|&#64;|&#x40;)${escaped(domain)}`, "i");
}

function readable(path) {
  const raw = readFileSync(path);
  return (path.endsWith(".gz") ? gunzipSync(raw) : raw).toString("utf8");
}

export function recordingOffences(root, { email = "", userId = "" }) {
  const checks = [
    ["a token", TOKEN],
    ["the word password", PASSWORD],
    ...(email ? [["the account email", emailPattern(email)]] : []),
    ...(userId ? [["the account user id", new RegExp(`(?<!\\d)${escaped(userId)}(?!\\d)`)]] : []),
  ];
  return files(root).flatMap((path) => {
    const text = readable(path);
    const name = relative(root, path);
    return checks.filter(([, pattern]) => pattern.test(text)).map(([what]) => `${name}: ${what}`);
  });
}

export function sizeOffences(root) {
  const bytes = files(root).reduce((total, path) => total + statSync(path).size, 0);
  if (bytes <= CAP_BYTES) return [];
  return [`the recordings hold ${(bytes / MEGABYTE).toFixed(1)} MB, over the 40 MB cap`];
}

export function fenceOffences(sitesYaml, overlayYaml) {
  const sites = [...sitesYaml.matchAll(/base_url:\s*https:\/\/([^/\s]+)/g)].map((m) => m[1]);
  const fenced = new Set([...overlayYaml.matchAll(/"([^":\s]+):127\.0\.0\.1"/g)].map((m) => m[1]));
  return [...new Set([...sites, ...ALWAYS_FENCED])]
    .filter((host) => !fenced.has(host))
    .map((host) => `${OVERLAY} fences no ${host}`);
}

const invokedDirectly = process.argv[1]?.endsWith("check-wire-recordings.mjs");
if (invokedDirectly) {
  const wire = join(ROOT, WIRE_DIR);
  const account = {
    email: process.env.WDK_TEST_EMAIL ?? "",
    userId: process.env.WIRE_REAL_USER_ID ?? "",
  };
  const offences = [
    ...recordingOffences(wire, account),
    ...sizeOffences(wire),
    ...fenceOffences(
      readFileSync(join(ROOT, TEST_SITES), "utf8"),
      readFileSync(join(ROOT, OVERLAY), "utf8"),
    ),
  ];
  if (offences.length > 0) {
    console.error(`check-wire-recordings: FAILED\n  ${offences.join("\n  ")}`);
    process.exit(1);
  }
  const held = files(wire).length;
  console.log(`check-wire-recordings: ${held} files, redacted and under the cap`);
}
