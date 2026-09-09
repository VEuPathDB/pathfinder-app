---
type: Decision
title: The hidden-default sweep stops at published defaults, and the rest is dated rather than measured
description: The nightly sweep binds every required parameter from its own initialDisplayValue and measures what WDK answers. It does not invent a value for channel or dataset_url. Researching a plausible value per search was rejected: it is 131 separate per-search studies whose answer expires, and the artifact already names every search that refuses and every search that 500s.
tags: [wdk-alignment, parameters, silent-zero, measurement, site-model]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

`veupathdb-py: tests/live/hidden_defaults.py`, run by the live check
in `veupathdb-py: tests/live/test_wdk_hidden_defaults.py`, binds every required parameter of a transcript
search from that parameter's own `initialDisplayValue` and records what WDK
answered. **It stops there.** Where a visible parameter's published default is
one WDK refuses, the search is recorded as a 422 and the hidden parameters behind
it stay unmeasured. The sweep does not
compose a value of its own for `channel`, `dataset_url`, or any other parameter,
and this item is closed by that ruling rather than by measuring them.

The run on plasmodb.org on 2026-08-22 measured 237 searches carrying a hidden
required default: 19 answered 200, exactly 1 of those returned zero rows
(`GenesByRNASeqpfal3D7_Lee_Gambian_ebi_rnaSeq_RSRCWGCNAModules`), 158 were
refused at `RUNNABLE`, 58 answered 500, 1 timed out and 1 publishes no default
to bind. Not one of the 158 refusals names a hidden parameter: every parameter
WDK named in `byKey` is visible. `channel` sits on 75 of the unmeasured searches
and `dataset_url` on 56.

# The alternative that was rejected

**Choosing a plausible value per search, so the hidden defaults behind the
visible refusal can be reached.** `channel` and `dataset_url` sit on microarray
and RNA-seq searches whose `samples_percentile_generic`, `samples_fc_ref_generic`
and `samples_fc_comp_generic` publish defaults WDK refuses, so reaching the
hidden parameter means picking sample sets for that dataset. That is a separate
study per search - 131 of them - and its answer is a property of the dataset
loaded on the site that day, not of the platform. The cost is a research task per
search; the yield is one more row in a table whose useful entries the sweep
already produces.

Two things the sweep already does make the study unnecessary:

- **The refusals are already attributed.** Every 422 carries WDK's own `byKey`,
  and every key in it is a visible parameter. The claim under test - that a
  hidden default silently returns nothing - is not what these searches do. They
  refuse, by name, before the query runs, which is
  WDK-PARAM-010 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`) on the visible
  half.
- **The artifact names every search by outcome.** `SweepReport.measured` holds one
  `SearchMeasurement` per search with its `status` and WDK's own message in
  `note`, so the 58 that answer 500 are listed by name in
  `wdk-hidden-defaults.json`, which the nightly lane uploads on every run. The
  lane also records the enumeration counts through `DriftLog`, so the next drift
  in which parameters exist is dated rather than rediscovered.

# What this costs

A hidden required default that returns zero rows on one of the 219 unmeasured
searches is not known today, and PathFinder would fill it
(`veupathdb-py: src/veupathdb/domain/parameters/specs.py:fill_hidden_required_defaults`). The protection
against that is not this sweep: it is that a filled hidden default is reported to
the user as a value nobody chose
(WDK-PARAM-008 in `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`, through
`filled_hidden_defaults`), and that a zero count is surfaced rather than
narrated away. The sweep buys advance warning, and it buys it for the searches
whose published defaults resolve.

The measurement becomes cheap the day a search's visible parameters are bound by
a real request. A run that builds one of these searches for a researcher has the
sample sets the study would have had to invent, and the count it reads is worth
more than a synthetic one.
