---
type: Decision
title: A private dataset is uploaded on the site and analysed here
description: A researcher uploads RNA-Seq counts on VEuPathDB's own My Data Sets page, which PathFinder links to; PathFinder lists the account's own uploads under the researcher's token, opens an installed one as a study, and keeps curated rows only in its shared study cache. Uploading through PathFinder, polling from the browser and deleting datasets automatically were rejected.
tags: [vdi, eda, user-datasets, privacy, veupathdb, product-line]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

PathFinder shows what the AI did and why. VEuPathDB is where a researcher edits by hand, so a
screen the site already has is a link to the site, not a copy of it. The upload page is such a
screen.

- **The upload.** The EDA tab's "Your datasets" section has one link, "Upload on VEuPathDB", to
  the site's own My Data Sets page, `{web_base_url}/app/workspace/datasets`. The genomics site
  links that path as "My Datasets" (`web-monorepo:
  packages/sites/genomics-site/.../records/gene-list-export-utils.tsx`), and its upload form is
  the same page's `/new` route. The site uploads, validates, annotates the samples and installs.
  PathFinder sends no byte of a file.
- **The listing.** `GET /api/v1/eda/datasets?siteId=` reads VDI's owned listing for the site's
  project, `GET /datasets?install_target=<project>&ownership=owned`, under the request's own
  registered token. The client refuses a call that carries none, and the deployment's service
  token is never a substitute. Only `rnaseqrc` rows are listed, since only they become a study
  DESeq2 runs on. Each row's state comes from the client's two-axis predicate for this project:
  `installing`, `installed`, or `failed`. A failed row of the owned listing carries no messages,
  so that row alone reads `GET /datasets/{id}` for VDI's own text, which the tab shows.
- **The study.** An installed row is `EDAUD_<vdiId>`. It is `installed` when this credential's
  `/eda/permissions` map holds it. A study installs after the map was read, so a miss re-reads
  the map once per listing through `catalog.refresh_permissions(site_id)`, and a row still absent
  after that is `waiting`. Opening one is the existing bind; subset, DESeq2 and the export run
  unchanged, because an installed upload is an EDA study like any other. The generic
  `GenesByEdaVizWithCompute` export was measured against the site's own
  `GenesByDESeqUserDataset` and the curated study's export: the same gene set.
- **The agent.** `search_eda_studies` puts up to five of the account's installed uploads ahead of
  the site's ranking, name matches first, marked `user_submitted` with the current site as their
  only site, and says so in one guidance sentence. The ranking of the site's studies is
  unchanged.
- **The shared cache.** `/eda/studies` answers per account (`service-eda:
  StudiesService.java:70-88`). `catalog.list_studies` keeps only `source_type == "curated"` rows
  in the process-wide map, so a researcher's own study never reaches another account's browse
  or the shared semantic index.
- **Genes the site does not annotate.** The export's join drops a gene id the site's annotation
  lacks, without an error. The tab states the difference beside the exported step, "N of M
  genes are not genes of <Site>'s current annotation", from the volcano's cut and the step's
  count. No model is involved.

The runtime's host-started task (`declare_durable_tool(..., host_started=True)` and
`start_host_task`) is released in `assistant-core` and is not used by PathFinder for now.

# What was rejected

- **Uploading through PathFinder.** A form in the tab that streams the files to VDI and a worker
  task that polls the install. It is a copy of the site's page: every rule the site's form
  checks would be checked twice, and PathFinder would hold or stream research data it has no
  business handling. The site's page also owns the reference-genome choice, the sample-details
  annotation and the account's quota.
- **Polling VDI from the browser.** VDI sends no CORS header
  ([VDI is a publish target, not a store](vdi-is-a-publish-target-not-a-store.md)), a browser
  loop stops when the tab closes, and every open tab would be a VDI poller. The tab reads the
  listing once each time it opens.
- **Deleting datasets automatically**, on unbind, on thread deletion, after an age or when an
  install fails. The dataset is the researcher's, in their VEuPathDB workspace; steps in other
  strategies can depend on it. Deleting is the site's page too.

# Anchor

`apps/api/src/pathfinder/services/eda/private_datasets.py`, pinned by
`tests/unit/services/eda/test_own_datasets.py` (states, VDI's text byte for byte, the one
permission re-read), `tests/unit/transport/test_vdi_calls_carry_the_request_token.py`,
`tests/unit/services/eda/test_study_cache_curated_only.py`,
`tests/unit/ai/tools/test_eda_study_search_lists_own_datasets.py`, and the live check
`tests/live/test_private_dataset_live.py`.
