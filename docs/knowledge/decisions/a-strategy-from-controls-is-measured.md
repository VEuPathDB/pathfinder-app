---
type: Decision
title: A strategy from controls is measured, and every number on its card is a WDK count
description: The separate_controls durable tool takes a positive and a negative gene list, a mode and a request budget; the tool server measures candidate searches from five sources with one real intersection each, keeps the ones whose returned controls beat chance, assembles a greedy AND/OR/MINUS and reads the tree back from the site. PathFinder offers the result on its own card, builds the measured spec on a yes with no model in between, attaches the controls to VERIFY, and shows each criterion's contribution by set algebra. Model-estimated scores, candidates built outside WDK, a fixed candidate list, propose_changes as the adoption, two intersections per candidate, the unpersisted report, one scalar score, an exhaustive search, a genome population read and literature search in the worker were rejected.
tags: [separation, controls, durable, evidence, strategy, wdk]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

**The run.** `separate_controls` (`ai/tools/standalone/separation.py`) is a
durable, approval-gated Lead tool. It takes two gene lists, a mode (`exact`:
every positive and no negative; `similar`: every positive in a result whose
returned controls are rich in positives), up to eight literature queries each
with the reference it was read from, and a budget. The budget is an estimate of
WDK requests: one measurement is about ten, the GO and pathway enrichment about
34, the confirm read `4n+6` for `n` leaves, and the run holds the read of the
largest tree back first. The default is 600, between 200 and 2000.

**The measurement** belongs to the tool server (`veupathdb_mcp.separation`),
because it reads WDK searches, parameters and the semantic index. It resolves
both lists, uploads the controls as one dataset, collects candidates from five
sources (the thread's own leaves, the Lead's literature queries, the site's GO
and pathway enrichment of the positives, the positives' product phrases, and the
catalog searches that bind from the organism alone), skips each one WDK cannot
intersect with a gene list (WDK-MAP-010), and measures each survivor with one
intersection against the shared dataset. Every score is the count of a real step.

**Informativeness.** A measured candidate `informs` "recovering" when its
returned controls hold more positives than chance allows, by the exact
hypergeometric tail under `INFORMATIVE_P_VALUE`, "excluding" when they hold more
negatives, and "neither" otherwise. Only recovering candidates cover and
intersect, only excluding ones are subtracted (exact mode), and a candidate that
informs neither is measured and never enters a tree. The statistic has one
implementation, `veupathdb_mcp.separation.hypergeometric_log_sf`; the evidence
card's enrichment row reads the same function.

**The assembly** is greedy: cover the positives by UNION, most new positives
first; then in exact mode remove admitted negatives by INTERSECT with a
recovering candidate that keeps every recovered positive or MINUS of an excluding
one, most negatives first; in similar mode only INTERSECT. A tree holds at most
six leaves. The set algebra only chooses: the run then builds the assembled tree
as one internal strategy and reads its root and its controls back, and that read
is what the offer states. `predicted_matches_read` records whether the two
agreed.

**The offer** (`domain/separation.py`, built by `services/separation/offer.py`)
is the measured tree as an `OperationalSpec`: each leaf a criterion bound to the
candidate's search and wire parameters, with a `ControlsRationale` holding the
counts its own step returned, the right input of a MINUS an `exclude` criterion.
Its card question is written from the site's read, and the adoption tool takes
the task id alone. A literature reference stays on a criterion only when a read
of the message returned it.

**The adoption.** `adopt_separating_strategy` is a card like `propose_changes`.
A yes clears a strategy the thread holds through the path `clear_strategy` runs,
so a revert restores it, then builds the offer's spec through `build_the_minted`,
the body `build_strategy` runs. The spec is minted and checked before the clear, so
an offer the build refuses leaves the strategy standing. It saves the controls as a control set with source
`separation`, and attaches them: VERIFY's work order names every attached control
and runs `run_control_tests_on_step` on the root with exactly those ids, so the
evidence card holds the site's own read of the adopted strategy. A no ends the
turn with no model call, records the card as declined, and keeps the offer.

**The ablation.** Each criterion's contribution is read by dropping its leaf and
evaluating the rest of the tree over the measured control sets: the positives
only it recovers, the negatives it alone removes, and their opposites. It costs
no WDK request, and it is a prediction from the measured sets, as the assembly
is; the confirm read covers only the whole tree.

**What the Lead reads.** The model is answered with the run's brief
(`domain/separation_brief.py::brief_of`): the summary, the card's question, the offer's counts
and each criterion's, the informative and skipped counts, and the task id. It
names no gene. The whole report rides the `data-separation-result` part.

**Claims.** A reply may cite the offer's read and each leaf's own counts: the
turn contract backs a control count with the offer the turn's card carries and
the offer the thread adopted (`AttachedControls.task_id`), beside the turn's
control tests and the last check's card. An earlier offer backs nothing.

# What was rejected

- **Model-estimated scores**: a model guessing how many positives a search
  holds cannot be checked and drifts between runs. The model's inputs are the
  lists, the mode, the budget and the literature queries; a query is a
  hypothesis the counts accept or reject.
- **Building candidates outside WDK** from a downloaded annotation file or the
  semantic index's text: the strategy runs on the site, and a local copy
  disagrees with the site the day the site updates.
- **A fixed candidate list per site**: the searches are a property of each
  deployment, a list goes stale, and it cannot hold the thread's searches or a
  paper's hypothesis.
- **`propose_changes` as the adoption**: its yes re-derives the edit from prose
  through FRAME, so a model would re-bind the measured parameters.
- **Two intersections per candidate**, one per control list: one dataset of all
  the controls and one intersection read both lists.
- **The unpersisted report per candidate**: it reads every row of a search's
  answer, where the intersection reads at most the controls.
- **One scalar score for both modes**, such as the sweep's MCC: exact mode is
  lexicographic (every positive, then no negative, then size), and a scalar
  trades a negative for positives.
- **An exhaustive minimal conjunction**: minimum set cover is NP-hard, and an
  optimum no read confirmed is a prediction. Greedy plus the confirm read reports
  what the site returns.
- **A genome population read for the ranking**: for candidates that recover
  every positive the genome-level tail orders as the result size does.
- **Literature search in the worker**: the research server is the turn's tool
  source, and turning a paper into catalog words needs the model the worker does
  not run. The Lead reads and passes queries with their references.
- **A yes-or-no informativeness flag**: it cannot tell a candidate rich in
  negatives, which a MINUS needs, from one that tells nothing.

# Where it lives

`domain/separation.py`, `domain/strategy/step_rationale.py`
(`ControlsRationale`), `services/separation/`, `services/evidence/separation.py`,
`services/evidence/control_enrichment.py`, `ai/tools/standalone/separation.py`,
`jobs/impls/separate_controls_impl.py`, `ai/lead/lead_adoption.py`,
`ai/graph/_lead_offers.py`, `ai/graph/_lead_durable.py`, `ai/lead/verify_dispatch.py`,
and in the web `features/conversation/content/parts/DataSeparationResult.tsx` and
`SeparationCard.tsx`. The live check is
`apps/api/src/pathfinder/tests/live/test_a_strategy_from_controls.py`.
