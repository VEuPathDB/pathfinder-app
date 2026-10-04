---
type: Decision
title: A turn keeps the classification that wrote
description: A repeated classification fails as ToolFailed and spends no retry, a new classification after the turn changed the strategy is refused, a card answer under the same message is classified once more, and a turn that built stays a building turn, so its check stays reachable.
tags: [lead, intent, control-flow]
status: stable
---

# The choice

`classify_user_intent` (ai/lead/lead_tools.py) refuses a second call that repeats the
held classification, and any new classification once the turn changed the strategy
(`TurnMarkers.changed_strategy`), with `ToolFailed`. The classification that did the work
governs the rest of the turn. A consult card answered under the same message reopens the
classification once: `consult_user` records the card in `TurnMarkers.answered_card`, and
while it differs from `TurnMarkers.classified_card`, the card the last classification read, a
classification that repeats the held one is taken. So the requirements that
answer states reach `deps.intent` and the thread's record, and a second classification of the
same answer is refused as a repeat. `intent_gate.turn_builds` also holds once the turn built, so
`verify_strategy` stays on the list whatever a later call said. The contract's refusal of
a reply that leaves out the change names the steps the turn pushed and the root count
(`contract_messages.unreported_change_message`).

# What was measured

The repeat refusal was a `ModelRetry`. pydantic-ai counts a tool's retries across run
steps and resets the count only when the same tool succeeds, and the Lead's tools carry 3
retries, so the fourth benign refusal ended the turn with "exceeded max retries count of
3" and a resend request (microsporidiadb, round-3 dry UAT). A follow-up classification
after an edit hid `verify_strategy`, and two edited strategies went back unverified. A
second classification after a build dispatched FRAME again, and the reply said nothing
changed on the turn that built both steps.

# What was rejected

**Returning the held classification as a normal result.** It hides that the call did
nothing, and the model reads a success as licence to call again.

**Only a monotone `turn_builds`.** It keeps the check reachable but lets a later
classification dispatch another pass over the work the first one did.
