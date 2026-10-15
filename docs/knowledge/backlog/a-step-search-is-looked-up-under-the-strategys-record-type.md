---
type: Backlog
title: A step's search is looked up under the strategy's record type
description: Building and importing a strategy whose steps answer two record types reads a leaf's search definition under the root's record type and under transcript first, and recovers only after each 404.
tags: [wdk, record-type, orthomcl, gene-sets]
generated: { by: claude-code/opus-5.5, at: 2026-10-15T00:00:00Z }
status: proposed
---

# A step's search is looked up under the strategy's record type

## What I did

One turn on the QA OrthoMCL site: a pasted protein, "BLAST it and tell me which
ortholog groups the hits fall into". The build made `ByBlast` (record type
`sequence`, 50 hits) under `GroupsFromSequences` (record type `group`, 1 group),
and the strategy's gene set was imported after it.

## What I got

The worker log of that turn holds four 404s, each followed by the read that worked:

| when | request | WDK answered |
|---|---|---|
| before the BLAST step is created | `GET /record-types/group/searches/ByBlast` | `There is no search "ByBlast" associated with record type "GroupRecordClass"` |
| before the strategy is created | `GET /record-types/group/searches/ByBlast` | same |
| the gene set import | `GET /record-types/transcript/searches/ByBlast` | `Resource 'record type: transcript' does not exist.` |
| the gene set import | `GET /record-types/transcript/searches/ByBlast` | same |

## Why that's wrong

Nothing the researcher sees is wrong, but every such strategy sends four requests
WDK refuses, each logged as an error, so a real error in the same log is harder to see.

## Why it happens

The import passes the strategy's record type to `_extract_step_search_context`
(`veupathdb_mcp/wdk/gene_set_steps.py`), where `record_type or step.record_class_name`
lets the caller's value win over the step's own record class. The build-side caller
that reads `ByBlast` under `group` is not traced yet.

## Fix

Read a step's search under the step's own record class, as `record_class_of` and the
WDK step's `recordClassName` name it.

## What you'd get

The same turn with no 404 in the worker log.
