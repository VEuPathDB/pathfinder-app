---
type: Backlog
title: A built step is counted by a column
description: The Lead's count_by_column counts one catalog search's records by a column, without a step, so a question that counts a transformed result (singleton ortholog groups per organism) has no tool; the byValue reader VERIFY uses on steps becomes a Lead tool for a built step.
tags: [lead, tools, tally, orthomcl]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: proposed
---

# A built step is counted by a column

## What happens

"Which organisms in OrthoMCL have the most singletons (ortholog groups with one
protein)?" The turn built `GroupsBySequenceCount` with a count of 1 (523,795 groups)
and then stated that no step can count them by taxon. The question is answerable on
the site: Transform Groups to Proteins (`FromGroups`) gives the one protein of each
group, and that step's records counted by organism give the ranking.

`ai/tools/standalone/column_tally.py` (`count_by_column`) counts "one catalog search's
records by each value of one column, without a step", so it cannot count a transform's
output. `_step_columns.py` already reads a step's column with the byValue reporter,
but only VERIFY's toolset (`ai/tools/toolsets/verification.py`) holds it.

## Change

1. A Lead tool counts a built step's records by one column, top values first, through
   the byValue reader that `_step_columns.py` uses.
2. The Lead's guidance names the pattern: a count over the members of a result
   (proteins of groups, genes of a list) goes through the transform to the members,
   then the count.

## Done when

The singleton question builds count, transform and count-by-organism, and answers
with the top organisms and their counts from the site; a unit test covers the tool on
a recorded byValue answer.
