import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

import {
  E2E_COMPOSE,
  QA_SITES,
  TEST_SITES,
  WORKFLOW_SITES,
  collect,
  composeServices,
  mountedFiles,
  offencesIn,
  productionHosts,
  scannedPaths,
  siteEntries,
} from "./check-test-sites.mjs";

const host = (...labels) => [...labels, "org"].join(".");

const QA = `sites:
  veupathdb:
    name: VEuPathDB
    base_url: https://qa.veupathdb.org/veupathdb.qa/service
    project_id: UniDB
    is_portal: true

  plasmodb:
    name: PlasmoDB
    base_url: https://qa.plasmodb.org/plasmo.qa/service
    project_id: PlasmoDB
    is_portal: false

  toxodb:
    name: ToxoDB
    base_url: https://qa.toxodb.org/toxo.qa/service
    project_id: ToxoDB
    is_portal: false

default_site: veupathdb
`;

const LIST = `# A subset of the QA sites.
sites:
  veupathdb:
    name: VEuPathDB
    base_url: https://qa.veupathdb.org/veupathdb.qa/service
    project_id: UniDB
    is_portal: true
  plasmodb:
    name: PlasmoDB
    base_url: https://qa.plasmodb.org/plasmo.qa/service
    project_id: PlasmoDB
    is_portal: false

default_site: veupathdb
`;

const COMPOSE = (workerConfig = "/app/e2e-sites.yaml") => `services:
  api:
    environment:
      API_ENV: test
      VEUPATHDB_SITES_CONFIG: /app/e2e-sites.yaml
    volumes:
      - ./e2e-sites.yaml:/app/e2e-sites.yaml:ro

  worker:
    environment:
      VEUPATHDB_SITES_CONFIG: ${workerConfig}
    volumes:
      - ./e2e-sites.yaml:/app/e2e-sites.yaml:ro

  db:
    ports: !override
      - "5433:5432"
`;

const NIGHTLY = (sites = WORKFLOW_SITES) => `name: WDK nightly

env:
  VEUPATHDB_SITES_CONFIG: ${sites}

jobs:
  live-lane:
    steps:
      - name: Run the live lane
        env:
          WDK_TEST_EMAIL: \${{ secrets.WDK_TEST_EMAIL }}
        run: uv run pytest src/pathfinder/tests -m live_wdk -q
`;

const CI = (sites = "plasmodb", extra = "") => `name: CI

env:
  E2E_SHARDS: 16
  E2E_SITES: ${sites}
${extra}
jobs:
  e2e:
    steps:
      - env:
          WDK_TEST_EMAIL: \${{ secrets.WDK_TEST_EMAIL }}
        run: yarn playwright test
`;

const files = (overrides = {}) =>
  new Map(
    Object.entries({
      [QA_SITES]: QA,
      [TEST_SITES]: LIST,
      [E2E_COMPOSE]: COMPOSE(),
      ".github/workflows/wdk-nightly.yml": NIGHTLY(),
      ".github/workflows/ci.yml": CI(),
      "apps/web/playwright.config.ts": "export default {};\n",
      ...overrides,
    }),
  );

test("the shipped test configuration names only QA sites", () => {
  assert.deepEqual(collect().offences, []);
});

test("a conformant set produces no offences", () => {
  assert.deepEqual(offencesIn(files()), []);
});

test("a bare site host is production", () => {
  assert.deepEqual(productionHosts(`url: https://${host("plasmodb")}/plasmo/service`), [
    { line: 1, host: host("plasmodb") },
  ]);
});

test("a beta, www, sign-in or numbered server host is production", () => {
  assert.deepEqual(
    productionHosts(
      `a https://${host("beta", "toxodb")}/x\nb ${host("www", "VectorBase")}\nc ${host("w1", "fungidb")}\nd ${host("auth", "veupathdb")}`,
    ).map(
      (found) => found.host,
    ),
    [host("beta", "toxodb"), host("www", "vectorbase"), host("w1", "fungidb"), host("auth", "veupathdb")],
  );
});

test("a mailbox is not a host, and a credential in a URL does not hide one", () => {
  assert.deepEqual(productionHosts(`write to help@${host("veupathdb")}`), []);
  assert.deepEqual(
    productionHosts(`https://ada:secret@${host("plasmodb")}/x`).map((found) => found.host),
    [host("plasmodb")],
  );
});

test("every file outside docs, the backup and local outputs is scanned, and no secret env file is read", () => {
  const paths = scannedPaths();

  assert.ok(paths.includes("apps/api/src/pathfinder/tests/unit/platform/test_stage_sites.py"));
  assert.ok(paths.includes("apps/api/src/pathfinder/data/seeds/hostdb.json"));
  assert.ok(paths.includes("apps/api/src/pathfinder/ai/models/mock/organism_params.json"));
  assert.ok(paths.includes("apps/web/src/features/sidebar/wdkStrategyRef.ts"));
  assert.ok(paths.includes(".github/workflows/ci.yml"));
  assert.ok(paths.includes(".env.example"));
  assert.ok(paths.includes("README.md"));
  assert.deepEqual(
    paths.filter((path) => /^(docs|thesis|fixtures-production-backup-2026-10-09)\//.test(path) || /(^|\/)\.env(\.(dev|test))?$/.test(path)),
    [],
  );
});

test("a qa or q2 host is not production", () => {
  assert.deepEqual(
    productionHosts("https://qa.plasmodb.org/plasmo.qa https://q2.toxodb.org/toxo.qa"),
    [],
  );
});

test("a production host in any scanned file is named with its line", () => {
  const offences = offencesIn(
    files({ "apps/web/playwright.config.ts": `const a = 1;\nconst b = 'https://${host("veupathdb")}';\n` }),
  );

  assert.deepEqual(offences, [
    `apps/web/playwright.config.ts:2: names the production host ${host("veupathdb")}`,
  ]);
});

test("the site list is read by id and field", () => {
  const entries = siteEntries(LIST);

  assert.deepEqual([...entries.keys()], ["veupathdb", "plasmodb"]);
  assert.equal(entries.get("plasmodb").get("base_url"), "https://qa.plasmodb.org/plasmo.qa/service");
});

test("a test site whose entry differs from the QA file is refused", () => {
  const drifted = LIST.replace("project_id: UniDB", "project_id: EuPathDB");

  assert.deepEqual(offencesIn(files({ [TEST_SITES]: drifted })), [
    `${TEST_SITES}: veupathdb.project_id is EuPathDB, and ${QA_SITES} says UniDB`,
  ]);
});

test("a test site the QA file does not hold is refused", () => {
  const extra = LIST.replace(
    "\ndefault_site",
    "  giardiadb:\n    name: GiardiaDB\n    base_url: https://qa.giardiadb.org/giardiadb.qa/service\n\ndefault_site",
  );

  assert.deepEqual(offencesIn(files({ [TEST_SITES]: extra })), [
    `${TEST_SITES}: giardiadb is not in ${QA_SITES}`,
  ]);
});

test("an empty test site list is refused", () => {
  assert.deepEqual(offencesIn(files({ [TEST_SITES]: "default_site: veupathdb\n" })), [
    `${TEST_SITES}: lists no site`,
    ".github/workflows/ci.yml: E2E_SITES names plasmodb, which e2e-sites.yaml does not list",
  ]);
});

test("the compose services and their mounts are read", () => {
  const services = composeServices(COMPOSE());

  assert.equal(services.get("worker").sitesConfig, "/app/e2e-sites.yaml");
  assert.equal(services.get("api").mounts.get("/app/e2e-sites.yaml"), "e2e-sites.yaml");
  assert.deepEqual(mountedFiles(COMPOSE()), ["e2e-sites.yaml"]);
});

test("a compose service that reads a file the test list does not mount is refused", () => {
  assert.deepEqual(offencesIn(files({ [E2E_COMPOSE]: COMPOSE("/app/config/sites/dev.yml") })), [
    `${E2E_COMPOSE}: worker reads /app/config/sites/dev.yml, which is not a mount of ${TEST_SITES}`,
  ]);
});

test("a compose service that sets no site list is refused", () => {
  const unset = COMPOSE().replace("      VEUPATHDB_SITES_CONFIG: /app/e2e-sites.yaml\n    volumes", "    volumes");

  assert.deepEqual(offencesIn(files({ [E2E_COMPOSE]: unset })), [
    `${E2E_COMPOSE}: api does not set VEUPATHDB_SITES_CONFIG`,
  ]);
});

test("a live workflow with another site list is refused", () => {
  assert.deepEqual(
    offencesIn(files({ ".github/workflows/wdk-nightly.yml": NIGHTLY("/elsewhere/sites.yaml") })),
    [
      `.github/workflows/wdk-nightly.yml: reaches a live site, and its top-level env sets VEUPATHDB_SITES_CONFIG to /elsewhere/sites.yaml, not ${WORKFLOW_SITES}`,
    ],
  );
});

test("a live workflow with no site list is refused", () => {
  const unset = NIGHTLY().replace(/env:\n {2}VEUPATHDB_SITES_CONFIG: .*\n\n/, "");

  assert.deepEqual(offencesIn(files({ ".github/workflows/wdk-nightly.yml": unset })), [
    `.github/workflows/wdk-nightly.yml: reaches a live site, and its top-level env sets VEUPATHDB_SITES_CONFIG to nothing, not ${WORKFLOW_SITES}`,
  ]);
});

test("a workflow that serves the MCP endpoint is a live workflow", () => {
  const served = "name: MCP\njobs:\n  a:\n    steps:\n      - run: uv run python -m veupathdb_mcp &\n";

  assert.deepEqual(offencesIn(files({ ".github/workflows/mcp-nightly.yml": served })), [
    `.github/workflows/mcp-nightly.yml: reaches a live site, and its top-level env sets VEUPATHDB_SITES_CONFIG to nothing, not ${WORKFLOW_SITES}`,
  ]);
});

test("a workflow with no live lane needs no site list", () => {
  assert.deepEqual(
    offencesIn(files({ ".github/workflows/security.yml": "name: Security\njobs: {}\n" })),
    [],
  );
});

test("an E2E site the test list does not hold is refused", () => {
  assert.deepEqual(offencesIn(files({ ".github/workflows/ci.yml": CI("plasmodb,vectorbase") })), [
    ".github/workflows/ci.yml: E2E_SITES names vectorbase, which e2e-sites.yaml does not list",
  ]);
});

test("the command line passes on the shipped tree", () => {
  const run = spawnSync(process.execPath, ["scripts/check-test-sites.mjs"], { encoding: "utf8" });

  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /^check-test-sites: \d+ files outside docs and the backup name only QA sites \(0 violations\)\n$/);
});
