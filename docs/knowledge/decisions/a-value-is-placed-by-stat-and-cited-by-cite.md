---
type: Decision
title: A value is placed by stat and cited by cite
description: Every value a statistic fact holds has a display form read from its type; `[stat:]` always renders the value in place and `[cite:]` always renders a numbered note after words that already state it, a field typed `Sentence` is refused under `stat` and a number under `cite`. Inferring the kind from where a reference stands, rendering every reference in place, and comparing the reply's words with the value were rejected.
tags: [agents, lead, reply, facts, references, audit]
generated: { by: claude-code/opus-5.5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

An audit read is a statistic fact whose rows are the values of its typed answer
(`domain/statistic_rows.py::model_rows`). The answer's serialization schema
(`fact_schema`) gives each leaf a display kind. Every answer a statistic fact is read
from is registered once (`ai/fact_sources.py::FACT_SOURCES`), and each audit
toolset and the FRAME toolset read every registered schema when it is built (`warm_fact_schemas`), so a leaf
with no display form (an untyped value, an object or an array with no item schema)
fails with `NoDisplayFormError` at startup, never in a turn. A value the schema does not
hold still renders, by its JSON type.

| leaf | row value | `StatisticRowFact.form` |
|---|---|---|
| a number | the number as the answer writes it, a number of 1,000 or more with thousands separators (`7,364`, `1,234.5`), so a reply that lists placed values separates them with `; `; a `Share` as a percentage (`88.9%`); an `Identifier` (a finding id) as written, with no separator | `number` |
| an enum or a constant | its words: a code table where `domain/audit/facts.py::CODE_WORDS` holds one, else underscores as spaces and, for an enum whose members are underscored capitals, lower case; `code` keeps the wire value | `word` |
| a boolean | `yes` or `no`, lower case since a row stands inside a sentence | `word` |
| a field typed `Sentence` (free text: a cause, a description, a card or review text, a message) | the string | `sentence` |
| any other string (a name, a genome, a product, an id) | the string | `word` |

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
synthesis summary is stored as the synthesis wrote it, with its references, beside the
rows they name (`StoredSynthesis.facts`, from `reply_notes.referenced_facts`); every read
renders it (`services/audit/views.py::_shown` through `reply_references.nested_text`), so
`GET /api/v1/audits/{id}` and the Lead's `read_audit_run` fact both hold text: a `stat`
renders in place and a `cite` as its value in parentheses, since nested text carries no
notes. The view types the rendered summary without a length cap (`SynthesisView`), so a
stored summary always reads; the synthesis refuses a draft whose rendered summary,
`nested_text` over the facts it cites, runs past `MAX_CARD` (1200 characters), since each
`cite` grows by its value.

`Sentence` and `Share` are `Annotated` markers (`statistic_facts.SchemaFormat`) that add
a `format` to the field's schema, which `fact_schema` reads. A name the gate refuses as a
token when written out ("17X" in a genome name, refused by `_token_faults` as a number with
a glued unit) is never refused when a `stat` places it, since the gate reads the prose
outside references, and the refusal of the written name names that `stat`.

The tool server's answer types are not marked here. Of their string fields,
`IntronAudit.correction_reason`, `IntronJudgement.reason` and `OrthologSupport.reason` are
free text and take `format: "sentence"` in the tool server's own schema, which
`fact_schema` reads the same way it reads `Sentence`; every other one (genes, transcripts,
organisms, products, titles, tracks, versions, ids, sequences) is a word.

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
- **A sentence decided by its word count.** It made every name of two words (a genome, a
  product) impossible to place, the most common placement.
- **A display form declared for each field.** The 16 registered answers hold 186 string
  fields, 88 of them in the tool server's distribution; the schema type decides the form,
  one marker names the free text, and the startup check refuses a leaf no type decides.

# What would prove this wrong

`tests/unit/ai/audit/test_the_audit_replies_read_as_prose.py` renders the six recorded
replies. `tests/unit/ai/audit/test_every_fact_field_has_a_display_form.py` holds the
registry against every answer an audit tool returns.
`tests/unit/domain/test_a_stored_value_has_a_display_form.py` holds each form, the
`Sentence` marker, an unknown key and the startup refusal;
`tests/unit/domain/test_a_cite_reference_is_a_note.py` the two kinds, their refusals and
the labels; `tests/unit/ai/lead/test_a_cited_question_still_ends_the_reply.py` the
contract over a cited question; and `apps/web/src/features/conversation/content/replyNotes.test.tsx`
the notes of two replies in the thread and in the export;
`tests/integration/jobs/test_audit_synthesis_job.py` the stored summary and its two
rendered reads.
