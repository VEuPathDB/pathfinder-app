---
type: Reference
title: EDA REST surface
description: The EDA service endpoints PathFinder would consume, their shapes, and how authentication works, verified live on PlasmoDB.
tags: [eda, rest, endpoints, auth]
generated: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA REST surface

Base URL: `https://{site}/eda` (verified on plasmodb.org and clinepidb.org).
Source of truth: `VEuPathDB/service-eda` `api.raml` + `schema/library.raml`,
rendered at https://veupathdb.github.io/service-eda/api.html. Endpoints below
are the subset PathFinder would consume; the service also carries dataset
access management, staff, metrics, and download endpoints.

## Authentication

Same WDK bearer token PathFinder already holds
(`integrations/veupathdb/auth_login.py:password_login`). Verified live:

- No credential -> `401 {"status":"unauthorized"}` even for `/studies`.
  Guest access is refused, consistent with
  [WDK requires a registered login](../decisions/wdk-requires-registered-login.md).
- `Cookie: Authorization={token}` -> 200, and `Authorization: Bearer {token}`
  -> 200 (both live-verified; the bearer form is what the WSF plugins send).
  The `Auth-Key: {token}` header form returns 401.

## Metadata

- `GET /studies` -> `{studies: [{id, datasetId, sha1hash, sourceType,
  displayName, shortDisplayName?, description?, lastModified}]}`. 759 rows on
  PlasmoDB on 2026-08-27; cross-project. `shortDisplayName` and `description`
  are declared required and are sometimes absent (14 and 2 of 759); `sha1hash`
  is the empty string on user-submitted studies.
- `GET /studies/{studyId}` -> `{study: {id, isUserStudy, hasMap, rootEntity:
  {id, idColumnName, displayName, variables[], collections[], children[]...}}}`.
  The full recursive tree.
- `GET /studies/{studyId}/entities/{entityId}` -> one entity, no recursion,
  and no `idColumnName` or `isManyToOneWithParent` either: the handler copies
  only id, description, displayName, displayNamePlural, variables and
  collections, despite its declared response type marking the other two
  required. Take those fields from `GET /studies/{studyId}`.
- `GET /permissions` -> `{perDataset: {<datasetId>: {studyId, sha1Hash,
  isUserStudy, displayName, shortDisplayName?, description?, type,
  actionAuthorization, isManager, accessRequestStatus}}}`. The dataset-to-study
  map and the user's access in one call. Keys are `DS_*` or `EDAUD_*`; the
  casing is `sha1Hash` here against `sha1hash` in `/studies`; `perDataset` is a
  superset of `/studies` (880 against 759 live, the extra 121 backing SNP/CNV
  sample studies); the RAML declares `shortDisplayName`/`description` required
  with `additionalProperties: false` while 24 of 880 live entries omit one, so
  parse with `extra="ignore"`.

## Subsetting

- `POST /studies/{s}/entities/{e}/count` with `{filters: [...]}` -> row count.
- `POST /studies/{s}/entities/{e}/tabular` with `{filters, outputVariableIds,
  reportConfig?}` -> TSV by default (primary key + ancestor primary keys +
  requested variables). JSON only when the `Accept` header is exactly
  `application/json` (`application/json, */*` yields TSV), and the JSON body
  is a bare `string[][]` with the header as row 0, not the declared
  `{tabular: [...]}`. This is the endpoint the WDK gene plugin uses. Full
  reportConfig semantics: [subsetting-and-tabular.md](subsetting-and-tabular.md).
- `POST /studies/{s}/entities/{e}/variables/{v}/distribution` -> histogram
  and stats for a variable under filters (how the UI shows live subset
  feedback).
- `POST /studies/{s}/entities/{e}/variables/{v}/root-vocab` -> TSV pairs of
  (root entity id, value), no header, TSV only (an `Accept: application/json`
  header is a 500). Requires a `string` variable with a vocabulary, and is NOT
  subset-sensitive: only filters on the same variable are applied, all others
  are discarded.
- `POST /filter-aware-metadata/continuous-variable` -> variable metadata
  under filters (subset-aware bin ranges and median).

## Merging and derived variables

- `POST /merging/query` -> tabular data across entities with derived
  variables applied. The response is `text/tab-separated-values`, there is no
  paging or sorting config (unlike `/entities/{e}/tabular`), and the call is
  gated on `permissions.perDataset[ds].actionAuthorization.resultsAll` - 403
  otherwise, verified live.
- `POST /merging/derived-variables/metadata/variables` -> one
  `DerivedVariableMetadata` per spec; `GET .../metadata/units` -> the unit
  conversion table. `POST .../input-specs` is documentation scaffolding only:
  the RAML says it exists "only to produce documentation of derived variable
  configuration types", and live it returns 204 empty on POST and 405 on GET.
- `GET|POST /users/{uid}/derived-variables/{project}` (+ `/{dvId}` GET/PATCH,
  no DELETE) -> persisted user derived variables, keyed by `datasetId`. This
  route returned HTTP 500 on both plasmodb.org and clinepidb.org on
  2026-08-27, so only the inline `DerivedVariableSpec[]` path in merge,
  compute and data-plugin bodies is usable today.

## Computes and visualization data

- `GET /apps` -> every app with its visualizations and per-project
  availability (see [visualizations.md](visualizations.md) for the live
  catalog).
- `POST /computes/{computeName}?autostart=...` (default `true`) with
  `{studyId, filters, config, derivedVariables}` -> `{jobID, status,
  queuePosition?}` with `status` in `queued | in-progress | complete | failed
  | expired | no-such-job`. `studyId` here is the STUDY id, not the dataset
  id. The job id is a derivable MD5 of the plugin name plus the key-sorted
  body, so identical requests share a result across users; `autostart=false`
  is a pure lookup.
- Reading output is per plugin: `POST /computes/{name}/statistics` (JSON) for
  `differentialexpression`, `differentialabundance`, `correlation`,
  `selfcorrelation`; `POST /computes/{name}/{file}` with `file` in
  `meta | tabular | statistics` (text) for `alphadiv`, `betadiv`,
  `rankedabundance`, `dimensionalityreduction`, `example`. The other family's
  route is a 404.
- `POST /apps/{app}/visualizations/{viz}` with `{studyId, filters,
  computeConfig?, config}` -> server-computed plot data (e.g. volcanoplot
  `statistics: [{pointID, effectSize, pValue, adjustedPValue}]`).
  Compute-less (pass-through) apps take no `computeConfig` at all; a
  compute-backed viz whose job has not completed is
  `400 "Compute results are not available for the requested job."` - the viz
  endpoint never starts a compute.
- `GET /jobs/{jobId}` -> `{jobID, status}`; `GET /jobs/{jobId}/files` -> the
  output file listing; `GET /jobs/{jobId}/files/{name}` -> one file;
  `DELETE /jobs/{jobId}` -> 204, allowed only on an owned, finished job (403
  otherwise). Details: [computes-and-jobs.md](computes-and-jobs.md).

## Analyses (persisted state)

- `GET|POST|PATCH /users/{uid}/analyses/{project}` and
  `GET|PATCH|DELETE|POST-copy .../{analysisId}` -> analysis CRUD. The body is
  the `Analysis` document (`descriptor` with subset filters, computations,
  derived variables).
- On the create, `displayName` is capped at 50 UTF-8 bytes and `description` at
  4000; over the cap the answer is
  `400 "displayName must not be larger than 50 bytes."` and no analysis is
  written. `EdaNewAnalysis` cuts both fields to those bounds.
- `GET /public/analyses/{project}` and
  `GET /import-analysis/{project}/{analysisId}` -> shared analyses.
- Thread surgery does not use the `POST .../{analysisId}` copy: a branch and a
  revert re-create the document from the descriptor the thread's own log
  recorded (`POST /users/{uid}/analyses/{project}` then
  `PATCH .../{analysisId}`), because the copy would carry the source's current
  subset and not the anchor's. Nothing in the application calls
  `DELETE .../{analysisId}`, so replacing a thread's binding leaves the
  document it replaced on the service.
- `GET|PUT /users/{uid}/preferences/{project}` -> workspace preferences.
