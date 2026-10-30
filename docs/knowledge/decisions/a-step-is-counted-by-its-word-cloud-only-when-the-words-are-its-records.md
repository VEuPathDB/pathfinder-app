---
type: Decision
title: A step is counted by its word cloud only when the words are its records
description: The Lead's count_step_by_column counts a built step's records by one column in one reporter request, with the tool server's count_by_column (the byValue reporter, over the record type's and the search's own columns) and with a genome code column's wordCloud attribute reporter where the site offers only that; step_columns lists a step's columns 100 at a time with which can be counted. Word counts are accepted only when every word is a genome code of the site's taxonomy and the counts sum to the step's record count, because a matching sum is necessary but not sufficient. Any other word-cloud column, a word cloud at the site's cap, a refused byValue report and a column with neither reporter are refused by name. Downloading the step's records and counting them in process, and accepting any word-cloud column whose sum matches, were rejected.
tags: [lead, tools, tally, orthomcl, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

**A built step is counted by the site, in one request.**
`services/experiment/step_tally.py::run_step_tally` reads the step's record type
from the site catalog (`get_raw_record_types`), so the only record type read on the
wire is the tool server's, then counts the step with one reporter request:

- a genome code column the record type offers only a `wordCloud` format for
  (`WDKAttributeField.format_named("wordCloud")`, for example
  `abbreviation-wordCloud`) is counted with it, through the client's
  `get_step_word_counts`;
- every other column goes to the tool server's `veupathdb_mcp.wdk.count_by_column`,
  which counts it with the step's `byValue` column reporter. It reads the record
  type's columns and the step search's own columns (a BLAST step's `evalue`), counts
  a `STRING` or `NUMBER` column that lists `byValue` in `tools.reports`, and refuses
  any other column with `ColumnNotCountedError`, which names the columns that can be
  counted. A string column answers its values ranked by count, at most `top`, with
  the number of values; a number column answers its bins, every bin in the site's
  order, and its number of values is its number of bins.

The tool takes `top`, 20 unless the model asks, at most 200
(`DEFAULT_COLUMN_COUNT_TOP`, `MAX_COLUMN_COUNT_TOP`). The column report counts the
step's records: WDK's `AbstractByValueReporter` groups one row per primary key of
the answer, and on a transcript step that is one row per transcript, so a gene
counts once per transcript. The tally's noun is the record type's own
(`graph_helpers.record_noun`: transcripts, proteins), never the noun a step's size
is counted in.

**The Lead lists a step's columns before it counts.** `step_columns` lists the
columns of any built step of the strategy, a transform included, through
`list_step_columns`: each column's name, display name, data type and `countable`, a
genome code column its word cloud counts marked countable
(`step_tally.py::countable_columns`). A transcript step lists about 2,400 columns,
so the tool takes a `name` (text the name or display name contains, any case) and
`countable_only`, and answers 100 per page with the number that match and an
`offset`.

**The Lead's rule routes a count per value by what holds the records.** A count
per value of a column is counted on the step that holds the records (`step_columns`,
then `count_step_by_column`); when no step holds them the question is a build and
the count follows it, through a transform when the records are a result's members;
`count_by_column` counts only one catalog search's whole result, unchanged, by a
search name the catalog lists (`ai/lead/_lead_count_rules.py`). Both step tools are
reads every turn reaches.

No OrthoMCL attribute offers `byValue`, so on OrthoMCL every count of a record
type column is a word cloud.

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
it; the tally refuses it by name. A column the tool server cannot count is refused
with the first 20 columns that can pass, those the site counts by value and the
genome code columns, never a column already refused on that step in the same Lead
pass, and the number left out; every other refusal names `step_columns`.

**Only a 4xx is a refusal, and a refusal is not a count of 0.** The client raises
`WDKError` on a failed report. A 4xx refuses the column with the site's HTTP status
and keeps it out of what the pass offers again; a 5xx, a timeout or a connect error
fails the call and refuses no column. A report of 0 records is a tally of 0. A
report whose records all lack a value refuses the column: WDK counts only the
records with a value, so the report's `subsetSize` is the step and the bins hold the
rest.

**Genome codes are named.** When every counted value is a genome code, each row
carries the genome's name as its `label`, and the card shows it beside the code.

**The tally keeps its `top` largest rows**, states the total and the number of
values, and its card links the step on the site (`ColumnTally.step_url`, the
strategy's page at that step). Each row, the total and the number of values are a
`TallyFact` the card draws; the note beside it writes none of them and may name the
genome a row leads with. A step tally carries the step it counted, and the facts
carry the strategy's result step; a tally of another step says so in its title
(`TallyFact.heading`).

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
