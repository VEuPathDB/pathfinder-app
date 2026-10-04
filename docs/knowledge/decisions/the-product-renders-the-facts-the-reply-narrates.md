---
type: Decision
title: The product renders the facts; the reply narrates
description: Every turn that holds a fact writes a typed facts part before the Lead's reply, built from the strategy, the spec and the ledger and rendered by React; the reply writes each fact as a reference the emitter renders from the same facts, and one rule refuses prose that writes a fact itself or names one the facts lack. A guard that read the model's free text for facts, widening that guard, and rendering the facts as markdown in the reply were rejected.
tags: [agents, lead, turn-contract, reply, facts]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-09-30T20:00:00Z }
status: stable
---

# What was decided

`domain/turn_facts.py::TurnFacts` is the data part `data-facts`. `ai/lead/turn_facts.py`
builds it from the Lead's deps, and `ai/graph/_lead_facts.py::show_the_facts` writes it once
per turn, before the first reply the turn shows: before the held card replies when the turn
ends on a card, else before the typed reply's text. A turn whose facts hold nothing writes none.
It holds:

- the steps under the strategy's root in tree order (each after its inputs), by display name,
  each with its count and each bound value by the name the site shows, its value, the
  vocabulary label read for it and who set it; a default or chosen value carries its
  measurement clauses (`measurement_clauses.counted_clauses`), a card value its option label,
  a stated or held value nothing more; a placeholder the site left (`BoundValue.placeholder`)
  reads "not set (site placeholder)" with no measurement. A bound parameter the sheet does not show and whose vocabulary offers no choice (`BoundValue.visible` false: a phyletic profile pattern, an RNA-Seq `dataset_url`) draws no row, no ledger value line and no reason term, and still rides the step; a hidden parameter with more than one entry is a choice and keeps its row, and a value a count measures never shows a not-measurable clause. A measurement a row shows as a note
  is no caveat as well (`TurnFacts._one_drawer_per_measurement`), and a clause or a caveat
  names a pick of more than three values by its size (`measurement_clauses.shown_value`); the
  row shows it whole. An analysis row names its filters and its measured variable as the study
  does (`AnalysisBinding.shown_subset`, `value_variable_name`, read by the export) and each
  chosen cut beside the count the compute holds at its other reading (`CutTallies`). While nothing is built the bound criteria of the spec
  stand in as a draft, each with the count it bound at;
- the root count, the titles of the steps the turn deleted, and the strategy link the build
  recorded; the pre-turn records the root and every step's count once, when the message
  arrives (`TurnMarkers.at_arrival`), and every count before an edit derives from that record
  (`TurnMarkers.count_before`, `root_count_before`): a step this turn's writes moved shows the
  count the message found, a step the turn created or left unchanged shows none, an export
  that took a step's place shows that step's count, and the root shows the count of the root
  the message found after any write, a delete included;
- the caveats (`caveats_for` over the verdict on the strategy, so an assumed value shows even
  before a check), the gaps (with each requirement a framing pass found no search on the site
  states, `FrameResult.unstated`, in words a researcher message carries, so a turn that builds
  nothing still shows what the site lacks), the column fits, and the requirements the researcher withdrew or
  an answer replaced (`retired_requirements`), shown as retired and never as gaps;
- the gene sets and control sets this turn saved, the control results it measured, a
  stopped check;
- every record a read of the turn returned, as a `SourceFact` under the step whose listing gave
  it (`TurnMarkers.listed_from`, the WDK step a sample or a step read listed the gene from) with
  its product, its other words (gene name, chromosome, and the orthologs of the one organism a read asked for with `ortholog_organism`; the first rows of the ortholog table are never drawn) and the fit the check judged (`VerificationReview.sampled_genes`), never under the
  root when it is a leaf's; a record a step the live strategy no longer holds listed is no
  source; every id a listing or a sample of the turn returned, as a `ListedFact` under the
  step it listed (`TurnMarkers.listings`), each id linked to its record page; the other references the turn read; and the genes the message names
  that the classification gate resolved, each with its site record link (`named_genes`);
- the counts each completed comparison of the turn returned (`comparisons`, a
  `domain/comparison_facts.py::ComparisonFact` per `compare_search_variants` call, read from
  `VariantComparison.fact`: each variant that ran with its genes, its unique genes and its
  result in place, the wire value of each parameter whose value differs between the variants,
  and the genes each pair shares); the comparison card shows them, so the facts part draws no
  row for them, and the text form of the facts (`TurnFacts.lines`) gives each variant a row with
  the values it differs by beside its count;
- the provider's or the site's refusal whole, with only a link's query left out because a
  query can carry a credential.

React renders it (`content/parts/DataFacts.tsx`, one test id per fact kind and per step row),
beside the reply in the default thread.

The reply writes no fact itself. `LeadResponse.prose` and a card's `reply` hold references,
and `domain/reply_references.py::render_reply` replaces each with the fact it names:

| reference | renders |
|---|---|
| `[count:<step_id>]` | the step's count, thousands-separated, with the record noun |
| `[before:<step_id>]` | the step's count before this turn's edit |
| `[root]`, `[root_before]` | the root's count now and before the edit |
| `[last_change:before]`, `[last_change:after]` | the root's count before and after the strategy's most recent change, made by this turn or an earlier one |
| `[diff:<a>,<b>]` | the difference of two counts; a side is a step id, `root`, `root_before`, `before:<step_id>`, `last_change:before`, `last_change:after` or `compare:<variant>`, and the two sides differ |
| `[value:<step_id>.<param>]` | the bound value with its label (`ParameterFact.shown`); a label that repeats the value is dropped on the type |
| `[source:<step_id>.<param>]` | who set it: "you stated", "your answer on a card", "the site's default", "chosen", "held by the strategy" |
| `[compare:<variant>]` | the variant's genes; `:unique`, `:result`, and `[compare:<a>,<b>:shared]` |
| `[stat:<id>.<row>]` | one value of a statistic the EDA service computed on the thread: a component's share of variance, a test's value, p-value or interval, a group's median, a count with its noun (`domain/statistic_facts.py`) |
| `[record:<record_id>]` | a read, listed or resolved record's id linked to its page, with its product |
| `[url]` | the strategy's link |

The emitter renders once, from the facts object the turn shows:
`ai/graph/_lead_facts.py::show_the_facts` keeps the `TurnFacts` it writes on the run capture,
`ai/graph/_lead_capture.py::_emit_residual_prose` renders the typed reply from it, and
`ai/graph/_lead_card_hold.py::CardHold.release` renders each held card's reply from it. The
replies the runtime writes when a run ends without one (`ai/graph/_lead_stops.py`) take the same
path; they are the runtime's own text and name no reference.

The turn contract's only check on prose content is `unrendered_prose`
(`turn_contract.unrendered_prose`, `reply_references.prose_faults`). It reads each token's
shape, not the presence of a digit. It refuses a number outside a reference (`_A_NUMBER`:
digits with thousands separators, a decimal point, an exponent, a range, a percent or a glued
unit, "37C", "5x", "2-fold", "1e-6", and a log scale, "log2"; an item number that starts a
line is the list's mark only when it is 1 or follows the item number before it), an
identifier shape (`domain/scratchpad_facts.hard_facts` gene ids and search names such as
`PF3D7_0908300`, `PKNH_1234500`, `TGME49_233460`, `LmjF.36.0010`; `_AN_ACCESSION`, the Pfam,
InterPro and Ensembl accessions; a snake_case, colon-joined or uuid token, so a GO term and a
step id), a link, a
source word ("default", "chosen", "stated", "you asked"), a reference that names nothing
the facts hold, and a bracket outside a reference that nests, opens with a reference's name
(`[count:]`, `[URL]`) or is never closed. A bracketed word that names no reference (`[mock]`)
is prose and renders as written. A name that mixes letters and digits in neither shape is
prose ("PfEMP1", "IL-6", "CD4+", "H3K27me3", "ME49", "3D7", and a version glued to a tool's
name, "SignalP-6.0"). A number that a researcher message of the thread writes as a whole
token is the researcher's word and is prose ("chromosome 1", "p 0.001"); an identifier shape
the message writes is still refused, since `[record:]` renders it (`TurnFacts.request_messages`,
kept off the wire). A rendered value the researcher did not state shows the decimals of the
parameter's published initial value, never more than four significant digits, and four
significant digits where those decimals show zero (`BoundValue.rounded`,
`domain/strategy/number_precision.py`); the facts row and the `[value:]` reference show the same
text. The check reads a number word only where the grammar places a reference
(`domain/reference_placement.py`): a number word (one to twelve, "twice", a "<word>-fold") in the
clause of a `[value:]`, `[count:]`, `[before:]`, `[root]`, `[root_before]`, `[last_change:]` or
`[diff:]` reference is refused, since the reference stands in place of the number; "both" names two
inputs and stands. A count noun ("gene", "record", their plurals, the strategy's record noun)
next after a count reference, or after only continuation words ("more", "fewer", "additional",
"matching"), is refused, since the reference renders with its
noun. Elsewhere a small count of steps in words is structure. Its correction
(`contract_messages.unrendered_prose_message`) names each token with the references that
render it: a count, a difference of two counts, a comparison count, a value, a record, the link
or the source of a row; a number that a read record's product holds names that record's
`[record:]`, which renders the product. It is refused on every answer and takes no part in
the one correction the other rules share (`to_correct`). Every card's reply of a response is
read whole (`to_correct(..., replies)`), so no reply is rendered that the check did not read. The
facts are this turn's: a count an earlier turn showed is rendered only while a step still holds
it, except the counts of the strategy's most recent change, which stay a fact until the next
change (`TurnFacts.last_change`, read from the thread's revision rows by
`revision_ops.last_change` when the message arrives and from the live tree once the turn writes,
so it never disagrees with `[root_before]` and `[root]`). Retired with their tests: `fact_outside_the_block`, `facts_in_prose.py`
(`outside_the_facts`, `misattributed_source`, `altered_record_text`), their three messages,
`TurnRecord.prose_refusal`, `held_facts`, `held_counts`, `machine_names`, `TurnFacts.held_lines`,
`TurnFacts.counts`, `TurnFacts.sources_named`, `RECORD_WORDS`, `VariantComparison.counts`, and
`TurnMarkers.facts_corrected`, `compared_labels`, `compared_counts`. The Lead's instruction and
the schema descriptions of `LeadResponse.prose` and `CardReply` (`card_reply.REPLY_REFERENCES`)
state the grammar, and the mock model writes references (`count_answer_arcs.derived_count`,
`facts_arcs.list_ids`). `LeadResponse.sources` is gone: the references a turn read are facts.

Retired with their tests and messages: `unnamed_search`, `misstated_count`,
`counted_in_the_wrong_unit`, `machine_words`, `unstated_gap`, `unstated_caveat`,
`misstated_control_list`, `misnamed_deletion`, `unretrieved_source`, `unbacked_evidence`,
`unwritten_gene_set`, `unwritten_control_set`.

The eval extract reads each turn's facts part beside its reply (`chunk_reader.read_turns`), the
runner scores what a turn showed (its facts lines, then its reply), and `ObservedOutcome.assumed`
counts the narrowing values the request did not state that the last facts part does not show
with who set them (`uncarried_assumptions`).

# Why

A check on free text reads a sentence the model wrote and guesses which of its tokens are facts.
It refused true values (a difference of two shown counts, a count a comparison returned, a
parameter value written against its unit) and made the model rewrite correct text, and each
fix widened the guess. A reference is a fact by construction: the product writes the number
from the same object the facts part shows, so the reply cannot disagree with it, and the only
thing left to check is whether the prose writes a fact itself.

# What was rejected

- **Reading the model's free text for facts** (`fact_outside_the_block`, with its source-word
  and record-text rules). Its tokens were guessed from shapes, so a thousands separator, a unit,
  an ordinal, a hyphen, a record's own words and a question's options each needed a rule, and a
  true count outside the held set was refused.
- **Widening the prose guard to accept differences and comparison counts.** Another rule on
  prose, with the same false-positive shape.
- **A validation context on the output type.** The check needs the turn's facts, which only the
  run holds, and the runtime writes its own stop replies from the record, with counts in them;
  the output validator reads the facts from the run and leaves the runtime's text alone.
- **Rendering the facts as markdown in the reply.** The reply would still be a string the model
  could edit, and the eval and the e2e specs would read counts out of prose again.
- **Showing a record a replaced step listed under "read earlier, no longer in the strategy".**
  The facts part is the copy of the strategy the researcher holds, and such a record is
  evidence for none of its steps.
- **Keeping the per-fact rules beside the facts part.** A rule that asks the prose to restate a
  number the facts part shows asks for the duplicate that disagrees with it.
- **Recording the counts before an edit at each write tool.** The delete, clear and replace
  paths had no copy, and a second bind in one turn recorded the first bind's count as "before".

# What would prove this wrong

`tests/unit/domain/test_the_reply_is_rendered_from_the_facts.py` holds every reference kind and
every fault, `tests/unit/domain/test_a_reference_renders_from_a_recorded_turn.py` every kind over
the facts two recorded turns showed, the differences of every pair of their counts and the
malformed brackets, `tests/unit/ai/lead/test_the_reply_names_facts_by_reference.py` the contract on a
typed reply and a card's reply, `tests/unit/ai/graph/test_the_reply_is_rendered_from_the_facts_it_shows.py`
that the text part and the facts part come from one `TurnFacts`,
`tests/unit/ai/lead/test_the_facts_hold_the_thread.py` the counts before an edit, the sources
by step, the resolved genes and the comparison counts,
`tests/unit/ai/lead/test_the_facts_hold_what_the_turn_read.py` the listings,
`tests/unit/ai/lead/test_the_turn_shows_its_facts.py` the builder,
`tests/unit/ai/graph/test_the_facts_are_written_before_the_reply.py` and
`tests/unit/ai/graph/test_the_text_beside_a_card.py` the order on the wire, and
`tests/unit/ai/models/test_mock_replies_meet_the_contract.py` every mock arc's reply. The
corpus cases `uat-core-d-microsporidiadb` and `uat-core-a-cryptodb` hold the rendered counts
on the real model; a count question answered with no count on them proves the grammar is not
followed.
