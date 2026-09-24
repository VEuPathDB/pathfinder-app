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
  realises. The Lead writes its reply as text and makes the call in the same response; the turn
  parks on the approval exactly as a `consult_user` turn does. The web draws it as
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
- **No.** `_lead_turn._resolve_proposal` reads the denial, and `turn_ends_before_the_run` closes
  the card as denied (`tool-output-denied`) and ends the turn with no model call. `final_reply`
  writes nothing for it, so the reply already on screen stays the turn's reply and the thread's
  `lead_next_state` and open questions stay as they stood. The denial's reason is the note.
- **Typed answers.** A typed approval phrase (`is_pure_approval`) accepts the card. Any other
  typed message declines it and reaches the Lead as the next message, the same rule a sub-agent
  approval follows. `propose_changes` is in `UNCLASSIFIED_TOOLS`, so a typed yes validates before
  the new message is classified.
- **The record.** A declined card is `StrategyDomainState.declined_proposal`, carried on the
  ledger (`InvestigationLedger.declined_proposal`, a `## Declined proposal` block in the summary)
  until a later card is accepted. A bare yes on a later turn does not accept it.
- **The contract.** `_unrecorded_question` refuses a reply whose prose ends with a question - the
  prose, with trailing whitespace and closing emphasis, code, bracket and quote marks removed,
  ends with `?` - whatever `next_state` says and whether the turn framed, unless the reply
  records `asked_questions` or the researcher answered a card (a consult or an accepted proposal)
  under this message. The correction sends an offer to `propose_changes`, a question for a value
  to `asked_questions`, and anything else to a reply without a question. The earlier trigger
  stands beside it: a framed turn waiting on the user that asks anywhere in its prose and records
  nothing is refused with the `asked_questions` correction.
- **The text beside the card.** pydantic-ai ends a run on an approval with `DeferredToolRequests`
  and runs no output validator on it, so the reply the researcher reads - the text written in the
  same response as a `propose_changes` or `consult_user` call - would escape the contract.
  `ai/lead/card_contract.py::hold_the_contract_on_a_card` is a `HandleDeferredToolCalls` handler
  on the Lead: it runs inside the run, before the approval chunk (which the stream writes only
  from the run's final output), builds a `LeadResponse` from that text and reconciles it against
  the `TurnRecord` with `ends_on_a_card` set. A card asks its own question, so `unrecorded_question`
  and `unfinished_work` stand. On a mismatch the card is denied with the correction - an
  approval call accepts only an approval or a denial - and the Lead answers again in the same run,
  issuing the card again; the latch is `contract_refused`, shared with the typed reply.
  `ai/graph/_lead_card_hold.py::CardHold` holds the Lead's text and every chunk of each new card
  of the response until the cards are denied (all dropped, the denials with them) or the run ends
  (the text, then each card whole, in the order the cards began), so a refused reply never reaches
  the thread and no card reaches the web in pieces. A call a resumed run re-announces passes.
- **A card beside another approval.** The chunks of a call that is not a card, such as
  `delete_step`, pass the hold at once, so that call reaches the thread before the held text. The
  runtime parks on every approval of one response together, and a card is answered in the same run
  only when nothing else parks it: a card denied beside `delete_step` leaves the run parked on
  `delete_step`, with the text and the card dropped, and the Lead reads the correction beside that
  call's answer when the researcher answers it.

# Why

A turn that built a five-step strategy and verified it ended "Would you like me to refine the
strategy to enforce strict 3-hour specificity and independently verify 1:1:1 syntenic
orthology?" with `next_state=complete` and nothing recorded. The researcher answered "Yes"; the
classifier read an approval; the Lead found no pending work in the ledger, read the strategy
and the verification section, and restated the same four genes. Nothing was dispatched, because
the offer existed only as prose and the old rule fired only for a framed turn waiting on the
user. The fix is to make the offer state: a card holds the exact changes, so the yes carries
them, and the contract refuses the prose form everywhere.

# What was rejected

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
