import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

import {
  CAP_BYTES,
  fenceOffences,
  recordingOffences,
  sizeOffences,
} from "./check-wire-recordings.mjs";

const JWT = ["eyJhbGciOiJFUzUxMiJ9", "eyJzdWIiOiIxIn0", "c2ln"].join(".");

function tree(files) {
  const root = mkdtempSync(join(tmpdir(), "wire-"));
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(join(root, name, ".."), { recursive: true });
    writeFileSync(join(root, name), name.endsWith(".gz") ? gzipSync(content) : content);
  }
  return root;
}

const CLEAN = {
  "manifest.json": '{"cassettes": 1}\n',
  "stack.jsonl": '{"cassette": "stack"}\n',
  "cassettes/feature@plasmodb/a.spec.ts/one-1.jsonl": '{"path": "/users/900000001/steps"}\n',
  "bodies/ab/abcd.gz": '{"email": "e2e-account@strategist.test"}',
};

test("a clean tree passes", () => {
  assert.deepEqual(recordingOffences(tree(CLEAN), {}), []);
  assert.deepEqual(sizeOffences(tree(CLEAN)), []);
});

test("a token inside a gzipped body fails naming the file", () => {
  const root = tree({ ...CLEAN, "bodies/cd/cdef.gz": `{"t": "${JWT}"}` });
  assert.deepEqual(recordingOffences(root, {}), ["bodies/cd/cdef.gz: a token"]);
});

test("the word password fails", () => {
  const root = tree({ ...CLEAN, "stack.jsonl": '{"body": "Password=x"}\n' });
  assert.deepEqual(recordingOffences(root, {}), ["stack.jsonl: the word password"]);
});

test("the account email and user id fail when the shell names them", () => {
  const root = tree({
    ...CLEAN,
    "stack.jsonl": '{"to": "Researcher%40Example.org", "path": "/users/376543210/steps"}\n',
  });
  const account = { email: "researcher@example.org", userId: "376543210" };
  assert.deepEqual(recordingOffences(root, account), [
    "stack.jsonl: the account email",
    "stack.jsonl: the account user id",
  ]);
});

test("a tree over the cap fails naming its size", () => {
  const root = tree(CLEAN);
  writeFileSync(join(root, "bodies/big.gz"), Buffer.alloc(CAP_BYTES + 1));
  const [offence] = sizeOffences(root);
  assert.match(offence, /^the recordings hold 40\.0 MB, over the 40 MB cap$/);
});

const SITES = `sites:
  plasmodb:
    base_url: https://qa.plasmodb.org/plasmo.qa/service
  toxodb:
    base_url: https://qa.toxodb.org/toxo.qa/service
`;

test("every QA host of e2e-sites.yaml is fenced", () => {
  const overlay = `x-fence: &fence
  - "qa.plasmodb.org:127.0.0.1"
  - "api.openai.com:127.0.0.1"
`;
  assert.deepEqual(fenceOffences(SITES, overlay), [
    "docker-compose.e2e-wire.yml fences no qa.toxodb.org",
  ]);
  assert.deepEqual(fenceOffences(SITES, `${overlay}  - "qa.toxodb.org:127.0.0.1"\n`), []);
});
