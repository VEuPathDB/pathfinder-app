---
type: Decision
title: An unlinked requirement is not verified and never blocks
description: A hard requirement the verdict has no typed way to compare, because it is untyped or no criterion links it to a parameter or an analysis field, gives an unchecked check with its reason, is shown to the researcher as "not verified", and neither passes nor blocks the verdict. Grounding such a requirement by reading its words with patterns, and blocking the verdict until a link exists, were rejected.
tags: [verification, requirements, trust]
generated: { by: claude-code/opus-5.5, at: 2026-11-01T00:00:00Z }
status: stable
---

# What was decided

[A verification verdict is computed from the site](a-verification-verdict-is-computed-from-the-site.md)
runs one typed check per requirement. Requirements are typed data
([a requirement carries a typed value of its kind](a-requirement-carries-a-typed-value-of-its-kind.md)),
and a check compares a requirement only through what the strategy binds for it:

- An untyped requirement (a stored requirement read back from before the typed
  model, or one the classifier could not type) gives an `unchecked` check with
  `why_unchecked: untyped`.
- A value requirement (percentile, fold change, significance, count) that no
  criterion links to a parameter or an analysis field gives `unchecked` with
  `no_value_to_compare`.
- A text, ortholog or property requirement no criterion links gives `unchecked`
  with `no_step_states_it`. A linked property shows "answered by step" and the
  step's title; a linked text or ortholog is compared with the value the site
  holds.

The grounding marks such a requirement with the status `not_verified` and the
reason (`GroundedConstraint.unverified`, held to the status by a validator), and
`requirement_checks.grounded_check` carries the reason as `why_unchecked`. It is
never a pass and never a failure, so it does not block the verdict, the same
rule `no_check` follows for `comparator`. The ledger renders it "not verified",
the evidence card's check row reads "Not verified", and the web constraints
section shows a "not verified" pill, never "grounded". The researcher sees which
requirements nothing compared.

Every kind follows this rule
([a requirement carries a typed value of its kind](a-requirement-carries-a-typed-value-of-its-kind.md)):
a value with no typed field is `untyped`; a percentile, fold change,
significance or count with no linked parameter, analysis cut or step count, a
text linked with no parameter and an ortholog with no linking transform are
`no_value_to_compare`; a data type, text, ortholog or property no criterion
links is `no_step_states_it`; a record type or an organism with no value is
`untyped`.

# What was rejected

**Grounding a requirement by patterns over its value.** The value is model
text; a regex that finds "top 5 percent" or "p < 0.05" in it decides what the
site is held to, and a value worded another way grounds differently or blocks.

**Blocking the verdict until every hard requirement is linked.** A requirement
the strategy has no parameter for is a fact about the site, not an error in the
strategy; blocking on it fails a correct build, which is the fault the computed
verdict was written to remove. Showing it "not verified" tells the researcher
the same thing without calling the strategy wrong.

**Passing an unlinked requirement.** Nothing compared it, so a pass would claim
a check that did not run.

# What would prove this wrong

The unit tests the redesign adds per kind: an untyped requirement, an unlinked
value requirement and an unlinked text requirement each give `unchecked` with
their reason and a passing verdict over an otherwise passing strategy, and a
linked one is compared with the value the site holds.
