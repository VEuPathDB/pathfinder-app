---
type: Decision
title: VDI is a publish target, not a store and not a search input
description: An opt-in button publishes a gene set to the researcher's VEuPathDB workspace through VDI and records the dataset id on the row; replacing the gene_sets table with VDI and feeding a VDI id back into a WDK DatasetParam were both rejected on measured evidence, and the action stays a human button rather than an agent tool.
tags: [vdi, user-datasets, gene-sets, veupathdb, wdk-alignment]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was decided

A gene set can be published, once and on request, as a `genelist` user dataset in the
researcher's own VEuPathDB workspace. PathFinder keeps the set; the row gains a nullable
`vdi_id` that points at the published artifact. Nothing PathFinder does next depends on
the publication.

- Client: `veupathdb/wdk/vdi/` (`client.py`, `models.py`), httpx, reaching only
  the `veupathdb` foundation. It reads the request's own registered token from
  `veupathdb_auth_token_ctx` and refuses with `WDKLoginRequiredError` when there is none;
  the deployment's service account is never a substitute, because the dataset belongs to
  whoever published it.
- Base URL: `{site_origin}/vdi`, derived the way the EDA base is. Every one of the
  fourteen configured sites answers `GET /vdi/plugins` with 200, so `sites.yaml` gains no
  per-site override.
- Service: `services/gene_sets/vdi.py`, two functions. `publish_to_vdi` loads the set,
  uploads it and records the id. `vdi_publication_status` reads the three status axes on
  demand. PathFinder runs no polling loop.
- Transport: `POST` and `GET /api/v1/gene-sets/{id}/vdi-publication`, both behind the
  registered-login gate.
- UI: one button on the gene-set figure in the thread (`content/parts/DataGeneSet.tsx`),
  beside its delete, with a visibility select and a confirm step, because the action creates
  a durable artifact outside PathFinder.

# What the probe measured

Against `https://plasmodb.org/vdi` on 2026-09-04, with the dev account's WDK token
obtained exactly as `veupathdb/wdk/auth_login.py::password_login` obtains it:

| request | result |
| --- | --- |
| `GET /plugins`, no credential | 200, `genelist` v1.0 over 13 install targets |
| `GET /datasets`, no credential | 401 `{"status":"unauthorized"}` |
| `GET /datasets`, `Authorization: Bearer <token>` | **200** |
| `GET /datasets`, `Authorization: bearer <token>` | 200 |
| `GET /datasets`, `Authorization: <token>` with no scheme | 401 |
| `GET /datasets`, `Auth-Key: <token>` | 401 |
| `GET /datasets`, `Authorization` cookie | 200 |
| `GET /datasets`, `?access_token=<token>` | 200 |

So S3's open question 4 is settled: PathFinder's own token clears VDI's
`@Authenticated(allowGuests=false)`. Three credential forms work, which is exactly what
`AuthFilter.findAuthUser` reads (header, `access_token` query parameter, `Authorization`
cookie). The client sends the bearer header.

One probe dataset was created and deleted. It reached `install: complete` on PlasmoDB
**7.6 seconds** after the 202, which answers open question 5: VDI publishes no SLA, and
the measured latency for a five-gene list was seconds, not minutes. The measurement does
not change the architecture: the number is not a contract, and an agent loop must not
wait on it.

# What was rejected

- **Replacing the `gene_sets` table with VDI.** 214 lines of storage would be replaced by
  a larger client, and every gene-set read would become a cross-service call against a
  service whose writes complete asynchronously through six hops. PathFinder's gene sets
  are working state inside a turn; VDI's are published artifacts installed into twelve
  production databases. Different lifetimes.
- **Feeding a VDI id back into a WDK search.** `DatasetParam.java` requires the stable
  value to pass `FormatUtil.isInteger` and to resolve through `getDatasetWithOwner(long,
  userId)`. A `VdiId` matches `^[a-zA-Z0-9_-]+$` (the probe's was `soV5JEQEcF00p`), so it
  is not a legal `DatasetParam` value. This is `WDK-PARAM-009`: the handle is one WDK
  issues, never one a client composes. PathFinder keeps minting `sourceType: "idList"`.
  The search that does consume a published list, `GenesByUserDatasetGeneList`, takes a
  flat vocabulary term that exists only after the per-site install finishes.
- **An agent tool.** Publishing creates a durable artifact in the researcher's account on
  a public site, under a visibility they choose. It stays a button a person presses.
- **Calling VDI from `apps/web`.** No response carries `Access-Control-Allow-Origin`.

# Falsifier

`GET https://<site>/vdi/plugins` stops listing `genelist`, or stops listing the site's own
project id among its `installTargets`; or `POST /datasets` stops accepting the multipart
`details` + `dataFile` pair recorded in
the VDI surface (`veupathdb-py: docs/knowledge/wdk/rest/vdi-surface.md`).
