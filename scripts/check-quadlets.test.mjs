import { test } from "node:test";
import assert from "node:assert/strict";

import { collect, offencesIn, parseUnit, TAG_PLACEHOLDER } from "./check-quadlets.mjs";

const unit = (name, body) => [name, body];

const API = `[Unit]
Description=Pathfinder API server

[Container]
ContainerName=pathfinder-api
Image=ghcr.io/veupathdb/pathfinder-api:${TAG_PLACEHOLDER}
Network=pathfinder.network
PublishPort=127.0.0.1:8010:8000
EnvironmentFile=%h/.config/pathfinder/.env
Environment=PATHFINDER_WDK_MCP_URL=http://pathfinder-wdk-mcp:8100/mcp
Environment=PATHFINDER_RESEARCH_MCP_URL=http://pathfinder-research-mcp:8110/mcp
Environment=FORWARDED_ALLOW_IPS=*

[Install]
WantedBy=default.target
`;

const WORKER = `[Container]
ContainerName=pathfinder-worker
Image=ghcr.io/veupathdb/pathfinder-api:${TAG_PLACEHOLDER}
Network=pathfinder.network
EnvironmentFile=%h/.config/pathfinder/.env
Environment=PATHFINDER_WDK_MCP_URL=http://pathfinder-wdk-mcp:8100/mcp
Environment=PATHFINDER_RESEARCH_MCP_URL=http://pathfinder-research-mcp:8110/mcp

[Install]
WantedBy=default.target
`;

const WEB = `[Container]
ContainerName=pathfinder-web
Image=ghcr.io/veupathdb/pathfinder-web:${TAG_PLACEHOLDER}
Network=pathfinder.network
PublishPort=127.0.0.1:3010:3000

[Install]
WantedBy=default.target
`;

const WDK_MCP = `[Container]
ContainerName=pathfinder-wdk-mcp
Image=ghcr.io/veupathdb/pathfinder-wdk-mcp:${TAG_PLACEHOLDER}
Network=pathfinder.network
EnvironmentFile=%h/.config/pathfinder/.env

[Install]
WantedBy=default.target
`;

const RESEARCH_MCP = `[Container]
ContainerName=pathfinder-research-mcp
Image=ghcr.io/veupathdb/pathfinder-research-mcp:${TAG_PLACEHOLDER}
Network=pathfinder.network
EnvironmentFile=%h/.config/pathfinder/.env

[Install]
WantedBy=default.target
`;

const SEARXNG = `[Container]
ContainerName=pathfinder-searxng
Image=docker.io/searxng/searxng:2026.9.15-ca4965040
Network=pathfinder.network
EnvironmentFile=%h/.config/pathfinder/.env

[Install]
WantedBy=default.target
`;

const DB = `[Container]
ContainerName=pathfinder-db
Image=docker.io/pgvector/pgvector:pg16
Network=pathfinder.network

[Install]
WantedBy=default.target
`;

const INSTALLER = `sed "s|${TAG_PLACEHOLDER}|$PATHFINDER_TAG|g"
pathfinder-db.service pathfinder-wdk-mcp.service pathfinder-searxng.service
pathfinder-research-mcp.service pathfinder-api.service pathfinder-worker.service
pathfinder-web.service
`;

const CLEAN = [
  unit("pathfinder-api.container", API),
  unit("pathfinder-worker.container", WORKER),
  unit("pathfinder-web.container", WEB),
  unit("pathfinder-wdk-mcp.container", WDK_MCP),
  unit("pathfinder-research-mcp.container", RESEARCH_MCP),
  unit("pathfinder-searxng.container", SEARXNG),
  unit("pathfinder-db.container", DB),
];

const withUnit = (name, text) =>
  new Map(CLEAN.map(([key, body]) => (key === name ? [key, text] : [key, body])));

const only = (units, installer = INSTALLER) => {
  const offences = offencesIn(units, installer);
  assert.equal(offences.length, 1, `expected one offence, got ${offences}`);
  return offences[0];
};

test("the shipped quadlets conform", () => {
  assert.deepEqual(collect(), []);
});

test("a conformant set produces no offences", () => {
  assert.deepEqual(offencesIn(new Map(CLEAN), INSTALLER), []);
});

test("a key outside a section is rejected", () => {
  const { errors } = parseUnit("Image=x\n[Container]\n", "u");

  assert.deepEqual(errors, ["u:1: key outside a section -> Image=x"]);
});

test("a line that is neither a header nor a pair is rejected", () => {
  const { errors } = parseUnit("[Container]\nImage\n", "u");

  assert.deepEqual(errors, ["u:2: not a key and a value -> Image"]);
});

test("a continued line is one key", () => {
  const { sections } = parseUnit("[Container]\nExec=one \\\n  two\n", "u");

  assert.deepEqual(sections.get("Container"), [["Exec", "one two"]]);
});

test("a comment and a blank line are not values", () => {
  const { sections, errors } = parseUnit("[Container]\n# note\n\n; note\n", "u");

  assert.deepEqual(errors, []);
  assert.deepEqual(sections.get("Container"), []);
});

test("an image built on the host instead of pulled is rejected", () => {
  const broken = API.replace(
    `ghcr.io/veupathdb/pathfinder-api:${TAG_PLACEHOLDER}`,
    `localhost/pathfinder-api:${TAG_PLACEHOLDER}`,
  );

  assert.match(
    only(withUnit("pathfinder-api.container", broken)),
    /image is localhost\/pathfinder-api:__PATHFINDER_TAG__/,
  );
});

test("an upstream image at latest is rejected", () => {
  const broken = SEARXNG.replace("searxng:2026.9.15-ca4965040", "searxng:latest");

  assert.match(
    only(withUnit("pathfinder-searxng.container", broken)),
    /runs :latest, which names no release/,
  );
});

test("an image at a fixed tag instead of the placeholder is rejected", () => {
  const broken = WEB.replace(TAG_PLACEHOLDER, "v0.2.0a2");

  assert.match(
    only(withUnit("pathfinder-web.container", broken)),
    /image is ghcr\.io\/veupathdb\/pathfinder-web:v0\.2\.0a2/,
  );
});

test("the worker runs the api image", () => {
  const broken = WORKER.replace("pathfinder-api:", "pathfinder-worker:");

  assert.match(only(withUnit("pathfinder-worker.container", broken)), /expected ghcr\.io\/veupathdb\/pathfinder-api/);
});

test("a port published on every interface is rejected", () => {
  const broken = API.replace("127.0.0.1:8010:8000", "8010:8000");

  assert.match(
    only(withUnit("pathfinder-api.container", broken)),
    /publishes 8010:8000, expected 127\.0\.0\.1:8010:8000/,
  );
});

test("a port on an internal unit is rejected", () => {
  const broken = WDK_MCP.replace(
    "Network=pathfinder.network",
    "Network=pathfinder.network\nPublishPort=8100:8100",
  );

  assert.match(
    only(withUnit("pathfinder-wdk-mcp.container", broken)),
    /publishes 8100:8100, expected no host port/,
  );
});

test("an MCP url that names a compose service is rejected", () => {
  const broken = WORKER.replace("http://pathfinder-wdk-mcp:8100", "http://wdk-mcp:8100");

  assert.match(
    only(withUnit("pathfinder-worker.container", broken)),
    /PATHFINDER_WDK_MCP_URL is http:\/\/wdk-mcp:8100\/mcp/,
  );
});

test("an api that does not trust the proxy is rejected", () => {
  const broken = API.replace("Environment=FORWARDED_ALLOW_IPS=*\n", "");

  assert.match(
    only(withUnit("pathfinder-api.container", broken)),
    /FORWARDED_ALLOW_IPS is unset/,
  );
});

test("an api that trusts only the loopback address is rejected", () => {
  const broken = API.replace(
    "Environment=FORWARDED_ALLOW_IPS=*\n",
    "Environment=FORWARDED_ALLOW_IPS=127.0.0.1\n",
  );

  assert.match(
    only(withUnit("pathfinder-api.container", broken)),
    /FORWARDED_ALLOW_IPS is 127\.0\.0\.1, expected \*/,
  );
});

test("a runtime NEXT_PUBLIC_API_URL on the web unit is rejected", () => {
  const broken = WEB.replace(
    "Network=pathfinder.network",
    "Network=pathfinder.network\nEnvironment=NEXT_PUBLIC_API_URL=http://pathfinder-api:8000",
  );

  assert.match(
    only(withUnit("pathfinder-web.container", broken)),
    /read at build time, not at run time/,
  );
});

test("a unit that reads secrets needs the environment file", () => {
  const broken = RESEARCH_MCP.replace(
    "EnvironmentFile=%h/.config/pathfinder/.env\n",
    "",
  );

  assert.match(
    only(withUnit("pathfinder-research-mcp.container", broken)),
    /no EnvironmentFile=%h\/\.config\/pathfinder\/\.env/,
  );
});

test("the database reads no environment file", () => {
  const broken = DB.replace(
    "Network=pathfinder.network",
    "Network=pathfinder.network\nEnvironmentFile=%h/.config/pathfinder/.env",
  );

  assert.match(
    only(withUnit("pathfinder-db.container", broken)),
    /expected no EnvironmentFile/,
  );
});

test("a unit off the network is rejected", () => {
  const broken = DB.replace("Network=pathfinder.network\n", "");

  assert.match(only(withUnit("pathfinder-db.container", broken)), /not on pathfinder\.network/);
});

test("a unit that does not start at boot is rejected", () => {
  const broken = SEARXNG.replace("WantedBy=default.target", "WantedBy=multi-user.target");

  assert.match(
    only(withUnit("pathfinder-searxng.container", broken)),
    /no \[Install\] WantedBy=default\.target/,
  );
});

test("a unit the installer does not name is rejected", () => {
  const installer = INSTALLER.replace("pathfinder-worker.service", "");

  assert.match(
    only(new Map(CLEAN), installer),
    /install\.sh: does not name pathfinder-worker\.service/,
  );
});

test("an installer that never substitutes the tag is rejected", () => {
  const installer = INSTALLER.replace(TAG_PLACEHOLDER, "v0.2.0a2");

  assert.match(only(new Map(CLEAN), installer), /does not substitute __PATHFINDER_TAG__/);
});

test("a missing unit is named", () => {
  const units = new Map(CLEAN.filter(([name]) => name !== "pathfinder-db.container"));

  assert.match(only(units), /expected pathfinder-api\.container/);
});
