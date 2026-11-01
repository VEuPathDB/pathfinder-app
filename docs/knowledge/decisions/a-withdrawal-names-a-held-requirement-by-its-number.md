---
type: Decision
title: A withdrawal names a held requirement by its number
description: The classifier withdraws a requirement by the number the Lead reads it under in the numbered list of held requirements, and the thread retires exactly the requirement that number names, in the source it recorded. A withdrawal derived from the words of a classifier value and a held value was measured on 1,018 recorded classifications and kept six requirements the researcher had withdrawn; it is rejected, as are a model-declared key and a judge model per withdrawal.
tags: [agents, lead, requirements, lifecycle]
generated: { by: claude-code/opus-5.5, at: 2026-11-01T00:00:00Z }
status: stable
---

# What was decided

The Lead reads the requirements the thread holds as a numbered list, as FRAME
already does ([a pass names a requirement by its number](a-pass-names-a-requirement-by-its-number.md)).
`UserIntent.withdrawn` is a list of those numbers. The classification gate refuses a
number the list does not hold. The thread maps each number to the id it minted for
that requirement and retires it; the retirement keeps the source the thread
recorded for it. No withdrawal reads a value's words.

This supersedes the withdrawal clause of
[the requirement lifecycle is derived](the-requirement-lifecycle-is-derived.md):
the bullet that retires each held requirement "whose value and the statement's
carry each other's words" (`requirement_lifecycle.withdrawn_by`) and the one that
sources a withdrawal from the first requirement its words name
(`requirement_lifecycle.with_recorded_sources`). The rest of that decision stands.
The code holds the superseded clause until step 5 of
[backlog item 77](../backlog/requirements-are-typed-data.md) lands.

# The measurement

An offline replay ran the current `ThreadRequirements.record` over every saved
debugger and eval run that recorded a completed `classify_user_intent` call: 522
conversations, 1,044 turn runs, 1,018 classifications, no model and no site call.
The withdrawal path compared a held requirement with a withdrawal statement 171
times (140 distinct) and retired 54. It kept six held requirements the message
withdrew, on four messages:

| Message | Withdrawal statement | Held requirement kept live |
|---|---|---|
| "Remove the transmembrane-domain step." (two runs) | `transmembrane-domain exclusion`, `transmembrane-domain step` | `exclude genes with 2 to 99 transmembrane domains` |
| "Drop the oocyst expression requirement entirely: remove the C. hominis expression step ..." | `oocyst expression requirement / C. hominis expression step` | `expressed in oocysts` |
| "Actually, use the 3D7 blood-stage expression instead of sporozoite." (three runs) | `sporozoite expression` | `expressed in sporozoites` |

Five more were doubtful: two runs of "Drop the transmembrane domain requirement"
where the requirement is held only inside a combination, so a statement of
another dimension names nothing; a narrowed ortholog requirement; a phrase the
same message retires in one run and keeps in another; and a stale combination.
In every wrong case the thread held the requirement the researcher meant, and the
statement and the held value named it in different words ("sporozoite" against
"sporozoites", "step" against "exclude"). A kept requirement stays a hard
requirement of the researcher's, so the next verdict checks a strategy against
something the researcher took back, and the same miss leaves its withdrawal
recorded as assumed: the replay found one such source on the sporozoite message.

# What was rejected

**The withdrawal derived from value words** (`withdrawn_by`). It compares two
model-written strings, so a plural, a hyphen or a paraphrase decides whether a
requirement retires. The measurement above is the evidence.

**A model-declared key checked by a gate.** Rejected in
[the requirement lifecycle is derived](the-requirement-lifecycle-is-derived.md):
the key was the canonical value, which an upstream rewrite changed. A number is
the position in the list the Lead read on this turn, which no validator rewrites.

**A judge model per withdrawal.** One more call per withdrawal statement, a
probabilistic answer to a question the list already answers exactly, and a
no-answer branch the thread would still need.

# What would prove this wrong

A replay of the same saved runs under the numbered schema in which a withdrawal
the researcher stated retires a requirement other than the one meant, or a
withdrawal the numbered list cannot name because the thread does not hold the
requirement. The unit tests step 5 adds hold a number the list lacks as refused
and a withdrawn number as retiring exactly its id.
