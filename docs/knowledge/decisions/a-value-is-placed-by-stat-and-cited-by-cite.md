---
type: Decision
title: A value is placed by stat and cited by cite
description: Every value a statistic fact holds has a display form read from its type; `[stat:]` always renders the value in place and `[cite:]` always renders a numbered note after words that already state it, a sentence is refused under `stat` and a number under `cite`. Inferring the kind from where a reference stands, rendering every reference in place, and comparing the reply's words with the value were rejected.
tags: [agents, lead, reply, facts, references, audit]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

An audit read is a statistic fact whose rows are the values of its typed answer
(`domain/statistic_rows.py::model_rows`). The answer's serialization schema
(`fact_schema`) gives each leaf a display kind. Every answer an audit fact is read
from is registered once (`ai/audit/fact_sources.py::FACT_SOURCES`), and each audit
toolset reads every registered schema when it is built (`warm_fact_schemas`), so a leaf
with no display form (an untyped value, an object or an array with no item schema)
fails with `NoDisplayFormError` at startup, never in a turn. A value the schema does not
hold still renders, by its JSON type.

| leaf | row value | `StatisticRowFact.form` |
|---|---|---|
| a number | the number as the answer writes it; a `Share` as a percentage (`88.9%`) | `number` |
| an enum or a constant | its words: a code table where `domain/audit/facts.py::CODE_WORDS` holds one, else underscores as spaces and, for an enum whose members are underscored capitals, lower case; `code` keeps the wire value | `word` |
| a boolean | `YES_NO` (`Yes`, `No`) | `word` |
| a string of one word | the string | `word` |
| a string of two or more words | the string | `sentence` |

Two reference kinds name a row (`domain/reference_grammar.py`):

- `[stat:<id>.<row>]` renders the value in place, wherever it stands.
- `[cite:<id>.<row>]` renders a footnote marker joined to the word before it, and the
  notes follow the reply as GitHub footnote definitions, each the field and the field
  that holds it, then the value (`[^n1a2b3c4d-1]: review verdict: error`). A row cited
  twice shares one note. Each emitted reply takes labels of its own (`note_label`), so
  two replies of a thread or of an export never share a footnote id.

`prose_faults` refuses a `stat` on a `sentence` row with the `cite` that names it, and
a `cite` on a `number` row with its `stat`; neither reads a word of the reply. The
contract's rules read `render_reply`, the reply with its markers and no notes; the
notes are joined only where the reply is emitted (`shown_reply`, in `_lead_capture`,
`_lead_card_hold`, `_lead_exchange` and the audit assistant's `reply_text`). A
synthesis summary is stored as the synthesis wrote it, with its references.

The placement rule (`card_reply.PLACEMENT_RULES`, in the Lead's instructions and every
schema that lists the references) is one sentence: `[stat:]` is the value written in
place, and `[cite:]` follows your own words for it.

# Why

A reply writes a stored value two ways: in its place in the clause, and as a citation
after a clause that already says it. One renderer for both doubles the word in the
second shape ("high high", "retained as an error error") and pastes a stored sentence
into the middle of the reply; a value with no display form renders as its wire spelling
("true", "UNSUPPORTED_SHIFTED", "not_searched"). Two kinds let the reply say which shape
it means, and the type of the row decides which kind may name it.

# What was rejected

- **Inferring the kind from where the reference stands** (a word reference closing its
  clause became a note). Over the six recorded audit replies the replay test holds, 12
  word and sentence references follow a clause that states them, 4 stand in place inside
  a clause, and 4 sit in a list of values; the inference rendered the list as markers
  ("replacement:[^1], 0, 1226,[^2]"). A reference at the end of a predicate ("Audit run
  [stat:...runId] is [stat:...status].") became a note and lost its word, which forced
  four mock replies into unnatural shapes. Notes appended to the text the contract reads
  hid a final question mark from `ends_with_a_question`, so an offer escaped
  `unrecorded_question` and a question over a failed check fell to `failed_check`.
- **Every reference in place.** It doubles each word the reply also writes.
- **Removing the reply's word that equals the value.** It reads the model's free text for
  facts, the guess [the product renders the facts](the-product-renders-the-facts-the-reply-narrates.md)
  retired.
- **A display form declared for each field.** The 16 registered answers hold 193 string
  leaves, many in the tool server's distribution; the schema type and the word count
  decide the form for every one, and the startup check refuses a leaf neither decides.

# What would prove this wrong

`tests/unit/ai/audit/test_the_audit_replies_read_as_prose.py` renders the six recorded
replies. `tests/unit/ai/audit/test_every_fact_field_has_a_display_form.py` holds the
registry against every answer an audit tool returns.
`tests/unit/domain/test_a_stored_value_has_a_display_form.py` holds each form, the
two-word threshold, an unknown key and the startup refusal;
`tests/unit/domain/test_a_cite_reference_is_a_note.py` the two kinds, their refusals and
the labels; `tests/unit/ai/lead/test_a_cited_question_still_ends_the_reply.py` the
contract over a cited question; and `apps/web/src/features/conversation/content/replyNotes.test.tsx`
the notes of two replies in the thread and in the export. A genome name of two words is a
`sentence` and so only cited; replies that need a name in place prove the threshold
wrong.
