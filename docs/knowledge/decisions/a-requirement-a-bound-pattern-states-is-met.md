---
type: Decision
title: A requirement a bound phyletic pattern states is met
description: A FRAME report that a requirement is unmet carries the requirement as a phyletic pattern term, the term must match the shape the classifier typed on the requirement, and the report is dropped in code when a term every group of the bound pattern meets selects the same groups on the site's taxonomy; the drop is a gap, a marker the Lead reads and a reference its reply must write. Comparing the requirement's words with the expression's reading, letting FRAME drop the report itself, and asking the researcher on the drop card were rejected.
tags: [frame, orthomcl, phyletic, requirements, consult]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

Two typed sources must agree before a requirement counts as met:

- The Lead's classification types a requirement about which genomes hold a group's proteins
  with `Constraint.genome_shape` (`GenomeShape`: the scope of genomes, the measure, the
  condition and the value, or a compare's reading, condition and factor), from the message.
- FRAME's `RequirementReport.clause` is the requirement as one `build_phyletic_expression`
  pattern term in JSON text, parsed at the check so FRAME's output type checks only shape.

While a criterion binds an expression this conversation built, the output validator
`hold_the_reports_to_the_bound_patterns` (`ai/agents/frame_clause_checks.py`) holds each
`site_has_no_search` or `stand_in_bound` report on a shaped requirement:

- A clause that does not parse, or that does not match the requirement's shape
  (`matches_shape`, `domain/strategy/pattern_clauses.py`, which builds the shape's term over the
  clause's codes and compares the groups both select), is refused within the shared refusal
  bound. At the bound the report stands, with a `clause_unread` or `clause_mismatch` gap.
- A report with no clause is asked for its clause once. The ask never tells FRAME to leave the
  report out.
- A matching clause that a term of the bound pattern states (`states_clause`) marks the
  requirement met in the pass's state. Every result the pass returns then drops that report in
  code, writes a `report_dropped` gap and carries a `MetClause` in `FrameResult.met_by_clause`.
  The turn records it, and the reply contract (`unnamed_clause`) refuses a reply that does not
  write `[met:<n>]`, which renders the requirement and the term that meets it.

A requirement with no shape keeps its report, so the drop card asks as before.

# Rejected

- **Comparing the requirement's words with the expression's reading.** A reading is the
  library's prose, and its words change with the expression's length.
- **Letting FRAME leave a met report out on a retry.** Nothing would record the drop, and a wrong
  clause would retire a requirement the strategy does not meet without a trace.
- **Asking the researcher.** The drop card asks about a requirement the strategy already meets.
