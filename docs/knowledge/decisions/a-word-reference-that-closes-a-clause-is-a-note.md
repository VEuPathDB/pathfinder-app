---
type: Decision
title: A word reference that closes a clause is a note
description: Every value a statistic fact holds has a display form read from its type, and a `stat` reference to a word or a sentence renders the word inside its clause and a numbered note below the reply where it closes the clause; a number or a one-word identifier always renders in place. Rendering every reference in place, rendering every word reference as a note, and comparing the reply's words with the value were rejected.
tags: [agents, lead, reply, facts, references, audit]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

An audit read is a statistic fact whose rows are the values of its typed answer
(`domain/statistic_rows.py::model_rows`). The answer's serialization schema
(`fact_schema`) gives each leaf a display kind, and a leaf with none (an untyped
value, an object or an array with no item schema) is refused with
`NoDisplayFormError` when the schema is first read:

| leaf | row value | `StatisticRowFact.form` |
|---|---|---|
| a number | the number as the answer writes it | `value` |
| a string of one word that no enum names (an id, a transcript, a site) | the string | `value` |
| an enum or a constant | its plain words (`plain_words`: underscores to spaces, an all-capital code in lower case) | `word` |
| a boolean | "yes" or "no" | `word` |
| a string of more than one word (a name, a reviewer's sentence) | the string | `word` |

`render_reply` reads the form where the reference stands (`domain/reply_notes.py`).
A `value` row renders in place wherever it stands. A `word` row renders its value in
place when a word follows the reference in its clause ("a [stat:...certainty]
certainty error" reads "a high certainty error"), and a numbered note when the reference
closes its clause: the next character after it and the references beside it is a
punctuation mark, a line end or the end of the reply. The note marker takes the place of
the reference, a reference cited twice shares one note, and the notes follow the reply as
GitHub footnote definitions, each the field's words and the value (`[^1]: frame kept:
yes`, `[^2]: cause: <the stored sentence>`). A token the reply writes as an enum code
names the reference whose value is that code's plain words
(`statistic_word_references`).

The Lead's instruction (`AUDIT_RULES`) and the shared placement rule
(`card_reply.PLACEMENT_RULES`) state it: a number or an identifier is the reference
alone; a word or a sentence is said once, by the reference in place of the word or in
the reply's words with the reference closing the clause; a stored sentence is never
copied.

# Why

A reply writes a word value two ways: as the word's own place in the clause, and as a
citation after the clause that already says it. A reference that always renders its
value in place doubles the word in the second shape ("high high", "retained as an error
error") and pastes a stored sentence into the middle of the reply; a value with no
display form renders as its wire spelling ("true", "UNSUPPORTED_SHIFTED",
"not_searched"). Where the reference stands is a fact of the reply's shape, so the
renderer reads it without reading the words around it.

# What was rejected

- **Every reference in place.** It doubles each word the reply also writes, and the
  reply writes the word because the tool answer shows it.
- **Every word reference as a note.** A reference in place of its word ("with
  [stat:...certainty] certainty") would lose the word from the sentence.
- **Removing the reply's word that equals the value.** It reads the model's free text
  for facts, the guess
  [the product renders the facts](the-product-renders-the-facts-the-reply-narrates.md)
  retired.
- **A display form declared for each field.** The answers hold about two hundred string
  fields, many in the tool server's distribution; the schema type and the word count
  decide the form for every one, and the schema check refuses a leaf neither decides.

# What would prove this wrong

`tests/unit/ai/audit/test_the_audit_replies_read_as_prose.py` renders four recorded
audit replies as single prose. `tests/unit/ai/audit/test_every_fact_field_has_a_display_form.py`
reads every answer an audit tool returns and every statistic kind.
`tests/unit/domain/test_a_stored_value_has_a_display_form.py` holds each form and the
refusal, and `tests/unit/domain/test_a_word_reference_that_closes_a_clause_is_a_note.py`
the placement. A reply that writes "Confidence is [stat:...certainty]." ends on a note
where it meant the word; a reply that does this often proves the placement rule is not
followed.
