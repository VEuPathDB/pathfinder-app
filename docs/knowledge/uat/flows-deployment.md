---
type: TestPlan
title: UAT flows - deployment checks
description: The checks a runner makes once on the test deployment before any flow - readiness with every catalog loaded, the served version, the worker, the two MCP servers, the site list, the model configuration and the request guards.
tags: [uat, flows, deployment, health]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Deployment checks (D)

`<api-url>` is the deployment's api origin and `<mcp-url>` / `<research-url>` its two MCP servers, all from the operator. A failed D check stops the whole run ([exit criteria](exit-criteria.md)). Not measured against the test deployment (no api was running here); the shapes are the code's and the MCP answers are the local containers'. Expected: measure at UAT start.

| Id | Do | Expect |
|---|---|---|
| D1 | `curl -s <api-url>/health/ready` | HTTP 200; `status: "healthy"`; `notReady: []`; `degraded: []`; `readiness.database`, `embedding_backend`, `graph_checkpointer` and `input_screening` each `{"ready": true, "error": null}`; `readiness.catalogs` holds 14 sites (`veupathdb`, `plasmodb`, `toxodb`, `cryptodb`, `piroplasmadb`, `giardiadb`, `amoebadb`, `microsporidiadb`, `tritrypdb`, `trichdb`, `fungidb`, `hostdb`, `vectorbase`, `orthomcl`), each `ready: true`. A site in `degraded` makes its flows `blocked` |
| D2 | `curl -s <api-url>/health` | `{"status": "healthy", "version": "<release>", ...}`; `<release>` is the tag under test (the checkout reads `0.2.0a16`). There is no `/health/live` |
| D3 | `curl -s <api-url>/health/system` | `ready: true`, `workerAlive: true`, `notReady: []` (a worker silent for 30 s makes it `false`) |
| D4 | `curl -s <mcp-url>/health` and `curl -s <research-url>/health` | `{"status":"healthy","server":"veupathdb-wdk-mcp","version":"<v>"}` and `{"status":"healthy","server":"veupathdb-research-mcp","version":"<v>"}`, `<v>` equal to the `ai-wdk-mcp` tag in `docker-compose.yml` (`v0.2.0a28` in this checkout). The local containers answered `0.2.0a27` on 2026-09-24: a stale local image, which the same check catches on a deployment |
| D5 | `curl -s <api-url>/api/v1/sites` | 14 rows, each `available: true`, `unavailableReason: null`; the five UAT sites among them |
| D6 | `curl -s <api-url>/health/config` | `llmConfigured: true`, `providers.openai: true` |
| D7 | `curl -s <api-url>/api/v1/models` | The three OpenAI models `enabled: true`; `GPT-5.6 Luna` with `supportsImages` and `supportsDocuments` true |
| D8 | `curl -s https://<host>/<project>/service/` for the five sites | `buildNumber` recorded in [the index](index.md); 71 when these documents were written |
| D9 | `curl -s -X POST <api-url>/api/v1/gene-sets/import -H 'Content-Type: application/json' -d '{}'` (no `X-Requested-With`, no bearer) | 403 `{"detail":"Missing required X-Requested-With header"}` |
| D10 | `curl -s <api-url>/api/v1/conversations?siteId=plasmodb` with no credential | 401 `Not authenticated` |
| D11 | In the app, signed in | Send `hello` in a new conversation on plasmodb | A reply within 30 s; the Tasks panel empty; no error toast |
