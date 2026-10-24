---
type: Backlog
title: A column fit names the records its report counts
description: read_column_fit states a byValue column fit of a transcript step in genes and an attribute histogram fit in transcripts, while veupathdb-mcp 0.2.0b48 states from WDK's reporter source that a byValue count on a transcript step counts each transcript; measure one step on QA and make the fit's unit what the report counts.
tags: [verify, wdk, tally, transcripts]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: proposed
---

# A column fit names the records its report counts

## What happens

`ai/tools/standalone/results.py::_column_bins` gives a fit read with the byValue
column reporter `counted_in="genes"` and a fit read with a search's attribute
histogram `counted_in="transcripts"`, so the evidence card says "840 of 840 genes
fit # TM Domains (2 to 99)". The tool server's `count_step_by_column` docstring
(veupathdb-mcp 0.2.0b48, read from `AbstractByValueReporter`) says a byValue count
on a transcript step counts a gene once for each of its transcripts, and
`count_step_by_column` here now names its tally in transcripts. One of the two
units is wrong for the byValue report.

## Change

Record, on QA plasmodb, one transcript step whose genes have more than one
transcript: its gene count, its transcript count and the byValue report's
`subsetSize` for one record type column. Set `counted_in` from what the report
counts, and add the recording to the suite.

## Done when

A unit test over the recording asserts the fit's total equals the count the site
states in the same unit, and the card's sentence names that unit.
