---
type: Backlog
title: A histogram fit and a byValue fit agree on one step
description: The recorded tm_count attribute histogram of GenesByTransmembraneDomains sums to 854 transcripts while the byValue report of the same search answers subsetSize 840; the recordings keep no request bodies, so record one step with both reports, totalCount and the bodies, and until then a histogram fit may overstate its total.
tags: [verify, wdk, transcripts, recordings]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: proposed
---

# A histogram fit and a byValue fit agree on one step

## What happens

`step_report_tm_count_histogram.json` (the `tm_count-histogram` attribute report of
`GenesByTransmembraneDomains` on QA plasmodb) sums to 854. `step_column_tm_count_by_value.json`
(the `tm_count` byValue report of the same search, recorded the same day) answers `subsetSize`
840, `numVarValues` 840. By WDK's source both count one row per primary key of the answer, one
per transcript: `AbstractByValueReporter` groups the answer's records, and
`AbstractAttributeReporter.getAttributeSql` joins the attribute query to the answer's id SQL
before `HistogramAttributeReporter` groups it. Neither recording keeps its request body, so the
two may have run with different parameter values.

A column fit read from a search's attribute histogram takes the sum of its bins as the step's
total (`ai/tools/standalone/results.py::_column_bins`). If the histogram counts more rows than
the step holds, the fit overstates its total and the card's "N of M transcripts".

## Change

Record, on QA plasmodb, one built transcript step with both reports of one column, its
`totalCount` and `displayTotalCount`, and the request body of each read. Compare the three
totals. If they differ, take the fit's total from the step's own count, and name the measured
cause.

## Done when

A unit test over the one recording asserts that the histogram fit's total equals the step's
`totalCount`, or states the measured difference and the reason for it.
