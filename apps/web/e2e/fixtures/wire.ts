import * as fs from "node:fs";
import * as path from "node:path";

import { request } from "@playwright/test";

import { type SigningJwk, type WireManifest, signTestToken } from "./wire-recordings";

export type WireMode = "replay" | "record";

export type WireOutcome = {
  report: string;
  error?: string;
};

const WIRE_URL = process.env["WIRE_URL"] ?? "http://127.0.0.1:8181";
const SIGNING_KEY = "WIRE_SIGNING_KEY";
const MANIFEST = path.resolve("e2e/wire/manifest.json");

export function wireMode(): WireMode {
  const mode = process.env["E2E_WIRE"] ?? "replay";
  if (mode !== "replay" && mode !== "record") {
    throw new Error(`E2E_WIRE is ${mode}; it is replay or record`);
  }
  return mode;
}

async function wire(
  method: "GET" | "POST",
  route: string,
  body?: object,
): Promise<unknown> {
  const client = await request.newContext();
  try {
    const response = await client.fetch(`${WIRE_URL}/__wire/${route}`, {
      method,
      ...(body === undefined ? {} : { data: body }),
    });
    const answered = (await response.json()) as Partial<WireOutcome>;
    if (!response.ok()) {
      throw new Error(
        `wdk-wire ${route} answered ${response.status()}: ${answered.error ?? ""}`,
      );
    }
    return answered;
  } finally {
    await client.dispose();
  }
}

export async function wireServes(mode: WireMode): Promise<void> {
  const health = (await wire("GET", "health")) as { mode: string };
  if (health.mode !== mode) {
    throw new Error(`wdk-wire runs in ${health.mode} mode, and E2E_WIRE is ${mode}`);
  }
}

export async function shareSigningKey(): Promise<void> {
  process.env[SIGNING_KEY] = JSON.stringify(await wire("GET", "signing-key"));
}

export function testToken(cassette: string): string {
  const key = process.env[SIGNING_KEY] ?? "";
  if (key === "") throw new Error("global setup read no wdk-wire signing key");
  return signTestToken(
    JSON.parse(key) as SigningJwk,
    cassette,
    Math.floor(Date.now() / 1000),
  );
}

export async function beginTest(cassette: string): Promise<void> {
  await wire("POST", "begin", { cassette });
}

function reportOf(answered: unknown): string {
  return (answered as Partial<WireOutcome>).report ?? "";
}

export async function endTest(cassette: string, keep: boolean): Promise<string> {
  return reportOf(await wire("POST", "end", { cassette, keep }));
}

export async function finishRun(): Promise<string> {
  return reportOf(await wire("POST", "finish"));
}

export function readManifest(): WireManifest {
  return JSON.parse(fs.readFileSync(MANIFEST, "utf8")) as WireManifest;
}

let current = "";

export function holdTestToken(token: string): void {
  current = token;
}

export function heldTestToken(): string {
  return current;
}
