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
in code.

An `unchecked` check names why in `why_unchecked`. `no_check` is a requirement
kind or a step property with nothing to compare on the site; it never blocks
the verdict. Once requirements are typed, a hard requirement that is untyped or
that no criterion links is unchecked the same way and shown "not verified"
([an unlinked requirement is not verified and never blocks](an-unlinked-requirement-is-not-verified-and-never-blocks.md));
until then a hard stated requirement its grounding marks ungroundable or
substituted fails its check (`domain/requirement_checks.py::grounded_check`). `site_unanswered` is a read the site did not answer: the strategy
read, a column read, the organism count, or a count the strategy read leaves
out. Any such check makes the verdict not checked: `success` is false, nothing
fails, the disposition stays `done` with no handoff, the reason says the site
did not answer, no memory is written, and the card and every summary say the
site did not answer instead of a pass or an objection.

`site_refused` is a site that answered the turn's other reads and refused one
reporter it advertises with an HTTP status. On QA PlasmoDB the step column
reporter `byValue` answers 500 on `organism` and on `primary_key` although the
record type lists it for both, so the organism count is refused while the
strategy read answers. A refused check never blocks the verdict, and its card
row says the site refused the count. Only a transport failure, a timeout or a
lost strategy read is `site_unanswered`. A root of at most `PAGED_RECORDS`
(2,000) records is counted from one page of its standard report by
`organism_full`, the genome name in full, under the view filters the step's
own count uses (`representativeTranscriptOnly` on a transcript step), so the
total is the root's count (`services/experiment/paged_tally.py`); the column
reporter is not sent. A larger root is counted by the column reporter. A
server error from a reporter is held per site and reporter for
`REFUSAL_LIFETIME_SECONDS` (one hour) in the process
(`services/experiment/reporter_refusals.py`), and while it is held no turn
sends that reporter to that site; the check is `site_refused`.

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
- **Passing a verdict the site did not answer.** With the strategy read lost,
  no check can fail, so a verdict computed from failures alone passes a strategy
  nothing checked. An unanswered read is a typed reason, not a failure, because
  the strategy is not shown wrong either.
- **Failing an organism requirement whose words name no organism the strategy
  selects.** An organism a request names can be the target of an ortholog
  pattern and not the organism of the result, so such a requirement is
  `unchecked`.

# What would prove this wrong

`tests/unit/domain/test_site_checks.py` holds each check kind on recorded WDK
bodies, `tests/unit/ai/lead/test_a_verdict_is_computed_from_the_site.py` the
recorded singleton ranking that passes over an objecting checker, a value the
site holds otherwise and a strategy read the site did not answer,
`tests/unit/ai/lead/test_a_second_organism_fails_the_verdict.py`
a step whose organism column holds a second organism,
`tests/unit/ai/lead/test_a_refused_organism_count.py` a refused organism count
counted from the records of a small result by gene, left refused on a large
one and not sent again while the refusal is held, and
`tests/unit/ai/lead/test_verify_dispatch_digest.py` a checker that objects to a
passing check.
