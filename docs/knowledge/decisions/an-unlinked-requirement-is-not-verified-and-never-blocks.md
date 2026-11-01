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
runs one typed check per requirement. Once requirements are typed data
([backlog item 77](../backlog/requirements-are-typed-data.md)), a check compares
a requirement only through what the strategy binds for it:

- An untyped requirement (a stored requirement read back from before the typed
  model, or one the classifier could not type) gives an `unchecked` check with
  `why_unchecked: untyped`.
- A value requirement (percentile, fold change, significance, count) that no
  criterion links to a parameter or an analysis field gives `unchecked` with
  `no_value_to_compare`.
- A text or property requirement no criterion links gives `unchecked` with
  `no_step_states_it`. A linked one shows "answered by step" and the step's title.

An unchecked check is shown "not verified" on the card and in the facts. It is
never a pass and never a failure, so it does not block the verdict, the same
rule `no_check` already follows for `comparator` and `other`. The researcher
sees which requirements nothing compared.

The code still grounds a value requirement by reading its words with patterns
(`constraint_grounding`, `fold_grounding`, `PercentileRequest.parse`), and a hard
stated requirement those patterns cannot ground blocks
(`constraints.is_blocking`), until steps 7 to 13 of backlog item 77 land.

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
