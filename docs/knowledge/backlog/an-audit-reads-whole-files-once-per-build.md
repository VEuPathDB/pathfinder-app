---
type: Backlog
title: An audit reads whole files once per build
description: The gene-model audit reads the sites one small request at a time; read each genome's static files once per release build into a cache keyed by build and checksum, ask WDK for whole answers instead of single records, group checks by reference position, and use a real aligner, so a full audit is one file sync plus local compute with near-zero site load.
tags: [audit, performance, caching, provenance, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# An audit reads whole files once per build

## What happens

The audit reads gene records, genome windows and variant records one request at a time, and its
alignments run in pure Python. A run over a few genomes costs a few hundred requests and minutes of
waiting; a run over every genome a site serves would put days of steady load on the site.

## Change

1. Files once per build. Each genome's static files in the genome-browser store (genome FASTA, gene
   models, RNA junctions, peptides) are read once per release build into a local cache, keyed by site,
   genome, build number and checksum. Checks read the cache. A new build re-reads only the files whose
   checksum changed, and re-checks only the genes whose model changed. Where the deployment can mount
   the release files directly, it reads them from there and sends no request at all.
2. Whole answers. Gene attributes and tables are read with one answer-level report per genome, not one
   record request per gene.
3. Grouped lookups. Checks that ask about a position in a reference genome (variant calls, the same
   locus in every strain) are grouped by position, so one search answers every strain at once.
4. A real aligner. DNA and protein alignments use a compiled aligner instead of pure Python.
5. Provenance. Every cached file and every value derived from it records its source URL, build number,
   checksum and read time, and audit findings point back to them.
6. Gentle scheduling. One request at a time per site, a per-site budget per run, conditional requests,
   and a stop on any server error, as today.

## Done when

A full audit of one site runs from the cache with no request beyond the per-build file sync, reports the
same findings as the request-at-a-time path on a recorded genome, and every finding names the file and
build it was read from.
