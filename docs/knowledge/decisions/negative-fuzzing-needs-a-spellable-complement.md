---
type: Decision
title: Negative fuzzing is off only where the complement cannot be spelled
description: The conformance lane keeps negative-case generation on every operation whose request schema the canonical form can complement, and asks for positive cases only on the fifteen whose parameter-value union it cannot. Rejected - a project-wide positive-only switch, which deletes negative coverage from the whole OpenAPI gate, and derandomizing alone, which pins the refusal instead of removing it.
tags: [testing, openapi, transport, tooling]
generated: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
status: stable
---

# What was measured

`tests/integration/transport/test_openapi_schemathesis.py::test_openapi_conformance`
failed on one operation per run and a different operation each run:
`POST /api/v1/gene-sets` once, `POST /api/v1/conversations/step-counts` once,
nothing the third time. Every failure read the same:

```
schemathesis.core.errors.UnsupportedSchema: Schemathesis does not support
a `not` whose complement is not spelled out, below the document root
```

The server never answered 500, and neither the served nor the committed spec
holds a `not`. A negative case is drawn from the complement of a barred
keyword, so the generator writes the `not` itself
(`schemathesis/specs/openapi/negative/mutations.py`, `negate_constraints`) and
then asks the canonical form to spell the complement
(`schemathesis/generation/jsonschema/strategy.py::_not`). Where negation
declines it hands back a bar over its own input, and the draw is refused.

The barred schema was recorded at the refusal: the eleven-branch parameter
value union, `oneOf` over `StringValue` ... `InputStepValue`. Negating each
branch alone succeeds. Negating three of them together fails whenever the
three include both `NumberRangeValue` and `DateRangeValue`, which declare
`min` and `max` at `number` and at `string`. The minimal reproduction is two
branches that give two shared property names different types, plus any third
branch. Those two branches alone still negate; a third shared name tips them
on their own.

# What was decided

The lane keeps both generation modes. A predicate over the served spec
(`tests/_support/openapi_negation.py`) names the operations whose request
schema reaches a union the canonical form cannot complement - 15 of 94 - and a
per-operation `OperationConfig` asks those for positive cases only. The other
79 keep negative coverage. `GenerationConfig(deterministic=True)` makes the
draws reproducible.

The predicate asks the canonicaliser rather than restating it: it builds each
union as the one keyword a mutation bars, with the definitions it reaches, and
reports the unions whose `negate()` declines. An operation that stops carrying
one gets negative generation back with no edit.

# What was rejected

*A project-wide `modes=[POSITIVE]`.* It makes the lane deterministic by
deleting negative-case generation from the whole OpenAPI gate, including the 79
operations that never had the problem.

*`derandomize` alone.* It pins which operation is refused. The lane stays red,
reproducibly.

*Changing the parameter value models.* `min` and `max` are WDK's own field
names on the number and date range values, the eleven discriminants may not be
collapsed, and the models are the client library's, not this repository's.
