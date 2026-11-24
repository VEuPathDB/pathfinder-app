import { test } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";

import {
  cassetteId,
  signTestToken,
  stalenessLines,
} from "../e2e/fixtures/wire-recordings.ts";

test("a cassette id is stable, slugged and ends in a short hash", () => {
  const id = cassetteId("turns@plasmodb", "uat/strategy-standard.spec.ts", [
    "Strategy standard",
    "S1 - One search: 3 genes!",
  ]);
  assert.match(
    id,
    /^turns@plasmodb\/uat\/strategy-standard\.spec\.ts\/strategy-standard-s1-one-search-3-genes-[0-9a-f]{8}$/,
  );
  assert.equal(
    id,
    cassetteId("turns@plasmodb", "uat/strategy-standard.spec.ts", [
      "Strategy standard",
      "S1 - One search: 3 genes!",
    ]),
  );
  assert.notEqual(
    id,
    cassetteId("turns@vectorbase", "uat/strategy-standard.spec.ts", [
      "Strategy standard",
      "S1 - One search: 3 genes!",
    ]),
  );
});

test("a cassette id never names a parent directory", () => {
  const id = cassetteId("feature@plasmodb", "../x.spec.ts", ["..", "."]);
  assert.ok(!id.split("/").some((segment) => segment === ".." || segment === "."), id);
  assert.match(id, /^[A-Za-z0-9@._-]+(\/[A-Za-z0-9@._-]+)*$/);
});

test("a test token is an ES512 JWT the stack key verifies", () => {
  const { privateKey, publicKey } = generateKeyPairSync("ec", { namedCurve: "P-521" });
  const jwk = { ...privateKey.export({ format: "jwk" }), kid: "wire", alg: "ES512" };
  const token = signTestToken(jwk, "feature@plasmodb/a.spec.ts/one-1", 1_800_000_000);

  const [header, payload, signature] = token.split(".");
  const signed = verify(
    "sha512",
    Buffer.from(`${header}.${payload}`),
    { key: publicKey, dsaEncoding: "ieee-p1363" },
    Buffer.from(signature, "base64url"),
  );
  assert.equal(signed, true);
  assert.deepEqual(JSON.parse(Buffer.from(header, "base64url").toString()), {
    alg: "ES512",
    typ: "JWT",
    kid: "wire",
  });
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString());
  assert.equal(claims.e2e_cassette, "feature@plasmodb/a.spec.ts/one-1");
  assert.equal(claims.is_guest, false);
  assert.equal(claims.iat, 1_800_000_000);
  assert.equal(claims.exp, 1_800_000_000 + 2 * 86_400);
  assert.match(claims.sub, /^e2e-[0-9a-f]{12}$/);
});

test("the staleness lines name the age and every build", () => {
  const lines = stalenessLines(
    {
      cassettes: 205,
      hosts: {
        "qa.plasmodb.org": {
          builds: { 69: 200, 70: 5 },
          oldest: "2026-11-02T10:00:00Z",
          newest: "2026-11-19T10:00:00Z",
        },
        "qa.vectorbase.org": {
          builds: { 69: 3 },
          oldest: "2026-11-03T10:00:00Z",
          newest: "2026-11-03T10:00:00Z",
        },
      },
      libraries: {},
    },
    new Date("2026-11-23T10:00:00Z"),
  );
  assert.deepEqual(lines, [
    "WDK replay: 205 recordings, 2026-11-02 to 2026-11-19 (21 days old).",
    "  qa.plasmodb.org build 69 (200), 70 (5); qa.vectorbase.org build 69",
  ]);
});

test("an empty set says there is nothing to replay", () => {
  assert.deepEqual(
    stalenessLines({ cassettes: 0, hosts: {}, libraries: {} }, new Date()),
    ["WDK replay: no recordings yet."],
  );
});
