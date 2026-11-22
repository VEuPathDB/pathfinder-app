---
type: Decision
title: A multi-pick override stays a list all the way to the typed value
description: Serializing a list to WDK wire form at the tool boundary made the whole array one candidate option, so the model was told its own correct answer was invalid. The list now reaches the declaration's reader, which reads a multi-pick as a list of terms.
tags: [agents, parameters, wdk-alignment]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# What was decided

A multi-pick override stays a list until the parameter's declaration reads
it. The bind walk reads each override once, through the declaration
(`read_under_parents`, see
[a value is read by its parameter](a-value-is-read-by-its-parameter.md)), and
a multi-pick reads a list of terms. `_wire_overrides`, which encoded a list as
WDK wire form at the tool boundary, is deleted.

# The alternative that was rejected

Encoding early "because a multi-pick value goes on the wire as a JSON array".
That is true of the WIRE, and untrue of every layer above it. `_apply_override`
matches a value against the vocabulary; handed `'["20 Hour", ... "32 Hour"]'` it
looked for that entire string as ONE option, found nothing, and passed it
through. Validation then answered:

> Parameter 'samples_percentile_generic' does not accept
> '["20 Hour", "21 Hour", ... "32 Hour"]'

with a `validOptions` list containing every one of those hours. The model was
told its own correct answer was invalid, and offered to build 13 separate search
arms and union them instead.

The value reader always accepted a list. The type at the tool boundary was the
only thing in the way.

# Consequences

Two places genuinely need a scalar, and say so rather than guessing:

- **The vocab ledger** (`_sole_claim`). It exists to stop the two halves of a
  ref/comp contrast picking the same option. A 13-element selection claims no
  single option, so it takes part in no claim bookkeeping.
- **Filter params** refuse a bare list with the shape a filter takes. A filter
  clause selects members of ONE facet, and a bare list names no facet; a
  statement is a list of `{field, value}` objects (see
  [a filter clause is bound by its facet](a-filter-clause-is-bound-by-its-facet.md)).
  Failing loudly beats picking a facet on the model's behalf.

# Evidence

Observed: `gpt-5.6-luna`, same prompt before and after:

| | before | after |
|---|---|---|
| `set_criterion` failures | 4 | **0** |
| DeRisi criterion | unbindable | 13 hours bound |
| strategy | none | the built strategy |

Final: a large result protein-coding, intersected with a large result top-percentile trophozoite
and 81 `PF00069` kinases, giving **the intended genes**.
