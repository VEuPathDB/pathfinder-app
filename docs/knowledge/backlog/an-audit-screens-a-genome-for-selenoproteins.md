---
type: Backlog
title: An audit screens a genome for selenoproteins
description: A genome-scope audit screens length and split candidates from the collected gene reports; the selenoprotein check needs each genome's proteins that hold a selenocysteine (U), which no library function reads per genome, so until one does the check runs on explicit gene targets only.
tags: [audit, selenoprotein, veupathdb-mcp, screen]
generated: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: proposed
---

# An audit screens a genome for selenoproteins

## What happens

A run's scope names the genomes it screens and the checks it screens them for,
and `domain/audit/scope.py::ScreenedCheck` admits `gene_length` and
`gene_split` only: the screen finds both from the gene report each genome's
collect stage stores. The selenoprotein check (`selenoprotein_end`) is
admitted only as a gene target, a model gene and its reference named by the
caller. A screen for it needs each genome's proteins with a `U`, and
`veupathdb_mcp.audit` holds no function that reads them per genome: its
selenocysteine functions judge one named pair.

## Depends on

A `veupathdb-mcp` release with a per-genome reader of the proteins that hold a
selenocysteine, or of the genes the site annotates as selenoproteins, read
only from what the site serves.

## Change

1. Take that release.
2. `selenoprotein_end` joins `ScreenedCheck`; the collect stage stores what the
   reader returns, and the screen writes one candidate per model gene with its
   reference.
3. Tests on the recorded bodies the library's own tests use.

## Done when

A scope that names a genome and the selenoprotein check screens that genome
with no gene target named, and the confirm stage checks its sample.
