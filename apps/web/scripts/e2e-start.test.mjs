import { test } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PLAYWRIGHT = path.join(WEB, "node_modules", ".bin", "playwright");
const SPEC = "e2e/feature/base-path.spec.ts";

function closedPort() {
  return new Promise((resolve) => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function fakeWire(health) {
  return new Promise((resolve) => {
    const server = createServer((request, response) => {
      const [status, body] =
        request.url === "/__wire/health" ? health : [404, { error: "no route" }];
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function runSuite(wireUrl, extraEnv = {}) {
  return closedPort().then(
    (appPort) =>
      new Promise((resolve) => {
        const { E2E_WIRE: _unset, ...inherited } = process.env;
        const env = {
          ...inherited,
          WIRE_URL: wireUrl,
          PLAYWRIGHT_BASE_URL: `http://127.0.0.1:${appPort}`,
          ...extraEnv,
        };
        execFile(
          PLAYWRIGHT,
          ["test", "--reporter=line", "--project=feature@plasmodb", SPEC],
          { cwd: WEB, env, timeout: 120_000 },
          (error, stdout, stderr) =>
            resolve({ code: error?.code ?? 0, output: `${stdout}${stderr}` }),
        );
      }),
  );
}

async function refusalFrom(health, extraEnv) {
  const server = await fakeWire(health);
  try {
    const { port } = server.address();
    return await runSuite(`http://127.0.0.1:${port}`, extraEnv);
  } finally {
    server.close();
  }
}

test("the package script runs the suite only on replayed recordings", () => {
  const manifest = JSON.parse(readFileSync(path.join(WEB, "package.json"), "utf8"));
  assert.equal(manifest.scripts["test:e2e"], "../../scripts/e2e-wire.sh replay");
  const others = Object.entries(manifest.scripts).filter(
    ([name, command]) => name !== "test:e2e" && /\bplaywright\b/.test(command),
  );
  assert.deepEqual(others, []);
});

test("the suite refuses to start when no wdk-wire answers", async () => {
  const { code, output } = await runSuite(`http://127.0.0.1:${await closedPort()}`);
  assert.notEqual(code, 0);
  assert.match(output, /no wdk-wire answers at http:\/\/127\.0\.0\.1:\d+/);
  assert.match(output, /scripts\/e2e-wire\.sh replay/);
});

test("the suite refuses a wdk-wire that records when it was asked to replay", async () => {
  const { code, output } = await refusalFrom([200, { mode: "record" }]);
  assert.notEqual(code, 0);
  assert.match(output, /wdk-wire runs in record mode, and E2E_WIRE is replay/);
});

test("the suite refuses to record through a wdk-wire that replays", async () => {
  const { code, output } = await refusalFrom([200, { mode: "replay" }], {
    E2E_WIRE: "record",
  });
  assert.notEqual(code, 0);
  assert.match(output, /wdk-wire runs in replay mode, and E2E_WIRE is record/);
});

test("the suite refuses a health route that is not wdk-wire's", async () => {
  const { code, output } = await refusalFrom([404, { error: "not here" }]);
  assert.notEqual(code, 0);
  assert.match(output, /no wdk-wire answers at http:\/\/127\.0\.0\.1:\d+/);
});
