---
type: Decision
title: A card option is a binding, and a requirement has a lifecycle
description: A question card asks the questions FRAME recorded with the options it typed; a picked value is bound into the spec as the card's with no model in between, a withdrawal retires its requirement, and a message that removes or swaps a requirement retires it with its lifecycle, so no check reports it as a gap. A card that offers no choice, or asks what the researcher answered, is never offered, and an option label is never a requirement. Rewriting the card's arguments, free-text options and filing an answered question as a requirement were rejected.
tags: [agents, lead, frame, parameters, verification]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: stable
---

# What was decided

A question FRAME asks about one parameter (`SlotQuestion` with `criterionId` and
`paramName`) becomes an `OpenQuestion` whose options are `TypedOption`s:
`SetValues` binds wire values on one criterion, `Withdraw` retires one requirement
by its `Constraint.key`, and `Keep` keeps it. No option binds its own label: a
question that binds no slot (the Lead's reply, a FRAME question that names no slot)
is typed with no option and answered in the researcher's words. A slot question on
an open parameter the site offers a vocabulary for offers the vocabulary's values,
whole while they fit a card.
A `SetValues` option's label states what it binds: the parameter's display name,
the value, and the count the site returned at that value when one was measured.
For each requirement the researcher stated that the ledger lists as ungroundable,
the FRAME dispatch adds a `Withdraw` option: on the question of the requirement's
dimension, beside the values the nearest search offers, or on a question of its own,
which also offers a `Keep` option, so a question never offers only to drop what the
researcher asked for. A fold change or a p value an exported analysis cuts at is
grounded, so no such question claims that nothing states it.

A card offers a choice or it is not asked, and the rule is held by the question
types, so no path can build a card that breaks it: FRAME's first pass or its
second, an edit's pass, the Lead's own card and the questions a reply records. An
`OpenQuestion`, an `AskedQuestion` (and so FRAME's `SlotQuestion`) and the Lead's
`CardQuestion` that offer options offer two at least, and two options that bind the
same values are refused as one; a question with no option is answered in the
researcher's words. An option spelled as the site's label of a vocabulary term binds
that term, so a slot question whose offered values bind one term offers no choice
and the pass records no question for it. A positive number offered for a parameter
whose display name names the log2 scale is offered in both readings, the fold and
the log2 value, each labelled with the fold it stands for ("0.585 (1.5-fold)" and
"1.5 (2.83-fold)"), so a card over a fold threshold never offers a bare log2
number. The FRAME dispatch asks no question the researcher answered. A requirement
the pass names in `unstated` gets the same drop-or-keep question as one the ledger
lists as ungroundable, so a card of the Lead's own about it is refused as a card
that leaves a recorded binding question out. A FRAME question with no option that
carries the words of such a requirement is that drop-or-keep question, and
`questions_that_bind_to_nothing` (`ai/lead/frame_questions.py`) counts it as bound.
A refusal of what a pass asks keeps each criterion the pass bound
(`refuse_and_keep_what_it_bound`); a refusal of undeclared changes puts back the
spec the dispatch found, and runs first.
The FRAME result hands the Lead `cardQuestions`, the card those questions become,
each a `CardQuestion` that carries the dimension its answer states. The
`consult_user` tool's arguments validator refuses a card that does not ask each
recorded binding question with its recorded labels, that offers one of those labels
on a question of the Lead's own, whose own question offers labels that bind
nothing, that asks again a question the researcher answered, or whose own question
with no option asks a dimension a parameter of the spec holds: one a recorded
question states, the organism while a criterion names its organism parameter, and
the dimension of each parameter a criterion holds (`dimension_of_parameter`). A
question of the Lead's own offers no option, or 'Drop <requirement>' and 'Keep
<requirement>' of a requirement the thread holds, which bind as `Withdraw` and
`Keep`; a value a parameter sets is asked by the pass that binds it. An answer applies its option before the
Lead reads it: the value is written into the spec as a `card` value whose basis is
the option id, in the kind of the value it replaces or of the open slot it fills
(an `OpenSlot` carries the parameter kind its sheet gives), and the FRAME re-bind
that follows sources it `card` again.
FRAME's `questions_that_bind_to_nothing` refuses a question that names a slot no
criterion of its draft holds, open or bound.

A requirement the researcher takes back leaves `requirements` for
`retiredRequirements` with a `withdrawn(turn)` lifecycle; one swapped for another
the same message states is `replaced(by)`. `classify_user_intent` records both from
`withdrawnRequirements` and refuses a key the conversation does not hold and a
successor the conversation already holds; an empty `replacedBy` is a plain removal.
A new combination over the terms of a held one displaces it: `with_requirements`
returns the displaced one as `replaced(by)`, so no path removes a requirement
without a retired record. A review row that names no held requirement, such as an
edit instruction the turn carried out, is no gap. An answer in the researcher's
words states a requirement on its question's dimension, which replaces the
requirement the thread held on that dimension (`replaced(by)`, shown in the words of
both). A question an answer settled, on a card or typed, is a question and never a
requirement: the thread keeps it in `answeredQuestions`, no retired row names it, and
`check_gaps` reports no gap for a row that carries every word of it. A question
carries the words of the requirements it asks about, so a row a question's words
carry is still a gap while nothing answers it; a `Keep` answer binds nothing and
leaves its requirement open. VERIFY passes the retired
requirements to `check_gaps`, which reports no gap a retired one names, and the ledger derivation drops every row whose key a retired requirement
holds, so a drop that still names it is no ungroundable row. A no on the removal
card that followed takes the message's withdrawals back.

A proposal card's changes are typed the same way: values set on a criterion, or a
criterion added with the search it runs, each with the sentence the card shows. A
change that names no search and no value is refused. A removal is not a proposal
change: the apply path refuses an edit that only removes built steps, so a removal is
the delete card, which lists its cascade, and one approval runs it. The card's
sentences are the Lead's words and are never recorded as the researcher's; the note
the researcher sends with the yes is. A requirement only a card sentence states is
therefore assumed, not stated. Rejected: recording the accepted sentences as the
researcher's message, which put a card sentence into VERIFY's request as a message the
researcher never wrote and filed it as a requirement row.

A removal card lists what the removal takes. The delete card's question names
the step; every other step the delete removes rides its own `data-delete-cascade`
part and is listed in full under the question (`approval-card-cascade`), because
a question is one summary line with a length limit. The steps are computed on a
copy of the graph before the card is shown (`_delete_rules.delete_cascade`),
never read from the reply. The approved delete computes them again and fails, removing nothing, when
the strategy changed while the card waited and the steps differ from the ones the
card listed (`_delete_rules.refuse_a_delete_the_card_did_not_list`).

# What was rejected

**One refusal function that every card path calls.** The one-option card came back
on paths that did not call it: the Lead's card, and a card a second pass built. A
check a caller must remember is a check a new caller forgets; a validator on the
question types runs wherever a card is built.

**Rewriting the card's arguments to the recorded options.** The card is drawn from
the tool call's input, which the model wrote, so a rewrite on validation would draw
one card and read another. The validator makes the model's card the recorded one.

**Free-text options.** A label is text the answer carried back as a requirement,
so a picked cutoff reached FRAME as words and the build ran the site default, and a
label such as "Specify an alternative evidence type" became a requirement and a
gap. A typed option carries the value itself, and a question that binds no slot
is answered in the researcher's words.

**Filing an answered question as a retired requirement.** It kept the question off
the gaps, but the facts then showed the card prompt as a requirement replaced by the
card's own option, with a parameter name in it. The question is kept as a question.

**Re-deriving the lifecycle each turn.** Grounded requirements are rebuilt every
turn, so a lifecycle set on them is lost. The retired record is stored on the
checkpointed domain state instead.
