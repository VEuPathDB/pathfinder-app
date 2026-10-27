---
type: Decision
title: A verification verdict is computed from the site
description: Every check runs a fixed set of typed checks over the strategy as the site holds it, one per typed requirement kind and per step property, and the verdict is success exactly when none of them fails; the checker model only reads sample records and writes notes. A model-judged verdict, with model-written requirement rows that became failing gaps, was rejected because it called correct answers unmet.
tags: [verification, evidence, wdk-alignment, requirements, trust]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: stable
supersedes: verify-reviews-the-intent-the-genes-and-the-sources.md
---

# What was decided

`run_verification` (`ai/lead/verify_dispatch.py`) runs the checks in code
every time, before the checker model runs (`ai/lead/verify_checks.py::site_checks`).
Each check is a `SiteCheck` (`domain/site_checks.py`): a kind, the subject it
checks, `pass`, `fail` or `unchecked`, and the site's answer as evidence. The
review on the digest and on the evidence card carries them as `checks`.

| Kind | What the site answers |
|---|---|
| `step_valid` | the `validation` WDK states on each step of the strategy read |
| `bound_values` | each step's `searchConfig` against the values the build pushed, in the wire form and the decoded form (`site_changes.values_the_site_holds_otherwise`) |
| `combine_counts` | each boolean combine's `estimatedSize` against its inputs': an intersection at most the smaller, a union between the larger and the sum, a minus at most the input it keeps |
| `result_count` | the root's `estimatedSize`; a root of no record fails |
| `organism` | the root's `organism` column counted by value over the whole step, against the organisms its WDK-marked organism parameter selects (`extract_output_organisms`); a requirement that names a selected organism carries the same result |
| `record_type` | the root's `recordClassName`, or every step's for a class the strategy passes through, against the classes the requirement's words name on the site |
| `expression_fit` | the first groups of a phyletic step judged against the expression as the site reads it |
| `tally` | a column tally this turn recorded on a step of the strategy, held as the recorded result |
| `data_type`, `statistical_threshold`, `fold_change`, `percentile`, `combination` | how the spec grounds the requirement (`constraint_grounding`), whose values `bound_values` holds to the site; a stated significance is compared with the cut the strategy binds |
| `comparator`, `other` | no deterministic check: `unchecked` |

The verdict is `success` exactly when no check fails, no word a criterion states
is unstated by every search, and the build put every step on the site with
records. The checker cannot write `success`, `disposition`, `reason`,
`failure_cause`, `gaps` or the checks: they are omitted from its schema and set
in code. A check the site does not answer, or a requirement kind with no
deterministic check, is `unchecked` and never fails the verdict.

The checker's remaining part is optional: it samples the root, reads up to
eight gene records and may cite sources; its prose and its sampled genes are
notes. The output validator still refuses a sampled gene, a source or a count
no read of the turn returned.

A stored verdict now lives in `StrategyDomainState.site_verdict`, so a verdict an
earlier build stored under `verification_digest` is dropped on load and the next
check writes it again ([a saved conversation outlives the build that saved it](a-saved-conversation-outlives-the-build-that-saved-it.md)).

# Rejected

- **A model-judged verdict.** The checker chose its checks, wrote a met or unmet
  row per requirement and set `success`, and an unmet row became a failing gap.
  On OrthoMCL the strategy built the 523,795 singleton groups, transformed them to
  proteins, and the turn's tally ranked Brachionus plicatilis first with 18,260;
  the checker still wrote the ranking unanswered, because the ranking came from a
  tally beside the strategy and not from a step. The code then needed a growing
  set of rules to hold the rows to the turn (questions dropped as rows, text
  queries held to the records, record-type rows rewritten), each of them shaped by
  one phrasing.
- **Keeping the rows as notes beside a computed verdict.** A card that shows a
  row "unmet" over a passing verdict contradicts itself in front of the
  researcher.
- **Running the control tests in code.** A control test is a durable job; its
  result stays a caveat, since a missed control measures recall, not whether the
  strategy states the request.
- **Failing an organism requirement whose words name no organism the strategy
  selects.** An organism a request names can be the target of an ortholog
  pattern and not the organism of the result, so such a requirement is
  `unchecked`.

# What would prove this wrong

`tests/unit/domain/test_site_checks.py` holds each check kind on recorded WDK
bodies, `tests/unit/ai/lead/test_a_verdict_is_computed_from_the_site.py` the
recorded singleton ranking that passes over an objecting checker and a value the
site holds otherwise, `tests/unit/ai/lead/test_a_second_organism_fails_the_verdict.py`
a step whose organism column holds a second organism, and
`tests/unit/ai/lead/test_verify_dispatch_digest.py` a checker that objects to a
passing check.
