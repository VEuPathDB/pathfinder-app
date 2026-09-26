---
type: Decision
title: The tools that change a strategy are hidden until this turn is classified as one that asks for a change, and each phase tool until its precondition holds
description: A pydantic-ai `PrepareTools` capability drops every tool but the always-on read set until the turn classifies its own message, then drops the building tools unless the classification asks for a build, then drops the phase tools whose precondition the ledger, the live graph and this turn's record do not meet. The instruction-only alternative was rejected because two measured runs already ignored it, and a gate that can dead-end is rejected too: `classify_user_intent` is always on the list, so a misclassified turn is corrected inside the same run.
tags: [agents, lead, intent, cost]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# The decision

Two `IntentClassification` values name a turn that asks for no strategy:
`context_statement` ("I'm investigating virulence factors in Leishmania major")
and `memory_request` ("Please remember for future sessions: ..."). Six name a
turn that does: `new_strategy`, `extend_strategy`, `edit_strategy`,
`clarification_response`, `slot_answer`, `approval`. The set lives in
`ai/lead/intent.py::BUILDING_INTENTS`.

`ai/lead/intent_gate.py::apply_tool_preconditions` is registered on the Lead as
`PrepareTools[LeadDeps]`. It runs on every model step and applies three
filters in order.

**Until this turn is classified**, the list holds `UNCLASSIFIED_TOOLS` and
nothing else: `classify_user_intent`, the two reads of what the thread holds
(`read_ledger_section`, `get_live_strategy_state`), the two literature reads
(`web_search`, `literature_search`) and `remember`. A turn is classified when
`LeadDeps.intent` is set AND `PipelineState.turn_markers.intent_classified` is
true for the message this turn answers, so a classification recorded by an
earlier message unlocks nothing.

**Once classified**, a turn whose classification is not a building one loses
`BUILDING_TOOLS` - the five dispatch tools plus `open_eda_analysis`,
`set_eda_filters`, `run_eda_compute` and `create_eda_step`.

**Once building**, each phase tool answers for its own precondition
(`unmet_preconditions`):

- `frame_problem`: gone once a frame dispatch ran this turn, and whenever the
  live graph holds a step, whatever the classification: a strategy with steps
  is changed through `edit_strategy`, and an answer to a question asked over it
  reaches the edit's work order. A `consult_user` call that comes back with
  answers clears the marker, because those answers are new requirements to
  frame against.
- `build_strategy`: gone once the live graph holds a step. The `ModelRetry` in
  the tool stays as the backstop for a graph that changes mid-turn.
- `verify_strategy`: absent until the live graph holds a step (a recorded
  `BuildOutcome` is not a strategy), and absent again once a verification of
  this turn reported success.
- `create_eda_step`: absent until `preview_eda_subset` counted the open
  analysis this turn, so an exported count is one that was measured.

Every gated tool's description states its own precondition ("Available
once ..."), so its absence explains itself. The markers are
`ai/graph/turn_records.py::TurnMarkers`, keyed by `user_message_id`: a resumed turn
(an approval answer, a durable result) carries the same message id and keeps
what the turn already did, and a new user message starts from an empty record.

**A misclassification degrades; it never dead-ends.** `classify_user_intent`
is on the list at every step, and `PrepareTools` reads `LeadDeps` live, so a
classification corrected inside the same run puts the tools back on the very
next step - one wasted step, not a refused turn. The Lead's rules name that
path as the FIRST action when the message asks it to run, rerun, build, add or
create and the building tools are absent, and they forbid both telling the user
that a tool is unavailable this turn and asking the user to retry the request.
`classify_user_intent` states that such an imperative - a bare "yes, do it"
typed while one of the assistant's cards waits, and a retry after a failed
task, included - is a building classification and never a `follow_up_question`.
An offer is never accepted from prose: the yes answers the card through
`_lead_offers.answer_to_the_offer`, and a bare yes after a declined offer with
no card waiting ends on `DECLINED_OFFER_REFUSAL`
([an offer is a card](an-offer-is-a-card-not-prose.md)).
`tests/unit/ai/lead/test_intent_gate.py::test_a_corrected_classification_unhides_the_building_tools`
pins the unhiding,
`tests/unit/ai/lead/test_intent_gate_preconditions.py` pins one predicate per test,
and `tests/unit/ai/lead/test_lead_instructions.py` pins the
guidance.

`ai/lead/memory_candidates.py` follows the same rule: a turn whose recorded
classification is not a building one contributes no strategy memory, so a
preference request cannot leave a strategy memory summarised by the user's
sentence.

# What was rejected

**An instruction alone.** The cataloged item proposed either a mechanical gate
or one more sentence in the Lead's prompt. Two measured runs on the default
provider already framed, built and verified a strategy for a bare context
sentence and for a preference request, so a rule the model may or may not
follow was not enough. The instructions that the gate enforces are deleted;
what stays is the intent behind them - the count-honesty rules, the
`consult_user` rule, and the misclassification degrade rule.

**A gate that can dead-end.** A hidden tool the Lead cannot ask back is a
turn the user pays for and gets nothing from: the measured refusal, "the
analysis controls ... are not available in this turn. Please retry this
request.", cost two turns. Every filter here leaves the tool that reopens it on
the list: `classify_user_intent` before a classification, `edit_strategy` when
`build_strategy` is gone, `preview_eda_subset` when `create_eda_step` is gone.

**Carrying the previous turn's classification.** The gate first read
`LeadDeps.intent`, seeded from the prior turn's recorded intent, so a turn that
built left the building tools unlocked at the next turn's entry and "classify
first, every turn" was unenforced. It was kept while the deterministic provider
might not re-classify; its arcs classify once per turn now
(`ai/models/mock/lead_flow.py::run_sequence`), and a turn that resumes a parked call
is the same turn by message id, so the turn-scoped marker costs no run a
duplicate classification.
