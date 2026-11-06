---
type: Backlog
title: The readings card's mock count is a recorded report
description: The Explore tests answer the signal-peptide count from the QA root count measured for a seed strategy, not from a recorded report of GenesWithSignalPeptide; record a real report and answer from it.
tags: [modes, explore, testing, fixtures, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# The readings card's mock count is a recorded report

## What is known

The Explore turn tests count two readings. `GenesByGeneType` is answered from the recorded
plasmodb QA report `report_gene_type_protein_coding` (5389). `GenesWithSignalPeptide` is
answered by `tests/_support/explore_turns.py::seed_count`, which builds an answer around the
root count measured for the plasmodb seed "PF3D7 Signal Peptide Genes"
(`data/seeds/plasmodb.json`). No standard report of that search is recorded, so the answer's
shape is built by hand.

CLAUDE.md requires mock data that matches a real WDK response.

## What to do

1. Record a standard report of `GenesWithSignalPeptide` on QA PlasmoDB, with the parameters
   the mock arc counts (the site organism, SignalP-6.0), from a host that reaches QA, and keep
   it beside `report_gene_type_protein_coding.json` in `tests/fixtures/wdk/`.
2. Answer the count in `tests/_support/explore_turns.py` from that recorded report and delete
   `seed_count`.

## Done when

Both counts on the readings card come from recorded reports, and no test builds a WDK answer
around a count by hand.
