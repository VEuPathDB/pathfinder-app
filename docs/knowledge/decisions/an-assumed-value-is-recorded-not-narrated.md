---
type: Decision
title: An assumed value is recorded, not narrated
description: Every bound value records who set it (stated, chosen, default, card or held), decided by the tool from the messages, the sheet and the card; a chosen value is rendered as a non-blocking constraint instead of appearing once in the reply's prose.
tags: [agents, frame, parameters, ledger]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-09-30T00:00:00Z }
status: stable
---

# What was decided

Every value a criterion binds is a `BoundValue` that carries who set it:
`stated` when one of the researcher's messages holds every word of the whole
value as one run (a number word up to twenty and an ordinal read as their
digits, and every
pick of a multi-pick and both bounds of a range must occur in the same
message; a filter, a dataset or a step is never stated), or names every label
the site gives the value (a vocabulary display, the organism a phyletic code
names), whole or with one word after its first left out when no other entry of
the vocabulary is named by the same words ("Homo sapiens" names "Homo sapiens
REF"), a run matching with its punctuation left out ("C57BL/6J" names
"C57BL6J"), `card` when an answered card set it, `default` when it is unset and
no message states it, and `chosen` otherwise. A value is unset when it is a
site placeholder (the radio-off value `N/A`, an example text such as
"(Example: chr22)") or equals the parameter's `initialDisplayValue` (or WDK
supplied it). A placeholder is never stated.

A `BoundValue` is built once, by `operational_spec.bind_values(values, source,
sheet, basis)`, from the parameter sheet the site publishes: `display_name`
from the sheet, `label` from the vocabulary (a pick's displays, a filter
clause's field, the organism a species code names), `placeholder` from
`ParameterInfo.is_placeholder`, and `at_default` when the value, read in its
own kind, is the published initial value. The bind, the hydration and replay
of a strategy that already exists, the fold (`BoundValue.carried`) and the
separation card all build through it; `read_again` reads held values on a
sheet through it and keeps who set each. No consumer holds a rule of its own:
`text_query` is a free-text class with neither `placeholder` nor `at_default`,
`measure_binding` gives a placeholder and an unset text no other reading, the
organism check of a search choice reads `unset`, and the facts row reads the
label and the placeholder from the value. A sheet read under the bound values
is never the sheet a value is judged against: WDK answers every sent value as
its `initialDisplayValue`, so plasmodb GenesByText read under
`text_expression = "cysteine-rich protein"` answers that text as the initial
value, where the published sheet holds `*reductase`.
`_frame_measure.vocabularies_under` takes only the dependent vocabularies from
such a read into the published sheet, and `get_parameter_options` sends no
value of the parameter it reads, so the initial value it answers is the site's. A pick at its initial value shown as one word ("any", "yes") is
stated only when a message writes it beside a word of the parameter's display
name ("in any selected sample"); otherwise the site set it. A parameter the
parameter rules class as `site_fixed` (read-only, or hidden with no vocabulary)
has the source rule `site`: its value is `default` whatever a message holds. `set_criterion` decides the source from that data;
the model never declares it. A value read from a strategy that already exists
(a hydrated spec, an outside change replayed) is `held`: the strategy holds it
and nothing records who set it, so it is neither called stated nor a caveat. `basis` holds the matched words for a stated
value, the reason FRAME gave in `why` for a chosen one, and the option id for a
card value. `Criterion.defaulted()` is derived from the sources, so no list of
defaulted names is stored beside the values.

The ledger's constraint section renders each chosen value as a `Constraint`
with `source = assumed`, `hard = False` and status `grounded`, its basis as the
note, so the Lead names them from the ledger and the user can override any of
them by stating the value. A default or chosen value whose measurement shows
another reading counts more genes is an `AssumedValueCaveat` of the check,
and one whose other reading did not arrive is an `UnmeasuredValueCaveat`, which
says the value's effect was not measured, so a default is never silent. That
holds for a number, a phrase and a species reading; another option of a pick or
a filter whose count the site refuses is no reading and makes no caveat, since
a choice caveat needs a differing count and a missing count is silence. A
binding whose own count did not arrive records each default or chosen value
that way too. A binding's own count that did not arrive in time stays bound
with no count. A count the site refuses with an error status (a 5xx on the
search's own report at the bound values) refuses the binding with that
status, as a 422 on its values does: the criterion is counted before it is
recorded, so a refused count records nothing and a re-bind leaves the held
binding in place. A default or chosen pick names the options of its vocabulary it
did not take, as a `ChoiceCaveat`, only when the choice changes the count: a
single pick is counted at up to `COUNTED_OPTIONS` other options, the site
default first, and a multi-pick at its site default or, when it holds that
default, at every option, its loosest bound. An option the site does not
count records nothing; a pick with one option names nothing. A
tree pick records that options not taken do not apply, since a parent term
takes the options under it.

Once a binding counts, `set_criterion` measures each default or chosen value
against another reading, each read once per turn and site: a number at its
published bounds (zero where the site publishes none), keeping the reading that
counts more genes; a quoted word in its wildcard form, and a quoted or
multi-word phrase in the site search, for the search the site search hands its
record type to; a species group required in every member against at least one;
an excluded species list against no species excluded; a pick or a filter
against the site's default, when it differs. Each parameter class names its
rule in `PARAMETER_RULES`, which is total over the kinds WDK publishes: a date,
a dataset, a step input and the derived profile pattern record why they have
no reading, an unquoted single word and a search the site search does not
read record the same, and a read-only parameter or a hidden parameter with no
vocabulary is the site's to set, so nothing is measured. A hidden parameter
that is not read-only and has a vocabulary is a choice the bind takes, since
WDK accepts any of its entries, and the sheet lists it marked hidden. A count
the service fails to answer (a 5xx) is recorded with no count.
An unquoted text is also counted with each operand of several words quoted
(`TextExpression`), recorded as a `phrase_reading`; the operator words `AND`,
`OR` and `NOT` and a wildcard word stay outside the quotes, and a text its
writer grouped has no such reading. The site matches any word of an unquoted
text, so the clause and the `PhraseCaveat` show the bind's count as the words
reading beside the phrase reading ("as any of its words: 4,497 genes; as the
phrase: 0").
When a request message asks for the phrase ("exact phrase", "the phrase", "as a
phrase", "in quotes", read by `text_expression.asks_for_the_phrase`), the word
reading is not a choice: `set_criterion` refuses a free-text term of several
words sent unquoted and names the quoted term (`_frame_stated.py`).
The reads of one bind run beside each other under one budget of their own
(`MEASUREMENT_BUDGET_SECONDS`), apart from the bind's count; a reading that has
not arrived by then is recorded with no count, and no missing count is held in
the turn's cache. A number with no published bound is read at zero whichever
way it bounds: for a parameter that bounds from above that read counts fewer
genes and records nothing, one extra read accepted in place of guessing the
direction from the parameter's name.
Every vocabulary pick records the label its vocabulary gives it, and a pick the
call proposed that has no label is refused with the labels nearest to it. The
per-term `vocabulary_label` measurements and `BoundValue.label` read the same
`value_label.term_labels`, so the row's label is the terms' labels joined. A
filter clause is labelled by the `display` of the `filter_fields` entry whose
`term` its field names, and each member value is its own label, since WDK
stores none (WDK-PARAM-014). A phyletic code, in a species list or the
derived pattern, is labelled by the organism the clade tree names it. The criterion records each parameter's display
name, which the caveat, the ledger and the tool's `measurements` clauses name
it by. An exported analysis names its effect-size cut by the label the
compute gave its effect size: the compute stores `effectSizeLabel` in the
volcano configuration of the analysis document, the step carries that document,
and `AnalysisBinding.effect_size_label` is read back from it, so a log2 cut
shows its fold on every turn after the one that computed it. The compute's
direction is labelled by the genes it keeps, named by its groups ("upOnly",
"Genes higher in 24h than in 18h").

A value binds on the scale its parameter names. A display name that names
log2 holds a log2 value, one that names a fold and no log2 holds a fold. A
number a researcher message writes on the other scale ("1.5-fold" for a log2
parameter, "log2 fold change of 1" for a fold one) binds converted to the
parameter's scale: `set_criterion` converts the proposal and says so in
`corrections`, and `create_eda_step` converts the cut when the compute's
`effectSizeLabel` names log2 and says so in `guidance`. A log2 value is
written at three decimals, which gives back a fold written with three
significant digits, so 1.5-fold binds at 0.585. That value is stated, its
basis the researcher's words, and a fold's number never states the same
number on the log2 scale. A log2 value shows the fold it stands for as its
label: "log2(Fold Change): 0.585 (1.5-fold)". A bind whose own count did not
arrive takes the count the live strategy holds for its step, so its values
read at that count ("12,318 genes; its other readings: not measured") and not
as unmeasured.

# What was rejected

**A shared unset test each consumer calls.** `value_source.is_unset` existed
and the text query, the measurements, the organism check and the hydration each
called it with the sheet they held; a measurement given the sheet read under
the bound values judged the bound text unset, and a hydrated placeholder was
patched after the value was built. A rule on each caller is skipped by the next
caller, so the sheet facts are fields of the value, set where it is built.

**Passing the published sheet beside the context sheet to each consumer.**
Every consumer of a context read then owns the choice of sheet again. The
context read gives vocabularies only, and the value is judged when it binds.

**Keeping a binding the site refused to count.** The criterion was once
recorded before its count, so a 500 on the count reported the call as failed
while the draft kept a binding the site cannot run, and the build pushed a
step with no count under a root with no count. An expiry says nothing about
the values; an error status says the site cannot run them.

**Trusting the model to convert.** The export tool and the bind once took the
model's number on the parameter's scale. The model passed the researcher's
1.5 for "1.5-fold" on a log2 compute, a 2.83-fold cut, and a loosen fell from
314 genes to 289. The scale is data the site publishes and the unit is in the
researcher's words, so the tool converts; the model's number is only the
number it read.

**The model declares its assumptions.** `set_criterion` used to take an
`assumed` list, one entry per value the model chose. A value the model did not
declare was silent, so the record held only what the model remembered to say.
The source is now read from the messages, the sheet and the card.

**A defaults-authorisation flag.** The item this closes was filed as "the user
said pick something sensible and nothing hears it". Diagnosis found most of it
was a defect in numeric defaults
([a number's initial value is a default](numeric-default-is-not-an-example.md)),
and the remaining slots now fill from the sheet in the `set_criterion` call
itself. A flag would have gated a mechanism that already runs.

**Filling the slot from a ranked candidate.** The design this was first drafted
against had a resolver that proposed a top candidate per parameter. That
resolver is gone ([one proposer, one validator](one-proposer-one-validator.md)),
so the filling half needs nothing; only the recording half was missing.

**Recording a held value as stated.** A spec rebuilt from the strategy once
bound every value `stated`. A value FRAME chose or the site defaulted then read
as the researcher's after a flushed checkpoint, which hides its caveat.

**Counting "at least one member" as a union of steps.** WDK's profile pattern
is a `LIKE` over leaf codes and states no disjunction, so a union needs a
temporary strategy of one step per member. The census holds every species
present or absent, so the genes with at least one member present are the genes
with no constraint on the group less the genes with every member absent: two
anonymous reports of the same search.

**A wildcard form of a phrase.** The text search reads no wildcard inside
quotes (on giardiadb `"surface* protein*"` and `"surface protein"` both count
21), and an unquoted phrase is already an OR of its words, so only a single
word has a wildcard form; a phrase is compared with the site search instead.

**Stating a value from three of its words.** A run of three words of a
longer value once made the whole value stated, so a Boolean the model composed
around a phrase of the request read as the researcher's, and skipped its
measurement. The whole value is now required.

**Holding every hidden parameter to its default.** A hidden parameter with a
vocabulary can decide a dependent vocabulary; holding it hid the comparison the
request named and refused a value WDK accepts.

**The message states a value before the site does.** A read-only
`document_type` "gene" and a site default "any" read as stated because a word
of the message matched them, which hid the "all" reading (1,366 against 560
genes). Who can set a value, and whether it is unset, are decided first.

**Refusing a chosen contrast half.** The declared-assumption refusal on a half
of a reference and comparison pair fired only when the model declared one. A
refusal on every chosen half would refuse a group the request names in other
words than the vocabulary's, so a chosen half is shown with its source instead.

# Anchor

`BoundValue`, `ValueSource` and `Criterion.defaulted` in
`domain/strategy/operational_spec.py`; `value_source` in
`domain/strategy/value_source.py`; `bind_values`, `read_again` and
`BoundValue.unset` in `domain/strategy/operational_spec.py`; `value_label` and
`term_labels` in `domain/strategy/value_label.py`; `get_parameter_options` in
`ai/tools/standalone/catalog_discovery.py`; `vocabularies_under` in
`ai/tools/standalone/_frame_measure.py`; `stated_words` in
`domain/strategy/value_source.py`; `ParameterRules.source`
and `text_query` in `services/strategies/parameter_rules.py`; `bound_values` in
`ai/tools/standalone/_frame_sources.py`; `assumption_constraints` in
`ai/lead/ledger_sections.py`; `AssumedValueCaveat` in `domain/value_caveats.py`;
`measure_binding` and `TurnCounts` in
`services/strategies/measurements.py`; `default_reading` in
`services/strategies/pick_readings.py`; `PARAMETER_RULES` and `site_fixed` in
`services/strategies/parameter_rules.py`; `vocabulary_labels` in
`services/strategies/value_labels.py`; `UnmeasuredValueCaveat` and
`ChoiceCaveat` in `domain/value_caveats.py`; `stated_texts`, `stated_run` and `stated_by_labels` in
`domain/strategy/value_source.py`; `in_the_sites_scale` and
`stated_on_the_other_scale` in `domain/log2_scale.py`; `on_the_sites_scale`
and `stated_by_their_labels` in `ai/tools/standalone/_frame_sources.py`;
`Criterion.counted_at` in `domain/strategy/operational_spec.py`;
`bound_count` and `record_and_count_criterion` in
`ai/tools/standalone/_frame_count.py`; `measurement_clauses` in
`domain/strategy/measurement_clauses.py`.
Guarded by `tests/unit/domain/strategy/test_a_value_says_who_set_it.py`,
`tests/unit/domain/strategy/test_a_value_is_stated_only_whole.py`,
`tests/unit/services/strategies/test_every_parameter_kind_is_measured_and_labelled.py`,
`tests/unit/domain/test_a_pick_names_the_options_not_taken.py`,
`tests/unit/ai/tools/test_a_hidden_choice_is_bindable.py`,
`tests/unit/services/strategies/test_a_choice_is_named_only_when_it_changes_the_count.py`,
`tests/unit/services/strategies/test_a_binding_is_measured_against_its_other_readings.py`,
`tests/unit/ai/tools/test_a_bind_records_its_measurements.py`,
`tests/unit/ai/tools/test_a_refused_count_binds_nothing.py`,
`tests/integration/ai/test_a_bind_is_measured_live.py`,
`tests/unit/ai/tools/test_frame_spec_sheet.py`,
`tests/unit/domain/test_a_log2_value_shows_its_fold.py`,
`tests/unit/domain/strategy/test_a_value_is_stated_in_the_researchers_words.py`,
`tests/unit/domain/strategy/test_an_unset_value_is_the_sites.py`,
`tests/unit/domain/strategy/test_a_bound_value_is_built_with_its_sheet.py`,
`tests/unit/ai/tools/test_a_bound_value_is_sourced_by_its_sheet.py`,
`tests/unit/ai/models/test_mock_unset_value_arcs.py`,
`tests/unit/ai/tools/test_a_value_binds_in_the_researchers_words.py`,
`tests/unit/ai/tools/test_an_eda_cut_binds_on_the_computes_scale.py`,
`tests/unit/ai/lead/test_the_facts_count_an_unread_bind_at_its_step.py` and
`tests/unit/ai/lead/test_derive_constraints.py`.
