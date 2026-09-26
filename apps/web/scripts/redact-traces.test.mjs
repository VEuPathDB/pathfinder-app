import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  REDACTED,
  accountSecrets,
  readZip,
  redactDirectory,
  redactFile,
  writeZip,
} from "./redact-traces.mjs";

const TOKEN =
  "eyJhbGciOiJFUzUxMiJ9.eyJzdWIiOiJmYWtlIiwiaXNfZ3Vlc3QiOmZhbHNlfQ.FAKEsignature_-0";
const MINTED = "eyJhbGciOiJFUzUxMiJ9.eyJzdWIiOiJtaW50ZWQifQ.MINTEDsignature";
const EMAIL = "someone@example.org";
const PASSWORD = 'pa"ss w0rd&x';
const SECRETS = accountSecrets({ WDK_TEST_EMAIL: EMAIL, WDK_TEST_PASSWORD: PASSWORD });

/** Lines in the shapes a Playwright 1.62 trace records them. */
const NETWORK_LINE =
  `{"type":"resource-snapshot","snapshot":{"request":{"cookies":[{"name":"Authorization","value":"${TOKEN}"}],` +
  `"headers":[{"name":"Cookie","value":"Authorization=${TOKEN}"}]},"response":{"headers":` +
  `[{"name":"Set-Cookie","value":"Authorization=${MINTED}; Path=/; HttpOnly"}]}}}\n`;
const FILL_LINE = `{"type":"before","params":{"selector":"internal:attr=[placeholder=\\"Password\\"i]","value":${JSON.stringify(PASSWORD)}}}\n`;
const FETCH_LINE = `{"type":"before","params":{"jsonData":${JSON.stringify(JSON.stringify({ password: PASSWORD }))}}}\n`;
const SNAPSHOT_LINE = `{"html":["INPUT",{"__playwright_value_":${JSON.stringify(PASSWORD)},"type":"password"}]}\n`;
const LOGIN_BODY = JSON.stringify({ email: EMAIL, password: PASSWORD });
const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46]);

function traceZip() {
  return writeZip([
    { name: "trace.network", data: Buffer.from(NETWORK_LINE) },
    { name: "trace.trace", data: Buffer.from(FILL_LINE + FETCH_LINE + SNAPSHOT_LINE) },
    { name: "resources/a73089dc.json", data: Buffer.from(LOGIN_BODY) },
    { name: "resources/page@1.jpeg", data: JPEG },
  ]);
}

function entryText(zip, name) {
  const entry = readZip(zip).find((e) => e.name === name);
  assert.ok(entry, `no entry ${name}`);
  return entry.data.toString("utf8");
}

test("every account token in a trace's network log is blanked", () => {
  const redacted = redactFile("trace.zip", traceZip(), SECRETS);
  assert.equal(
    entryText(redacted, "trace.network"),
    `{"type":"resource-snapshot","snapshot":{"request":{"cookies":[{"name":"Authorization","value":"${REDACTED}"}],` +
      `"headers":[{"name":"Cookie","value":"Authorization=${REDACTED}"}]},"response":{"headers":` +
      `[{"name":"Set-Cookie","value":"Authorization=${REDACTED}; Path=/; HttpOnly"}]}}}\n`,
  );
});

test("the password leaves the fill action, the fetch body, the DOM snapshot and the request body", () => {
  const redacted = redactFile("trace.zip", traceZip(), SECRETS);
  assert.equal(
    entryText(redacted, "trace.trace"),
    `{"type":"before","params":{"selector":"internal:attr=[placeholder=\\"Password\\"i]","value":"${REDACTED}"}}\n` +
      `{"type":"before","params":{"jsonData":"{\\"password\\":\\"${REDACTED}\\"}"}}\n` +
      `{"html":["INPUT",{"__playwright_value_":"${REDACTED}","type":"password"}]}\n`,
  );
  assert.equal(
    entryText(redacted, "resources/a73089dc.json"),
    `{"email":"${REDACTED}","password":"${REDACTED}"}`,
  );
});

test("an image entry keeps its bytes", () => {
  const redacted = redactFile("trace.zip", traceZip(), SECRETS);
  const image = readZip(redacted).find((e) => e.name === "resources/page@1.jpeg");
  assert.deepEqual(image?.data, JPEG);
});

test("a blob report's nested trace and its report lines are redacted on disk", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "redact-traces-"));
  try {
    const blob = writeZip([
      {
        name: "report.jsonl",
        data: Buffer.from(`{"stdout":"cookie: Authorization=${TOKEN}"}\n`),
      },
      { name: "resources/0123abcd.zip", data: traceZip() },
    ]);
    const blobPath = path.join(dir, "report-1.zip");
    writeFileSync(blobPath, blob);

    assert.deepEqual(redactDirectory(dir, SECRETS), [blobPath]);

    const onDisk = readFileSync(blobPath);
    assert.deepEqual(
      readZip(onDisk).map((e) => e.name),
      ["report.jsonl", "resources/0123abcd.zip"],
    );
    assert.equal(
      entryText(onDisk, "report.jsonl"),
      `{"stdout":"cookie: Authorization=${REDACTED}"}\n`,
    );
    const nested = readZip(onDisk).find((e) => e.name === "resources/0123abcd.zip");
    assert.equal(
      entryText(nested.data, "resources/a73089dc.json"),
      `{"email":"${REDACTED}","password":"${REDACTED}"}`,
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a report with nothing to redact is left byte for byte", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "redact-traces-"));
  try {
    const clean = writeZip([
      { name: "report.jsonl", data: Buffer.from('{"ok":true}\n') },
    ]);
    mkdirSync(path.join(dir, "nested"));
    const cleanPath = path.join(dir, "nested", "report-2.zip");
    writeFileSync(cleanPath, clean);

    assert.deepEqual(redactDirectory(dir, SECRETS), []);
    assert.deepEqual(readFileSync(cleanPath), clean);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a directory that does not exist has nothing to redact", () => {
  assert.deepEqual(
    redactDirectory(path.join(tmpdir(), "no-such-blob-report"), SECRETS),
    [],
  );
});

test("an unset credential names no secret, and each set one names its encodings", () => {
  assert.deepEqual(accountSecrets({ WDK_TEST_EMAIL: "", WDK_TEST_PASSWORD: "" }), []);
  assert.deepEqual(accountSecrets({ WDK_TEST_PASSWORD: 'a"b c' }), [
    'a"b c',
    'a\\"b c',
    'a\\\\\\"b c',
    'a\\\\\\\\\\\\\\"b c',
    "a%22b%20c",
  ]);
});

test("a zip that uses an unknown compression method is refused", () => {
  const zip = writeZip([{ name: "trace.trace", data: Buffer.from("x") }]);
  // Method field of the one central directory entry, 10 bytes into its header.
  const central = zip.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]));
  zip.writeUInt16LE(12, central + 10);
  assert.throws(() => readZip(zip), /compression method 12/);
});
