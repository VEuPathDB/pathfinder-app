---
type: Decision
title: The requirement lifecycle is derived
description: The classifier states requirements by dimension and value, and the ones a message takes back; the thread derives every replacement, withdrawal and successor from those statements and from what it holds. FRAME's disposition of a criterion is read from its wire values, and a review row's status agrees with its answer by construction. Model-declared replacement keys checked by a gate were rejected.
tags: [agents, lead, frame, verification, requirements]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: stable
---

# What was decided

`UserIntent` states requirements and nothing about their identity:
`explicitConstraints` (dimension, value, label, quote, hard) and `withdrawnIds`,
the held requirements the message takes back. It names no key and no
successor. `ThreadRequirements.record(intent, messages)`
(`ai/graph/thread_requirements.py`) derives the lifecycle:

- A stated value of a dimension that holds one value (organism, record type,
  threshold, fold change, percentile, data type, comparator) replaces the value
  the thread held for it, which retires as `replaced(by=<new id>)`
  (`stated_requirements.with_requirements`). Two values stated in one message
  both stand, and a value the reading states `beside` a held requirement's number
  adds beside that one. `other` and `combination` hold many values; no reading or
  card writes a new combination, and a message that swaps an `other` value names
  the old one's number among its withdrawals.
- A value whose quote no researcher message holds (`assumed`, see
  [a requirement is the researcher's when it quotes their words](a-requirement-is-the-researchers-when-it-quotes-their-words.md))
  never displaces a value the researcher stated of a single-valued dimension: it is dropped, neither recorded
  nor retired (`stated_requirements._outranked`). A stated value displaces an
  assumed one.
- `count`, `ortholog`, `text`, `property`, `untyped` and `combination` hold many
  values everywhere, the ledger's merge included: two of them collapse only when
  their typed values are equal, or when they are one requirement by id
  (`constraints.MANY_VALUED_KINDS`, `constraints.merge_constraints`), the stated
  one winning.
- A withdrawn requirement retires as `replaced` by a value of the same dimension
  the message states, else as `withdrawn` on this message. Which held
  requirement a message withdraws is decided by
  [a withdrawal names a held requirement by its number](a-withdrawal-names-a-held-requirement-by-its-number.md),
  which superseded the clause that compared the words of a withdrawal statement
  and a held value.
- Which values a message states is the message reader's: each requirement the
  reading writes is recorded, and no test of its words against the message's
  asks (`StatedRequest.asks`), its compared sides
  (`StatedRequest.differential_sides`) or a picked card label drops it. A card
  pick binds its option by id and states no requirement, a card answer in the
  researcher's words is recorded as theirs by the card, and a card sentence is
  never recorded as the researcher's words.
- An approved `delete_step` retires each live requirement that a deleted
  criterion links and no remaining criterion links
  (`retire_what_a_delete_leaves_unanswered`, see
  [a criterion links the requirement it answers](a-criterion-links-the-requirement-it-answers.md)),
  a held combination among them. A withdrawn combination shows no row: each
  requirement its criteria linked has a row of its own
  (`RetiredRequirement.shown_requirements`).

FRAME's disposition of each criterion the dispatch found is the computed diff of
the two specs (`frame_dispatch.derived_changes`): `kept` only when no wire value
moved. `FrameResult.changes` is omitted from FRAME's schema, so the pass writes no
account.

A check writes no requirement row: each requirement is a check on the site
([a verification verdict is computed from the site](a-verification-verdict-is-computed-from-the-site.md)),
and a retired requirement is no check.

# What was rejected

**Model-declared replacement keys with a gate that checks them.** The classifier
wrote `withdrawnRequirements` as `<dimension>:<value>` keys with a `replacedBy`
successor, and the classification gate refused a key the thread did not hold and
a successor it already held. The key is the canonical value the thread recorded,
so the gate refused the correct withdrawal whenever an upstream validator had
dropped or rewritten the constraint the key named, and the successor duplicated
what the message's own constraint already stated.

**A disposition the pass declares, refused when it disagrees with the values.**
The refusal read the pass's label, so a pass that moved exactly what the request
asked was refused for a wrong word. The values are the account.

**An `unmet` row that names the step answering it.** A combine joined another
way and a text row a record shows missing were both filed as `unmet` with steps
named, so a reader could not tell a requirement nothing answers from one the
records leave short. The note names the combine, and the records' verdict is a
status of its own.

**A withdrawn combination's row read from the live criteria's text.** The row
named each side whose words no live criterion's text carries. A criterion text
paraphrases its side ("without" for "no", a Pfam name for a domain), so a side
a live step answers read as withdrawn. The terms are matched to criteria once,
when the delete knows which criterion left.
