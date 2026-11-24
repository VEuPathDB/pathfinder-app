import { createHash, createPrivateKey, sign } from "node:crypto";

export type HostRecordings = {
  builds: Record<string, number>;
  oldest: string;
  newest: string;
};

export type SigningJwk = JsonWebKey & { kid?: string };

export type WireManifest = {
  cassettes: number;
  hosts: Record<string, HostRecordings>;
  libraries: Record<string, string>;
};

const HASH_LENGTH = 8;
const SUBJECT_LENGTH = 12;
const TITLE_LENGTH = 80;
const TOKEN_DAYS = 2;
const DAY_SECONDS = 86_400;
const DAY_MS = DAY_SECONDS * 1000;

function digest(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9@._-]+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .replace(/-{2,}/g, "-");
}

function pathSegment(text: string): string {
  const slugged = slug(text);
  return slugged === "" ? "_" : slugged;
}

export function cassetteId(
  project: string,
  specFile: string,
  titles: string[],
): string {
  const file = specFile.split("/").map(pathSegment).join("/");
  const title = slug(titles.join(" "))
    .slice(0, TITLE_LENGTH)
    .replace(/[-.]+$/, "");
  const hash = digest([project, specFile, ...titles].join("\n")).slice(0, HASH_LENGTH);
  return `${pathSegment(project)}/${file}/${title === "" ? "" : `${title}-`}${hash}`;
}

function base64url(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

export function signTestToken(
  jwk: SigningJwk,
  cassette: string,
  nowSeconds: number,
): string {
  const header = base64url({ alg: "ES512", typ: "JWT", kid: jwk.kid });
  const payload = base64url({
    sub: `e2e-${digest(cassette).slice(0, SUBJECT_LENGTH)}`,
    is_guest: false,
    iat: nowSeconds,
    exp: nowSeconds + TOKEN_DAYS * DAY_SECONDS,
    e2e_cassette: cassette,
  });
  const key = createPrivateKey({ key: jwk, format: "jwk" });
  const signature = sign("sha512", Buffer.from(`${header}.${payload}`), {
    key,
    dsaEncoding: "ieee-p1363",
  });
  return `${header}.${payload}.${signature.toString("base64url")}`;
}

function day(iso: string): string {
  return iso.slice(0, 10);
}

function builds(held: HostRecordings): string {
  const entries = Object.entries(held.builds);
  if (entries.length === 1) return `build ${entries[0]?.[0] ?? ""}`;
  return `build ${entries.map(([build, tests]) => `${build} (${tests})`).join(", ")}`;
}

export function stalenessLines(manifest: WireManifest, now: Date): string[] {
  const hosts = Object.entries(manifest.hosts).sort(([a], [b]) => a.localeCompare(b));
  if (manifest.cassettes === 0 || hosts.length === 0)
    return ["WDK replay: no recordings yet."];
  const oldest = hosts.map(([, held]) => held.oldest).sort()[0] ?? "";
  const newest =
    hosts
      .map(([, held]) => held.newest)
      .sort()
      .at(-1) ?? "";
  const age = Math.floor((now.getTime() - new Date(oldest).getTime()) / DAY_MS);
  return [
    `WDK replay: ${manifest.cassettes} recordings, ${day(oldest)} to ${day(newest)} (${age} days old).`,
    `  ${hosts.map(([host, held]) => `${host} ${builds(held)}`).join("; ")}`,
  ];
}
