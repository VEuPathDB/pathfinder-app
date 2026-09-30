---
type: Backlog
title: A curated search's data type is a catalog mark
description: A data-type requirement is grounded by what a step runs on; an upload's type and an analysis's compute are read, but a curated search and a curated EDA study still fall back to the search's name, and the upload types refresh only when a check runs.
tags: [frame, verification, catalog, veupathdb-mcp]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A curated search's data type is a catalog mark

**What I did.** Grounded a data-type requirement ("RNA-Seq") by the data the
step carries: the declared type of the upload a user-dataset search binds, and
the compute of an analysis on an upload's study.

**What I got.** Those two paths ground the requirement from data. A curated
search (`GenesByRNASeq...`) is still grounded by its WDK question name, a
curated EDA study (`DS_...`) has no readable data type so its analysis step
falls back to the search name, and `StrategyDomainState.upload_types` is read
only when a check runs, so between a build and its check the ledger shows a
new upload step as ungroundable.

**Why that's wrong.** A name is not data: a renamed or unfamiliar search
grounds nothing, and a curated study's assay is a fact the site holds.

**Fix.** The tool server marks each search's assay from the site's own
metadata (the record class's dataset attributes, the question's `properties`,
or the study's EDA metadata), the way it marks the organism parameter, and the
host reads that mark for curated searches and studies; `upload_types` is read
at bind, not at check.

**What you'd get.** Every step grounds its data type from the site's data,
and the ledger never shows a step as ungroundable between its build and its
check.
