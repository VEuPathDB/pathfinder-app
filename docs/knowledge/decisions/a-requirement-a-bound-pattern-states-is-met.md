---
type: Decision
title: A requirement a bound phyletic pattern states is met
description: A FRAME report that a requirement is unmet carries the requirement as a phyletic pattern term, and the report is refused when a term every group of the bound pattern meets selects the same groups on the site's taxonomy. Comparing the requirement's words with the expression's reading, and asking the researcher on the drop card, were rejected.
tags: [frame, orthomcl, phyletic, requirements, consult]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

A `RequirementReport` of `site_has_no_search` or `stand_in_bound` may carry `clause`, the
requirement written as one `build_phyletic_expression` pattern term in JSON text, parsed at the
check so FRAME's output type checks only shape. While a criterion binds an
expression this conversation built, the output validator
`hold_the_reports_to_the_bound_patterns` (`ai/agents/frame_clause_checks.py`) holds each such
report to the bound pattern:

- A report with a clause that the bound pattern states is refused, and dropped with a
  `report_dropped` gap once the refusal bound is spent. The report never reaches the drop card.
- A report with no clause is sent back once, with the expression's reading, so the pass either
  leaves it out or states its clause.

`states_clause` (`domain/strategy/pattern_clauses.py`) reads a term as the groups it selects:
each set as the genomes its codes cover, each bound as a span of counts over that set. A share is
a genome count over the set's size, an absence is a span of zero whatever its measure, and a
`none_of` of one presence is that absence. Only a term every group must meet states a clause:
the pattern itself and the terms of an `all_of`, never a term of an `any_of`.

# Rejected

- **Comparing the requirement's words with the expression's reading.** A reading is the
  library's prose, and its words change with the expression's length; a word match would hold
  on one shape of question and fail on the next.
- **Asking the researcher.** The drop card asks about a requirement the strategy already meets,
  which is the fault this rule removes.
