---
type: Decision
title: An offer is a card, not prose
description: The Lead offers further work on a proposal card (`propose_changes`) that parks the turn like a consult. A yes runs the edit from the card's own changes and the researcher's note, a no ends the turn with no model call and records the declined card on the ledger, and the turn contract refuses any reply that ends on a question it did not record. A contract rule for approval turns alone and a proposal kind on the runtime's consult question were rejected.
tags: [agents, lead, honesty, approvals, contract]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

An offer of further work on the strategy is a card the researcher answers, never a question the
Lead asks in prose.

- **The card.** `propose_changes` (`ai/lead/lead_proposal.py`) is a Lead tool with
  `requires_approval=True`. Its one argument is a `Proposal` (`ai/lead/proposal.py`): a
  one-sentence `question` and a list of `proposedChanges`, each a plain sentence the edit
  realises. The Lead's reply is an argument of the card call and streams before the card; the
  turn parks on the approval exactly as a `consult_user` turn does. The web draws it as
  `ProposalCard` (the question, the changes, Yes, No and a note field that is always shown).
- **Yes.** The approval resumes the run and pydantic-ai executes the tool body, which dispatches
  `run_edit` with `Proposal.brief(note)` as the edit's work order: the question, every change,
  and the note the card sent as a `data-user-question-answers` answer. The model never has to
  remember the offer: the parked call's arguments are the state. The body draws the edit's
  dispatch card itself (the tool is not a sub-agent tool, so its own chunks stay on the wire),
  sets `TurnMarkers.accepted_proposal`, and returns the `EditDelta`; the Lead then answers as
  after any edit. `turn_builds` is true for a turn whose researcher accepted a card, so the
  verification the contract asks for is reachable. On a thread with no strategy the body refuses
  with the accepted brief and sends the Lead to `frame_problem` and `build_strategy`.
- **No.** `_lead_offers.answer_to_the_offer` reads the denial, and `turn_ends_before_the_run`
  closes the card as denied (`tool-output-denied`) and ends the turn with no model call. `final_reply`
  writes nothing for it, so the reply already on screen stays the turn's reply and the thread's
  `lead_next_state` and open questions stay as they stood. The denial's reason is the note.
- **A run is its own card.** A sweep, a separation or a control test is never offered on a
  `propose_changes` card, whose yes runs an edit. The Lead calls that tool, whose own approval is
  the card, with the controls the conversation holds: a saved control set by its
  `control_set_id`, which the worker reads whole, or the ids the researcher typed. A sweep that
  names no control, both kinds, or a parameter by its label is refused before the card.
- **Typed answers.** Every Lead card follows one rule, `ai/graph/_lead_offers.py::answer_to_the_offer`:
  a typed approval phrase (`is_pure_approval`) accepts the card as a click on yes would, except a
  `consult_user` card, which only its answers answer. Any other typed message declines the card
  and reaches the Lead as the next message; when the card is an offer (`propose_changes`,
  `adopt_separating_strategy`) the decline is recorded as a clicked no is. A clicked no on any
  card that is not an offer resumes the run with the denial. `propose_changes` is in
  `UNCLASSIFIED_TOOLS`, so a typed yes validates before the new message is classified.
- **The record.** A declined offer is `StrategyDomainState.declined_proposal`, carried on the
  ledger (`InvestigationLedger.declined_proposal`, a `## Declined proposal` block in the summary)
  until a later card is accepted. A bare yes on a later turn does not accept it: when a declined
  offer stands, no parked call is re-entered and no question is open,
  `intent_gate.bare_assent_refusal` ends the turn on `DECLINED_OFFER_REFUSAL` ("You declined the
  last offer. Say what to change, or ask me to offer it again.") with no model call.
  A clicked no on a removal card (`delete_step`, `clear_strategy`) withdraws the requirements
  the message that asked for it recorded (`TurnMarkers.requirements_added`), so a later check
  never reports the declined removal as unmet.
- **The contract.** `_unrecorded_question` refuses a reply whose prose ends with a question - the
  prose, with trailing whitespace and closing emphasis, code, bracket and quote marks removed,
  ends with `?` - whatever `next_state` says and whether the turn framed, unless the reply
  records `asked_questions` or the researcher answered a card (a consult or an accepted proposal)
  under this message. The correction sends an offer to `propose_changes`, a question for a value
  to `asked_questions`, and anything else to a reply without a question. The earlier trigger
  stands beside it: a framed turn waiting on the user that asks anywhere in its prose and records
  nothing is refused with the `asked_questions` correction.
- **The reply is an argument of the card call and streams before it.** Every call that ends a
  Lead turn on a card - `propose_changes`, `consult_user`, `adopt_separating_strategy`,
  `optimize_search_parameters`, `separate_controls`, `clear_strategy` and `delete_step`
  (`ai/lead/card_contract.py::CARD_TOOLS`) - takes a required `reply` (`ai/lead/card_reply.py`,
  at least one sentence after whitespace is stripped), so a call without one is refused by the
  schema before any card. pydantic-ai ends a run on an approval with `DeferredToolRequests` and
  runs no output validator on it, so `card_contract.py::hold_the_contract_on_a_card`, a
  `HandleDeferredToolCalls` handler on the Lead, reads the replies of the response's card calls,
  builds a `LeadResponse` from them and reconciles it against the `TurnRecord` with
  `ends_on_a_card` set: the count claims, the named searches and every other rule of a typed reply
  apply, and `unrecorded_question` and `unfinished_work` stand because a card asks its own
  question. On a mismatch every card of the response is denied with the correction and the Lead
  answers again in the same run; the latch is `contract_refused`, shared with the typed reply.
  `ai/graph/_lead_card_hold.py::CardHold` holds every chunk of each new card until the cards are
  denied (all dropped) or the run ends; each card is then written after its reply as text, and
  any free text beside a card is dropped, so the reply the contract read is the only one the
  researcher reads. A call a resumed run re-announces passes, with no second reply. The durable
  cards forward `reply` to their jobs, and the worker impls take it in their ignored keywords.

# Why

A turn that built a five-step strategy and verified it ended "Would you like me to refine the
strategy to enforce strict 3-hour specificity and independently verify 1:1:1 syntenic
orthology?" with `next_state=complete` and nothing recorded. The researcher answered "Yes"; the
classifier read an approval; the Lead found no pending work in the ledger, read the strategy
and the verification section, and restated the same four genes. Nothing was dispatched, because
the offer existed only as prose and the old rule fired only for a framed turn waiting on the
user. The fix is to make the offer state: a card holds the exact changes, so the yes carries
them, and the contract refuses the prose form everywhere.

The reply was first the text the Lead wrote beside the card call. Measured on 2026-09-24 with
`openai:gpt-5.6-luna`, text output allowed: the `/analyze` turn parked on
`[thinking, tool-call propose_changes]`, and a sweep turn told by the contract to write its reply
answered again with only `[thinking, tool-call optimize_search_parameters]`. The researcher got a
card and no answer. A required argument is written every time, because the schema refuses the
call without it.

# What was rejected

- **A contract rule that refuses a card with no text beside it.** The model answered the
  correction with the same bare tool call, so the rule cost one model call and wrote nothing.

- **A contract rule for `approval` turns.** Refusing an approval-classified turn that dispatches
  nothing patches the second turn of one incident. The offer is still lost when the first turn
  ends, and the Lead still has to reconstruct from prose what "yes" accepted. A card records the
  offer when it is made.
- **A `proposal` kind on `ConsultQuestion`.** The question kind is a closed literal owned by the
  runtime (`assistant_core.graph.turn_state`), and a consult question has no field for the
  changes a yes makes. A sibling tool in the same approval family carries its own typed argument
  and needs no runtime release.
- **Running the Lead on a no.** There is nothing for it to say: the reply is already on screen,
  and a model call would spend a turn restating it.
- **Checking the parked turn after the run, in `_lead_turn`.** The run is over by then, so a
  refusal needs a second run started from the parked history, and the approval request is
  already among the run's chunks. The handler runs before either.
- **Refusing a response that holds a card beside another approval.** It is a second refusal rule
  the Lead would have to learn, for a shape its instructions give it no reason to produce: a card
  ends a reply that offers further work, and `delete_step` or `clear_strategy` carries out a
  removal the researcher asked for. The hold keeps such a response correct: nothing is lost, and
  the correction is read one answer later.
- **The note on its own field of the approval.** The note on a yes rides the consult answer part
  the web already sends, and the note on a no rides the denial's reason; no new wire shape was
  added.
