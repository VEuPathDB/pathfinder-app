---
type: Decision
title: A step with no countable column names the transform that reaches one, and a limit stands only where none does
description: step_columns answers reach and transforms from the site's catalog (veupathdb-mcp StepColumns.transforms), the turn records each read that named a transform, and the turn contract refuses a reply that leaves that count unmade unless it asks or offers a card; a requirement the check found unmet is unmet in the ledger, lets the build change the tree after the check and never ends the turn complete. A hardcoded transform table, reading limit words in the reply and a prompt rule alone were rejected.
tags: [lead, tools, tally, contract, verification]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

**The column read says how to reach a countable column.** veupathdb-mcp
`list_step_columns` fills `StepColumns.transforms` with `transforms_from(record_types,
record_type)`: each search of the site's catalog whose
`allowedPrimaryInputRecordClassNames` holds the step's record type and that takes no
second input, the record type it produces and the countable columns of that record type
and of its own search. The Lead's `step_columns`
(`ai/tools/standalone/step_tally.py`) answers `reach`: `step` when a column of the step
that matches can be counted, `transform` when none can and a transform reaches a
countable column, `none` when no transform does. Beside `transform` and `none` it lists
`transforms` (`domain/column_reach.py::TransformReach`), each with its countable count
and the columns that match the asked name, or else its first twenty countable columns.
A genome code column that only a word cloud counts is countable on the produced record
type as it is on the step (`services/experiment/step_tally.py::step_reach`).

**A reply never leaves a reached count unmade.** Each read that answered `transform` or
`none` is a `StepReach` on `TurnMarkers.column_reaches`, with the number of tallies the
turn held when it answered. A `transform` read that no tally followed is
`TurnRecord.unfollowed_reach`, and the turn contract's `unfollowed_reach` rule refuses a
reply over it that records no question and is no card, naming the transform, the record
type and its columns. The rule reads the typed read, never the reply's words, so "the
site cannot" stands only beside a read that answered `none`.

**A requirement the check found unmet is unmet.** A requirement gap of the standing
verdict with status `unmet` (nothing in the strategy answers it) makes the matching
constraint of the ledger `ungroundable` (`ai/lead/derive.py::_as_checked`), so a hard
requirement the researcher stated blocks. The same gap makes
`VerificationDigest.blames_the_tree` true, so the build may change the tree after the
check and the verify delta drops the card-only next step. The `unmet_requirement` rule
refuses a reply that ends the turn `complete` while a requirement blocks. That the reply
never calls the strategy correct is the one part no typed signal carries, so the Lead's
instructions say it beside the Constraints rule.

# What was rejected

**A table of transforms per record type.** The catalog names them on every site, and a
table drifts with the site's model.

**Reading "cannot" in the reply.** A word list refuses a true sentence and misses a
paraphrase; the read the turn made says whether the count is reachable.

**A prompt rule alone.** The Lead had read the transform and the tool's docstring named
the path, and it still declared the count impossible.

# Anchor

`veupathdb-mcp: src/veupathdb_mcp/wdk/column_counts.py`,
`ai/tools/standalone/step_tally.py`, `ai/lead/limit_messages.py`,
`ai/lead/turn_contract.py`, `ai/lead/derive.py`, `ai/graph/state.py`. Guarded by
`tests/unit/ai/tools/test_a_step_names_the_transform_that_reaches_a_column.py`,
`tests/unit/ai/lead/test_a_count_a_transform_reaches_is_made_or_offered.py` and
`tests/unit/ai/lead/test_a_requirement_the_check_found_unmet_is_unmet.py`.
