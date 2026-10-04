---
type: Backlog
title: A card holds one change per stated part
description: A proposal card for a two-part message carries one change and calls the reading it prefers focused, although the comparison's unique genes show it is not.
tags: [lead, cards, proposals]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A card holds one change per stated part

**What I did.** On tritrypdb, answered a text-term question with: use the phrase "GPI anchored", and also include the variant surface glycoprotein products.

**What I got.** `propose_changes` with one change (`text_expression: "GPI anchored"`) and the reply "I recommend the hyphen-free text search ... a focused direct-text result" for the 12-gene word reading, whose `compare_search_variants` `sample_unique_genes` hold TcIL3000_0_29570 (glucose-6-phosphate isomerase) and TcIL3000_10_11240 and _11250 (GPI mannosyltransferases).

**Why that's wrong.** The researcher asked for a union of two arms and was offered a replacement term; accepting builds a strategy they did not ask for, described as focused.

**Why it happens.** The card's changes are the Lead's own, and nothing holds them
to the parts the message states. In that run the researcher's text was a second
`consult_user` answer under the same message: `classify_user_intent` refused the
Lead's classification of it ("already classified as clarification_response",
`ai/lead/lead_tools.py`), so `deps.intent` kept the first answer's parts, and the
only record of the second answer is one `other` requirement holding the whole note
(`ai/lead/lead_consult.py::_answer_requirement`). A `ProposedChange` carries a search
name and wire values, and nothing links it to a stated part, so matching words
against wire values would refuse good cards.

**Fix.** A design decision, not yet taken:
- A card answer under the same message reopens classification, so its stated
  parts reach `deps.intent`.
- Each `ProposedChange` names the `Constraint.key` values it answers, and the card
  names the keys it leaves to a question; an unknown key is refused.
- `propose_changes` is registered with an `args_validator` (the pattern
  `consult_user` uses) that refuses a card when a stated part is in neither list,
  naming the part by its label. A part the spec already binds needs no change, and
  a combination is covered when each of its terms is.

The comparison half is done: each sampled unique gene carries its product.

**What you'd get.** A card with two changes (the phrase arm and the VSG arm under
UNION) for that message, or a refusal naming the uncovered part.
