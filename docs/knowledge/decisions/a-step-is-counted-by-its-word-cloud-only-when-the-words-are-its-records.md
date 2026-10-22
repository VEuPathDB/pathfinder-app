---
type: Decision
title: A step is counted by its word cloud only when the words are its records
description: The Lead's count_step_by_column counts a built step's records by one column in one reporter request, with the column's byValue reporter where the site offers it and with the column's wordCloud attribute reporter otherwise; word counts are accepted only when every word is a genome code of the site's taxonomy and the counts sum to the step's record count, because a matching sum is necessary but not sufficient. Any other word-cloud column, a word cloud at the site's cap, a byValue answer with no counts and a column with neither reporter are refused by name. Downloading the step's records and counting them in process, and accepting any word-cloud column whose sum matches, were rejected.
tags: [lead, tools, tally, orthomcl, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

**A built step is counted by the site, in one request.**
`services/experiment/step_tally.py::run_step_tally` reads the step's record type
once, then counts the step with one reporter request:

- a column whose `tools.reports` holds `byValue` is counted with the step's
  `byValue` column reporter (`get_column_distribution`), the reporter
  `count_by_column` uses for a search;
- any other column is counted with its `wordCloud` format
  (`WDKAttributeField.format_named("wordCloud")`, for example
  `abbreviation-wordCloud`), through the client's `get_step_word_counts`.

No OrthoMCL attribute offers `byValue`, so on OrthoMCL every count is a word cloud.

**Word counts are accepted only from a column of genome codes.** The word cloud
counts words, not values: it splits a value into words, drops short and numeric
pieces, and folds case and plurals (the client's WDK-ANS-011). So a sum that
equals the step's record count is necessary and not sufficient: two values
`kinase` and `kinases` answer one word `kinase` whose count matches the step, and
two domains on one record can offset a record with none. The tally therefore
accepts word counts only when every word is a genome code of the site's taxonomy
(`veupathdb_mcp.catalog.genome_names`), a value of one fixed token that no fold
merges, and then only through `WDKWordCounts.record_counts`, which refuses a sum
that differs (`ColumnNotCountableError`). A word-cloud column is a column of
genome codes by its name (`abbreviation`, the genome code column of OrthoMCL's
records), never by a word cloud sent to find out; any other column with only a
word cloud is refused by name before a word cloud is read. A word cloud at the
site's cap of 10,000 distinct words answers no counts, and the client refuses
it; the tally refuses it by name. Every refusal lists only the columns that can
pass: those the site counts by value and the genome code columns, and never a
column already refused on that step in the same Lead pass.

**A byValue answer with no counts is not a count of 0.** The client answers a
site error on the byValue reporter with an empty distribution. When it names no
records, the tally reads the step's count: a step of 0 records is a tally of 0,
and any other step is refused as "the site answered no counts". When it names
records that all lack a value, the column is refused.

**Genome codes are named.** When every counted value is a genome code, each row
carries the genome's name as its `label`, and the card shows it beside the code.

**The tally keeps its 200 largest rows** (`services/experiment/tally_rows.py`,
`KEPT_ROWS`), states the total and the number of values, and its card links the
step on the site (`ColumnTally.step_url`, the strategy's page at that step).

**A count of a result's members goes through the transform.** The Lead's rule:
a count of a result's members by a column (the proteins of a set of groups by
organism) is the transform to the members, then `count_step_by_column` on that
step. A step the strategy does not hold, and a refused column, go back to the
model with what it can do instead.

# What was rejected

**Downloading the step's records and counting them in process.** A transform
step of several hundred thousand proteins is counted by genome in one word-cloud
request; reading every protein's code would page the whole answer through the
standard reporter and hold it in the worker for one table of a few hundred rows.

**Accepting any word-cloud column whose sum matches.** The sum separates a
multi-word column (`taxon_name`, one count per word of the genome names) only
when the sum differs. A folded or offset column keeps the sum and still merges
values, so the sum alone would show a wrong table with no refusal.
