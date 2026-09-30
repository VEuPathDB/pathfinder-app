---
type: Decision
title: The product renders the facts; the reply narrates
description: Every turn that holds a fact writes a typed facts part before the Lead's reply, built from the strategy, the spec and the ledger and rendered by React; one contract rule refuses a reply that prints a number, an identifier or a link that no facts part of the thread showed and the researcher did not write, and twelve rules that held the prose to one fact each were retired. Rendering the facts as markdown in the reply, and keeping the per-fact rules beside the facts part, were rejected.
tags: [agents, lead, turn-contract, reply, facts]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-30T18:00:00Z }
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
  reads "not set (site placeholder)" with no measurement. A bound parameter the sheet hides and offers no entries for (`Criterion.hidden_params`, a phyletic profile pattern) draws no row, and a value a count measures never shows a not-measurable clause. A measurement a row shows as a note
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
- the provider's or the site's refusal whole, with only a link's query left out because a
  query can carry a credential.

React renders it (`content/parts/DataFacts.tsx`, one test id per fact kind and per step row),
beside the reply in the default thread.

The turn contract's prose rule is `fact_outside_the_block`: the reply prints no number, no
identifier and no http link that is not a fact. A fact is what the page shows: every line a
facts part of the thread held (`StrategyDomainState.facts_shown`, kept by `show_the_facts` from
`TurnFacts.held_lines`), this turn's facts, the variant labels and counts a comparison card of
the turn shows, and the researcher's own messages. A number is also held when it is one of
the turn's typed counts (`TurnFacts.counts`: each step's count and the result's, each count
before an edit; with every count a completed comparison returned, `VariantComparison.counts`:
genes, result, unique and shared) or the difference of two of them
(`TurnRecord.held_counts`); differences are taken over that set only, never over every
number the text writes. The refusal names only the refused tokens and says every count the
facts show stays in the reply. A source word about a value ("the site's default", "chosen",
"you asked for") must fit the source its facts row shows (`TurnFacts.sources_named`, read by
`facts_in_prose.misattributed_source`), and a word of a record's product the reply writes
another way beside the record's own words is refused (`facts_in_prose.altered_record_text`).
`TurnRecord.prose_refusal` answers all three in that order. What a tool returned and no facts part draws
is no fact. A record's own words sit on a held line of their own (`RECORD_WORDS`): a number in
them is held only beside the same word ("chromosome 6" holds "chromosome 6", never "6 more
genes"). A number written against its unit is that number ("37C", "37°C"), and a number word
from "three" up is its digits; "one" and "two" are read as words. A value an option of the reply's own
`askedQuestions` offers is a choice, not a claim, and may be named. A number or a token a fact
holds whole may be named; a bare number no fact holds is refused. A number joined to a word by a
hyphen ("36-gene", "1.5-fold") and an ordinal ("95th") are that number. A token with a digit is
an identifier only when it has an identifier's shape (`domain/scratchpad_facts.hard_facts`: a
site's gene id, a step id, a search name; or a snake_case, colon-joined or uuid token, or a name
the product uses and never shows), so a product word such as "GP63" or a strain such as "SC5314"
is prose. A range, a ratio and a date are numbers, held only as the facts write them
("2-99" is held where the facts show "2-99", "2 to 99" is not), and a number is compared
without its thousands separator; a comma is a separator only between a digit and exactly
three more ("21,60" is not 2,160). A number in scientific notation is its decimal value
("1e-5", "1E-05" and "0.00001" are one number). The
Lead's instruction says the facts are shown beside the reply, and that the reply explains,
recommends and asks. `LeadResponse.sources` is gone: the references a turn read are facts.

Retired with their tests and messages: `unnamed_search`, `misstated_count`,
`counted_in_the_wrong_unit`, `machine_words`, `unstated_gap`, `unstated_caveat`,
`misstated_control_list`, `misnamed_deletion`, `unretrieved_source`, `unbacked_evidence`,
`unwritten_gene_set`, `unwritten_control_set`.

The eval extract reads each turn's facts part beside its reply (`chunk_reader.read_turns`), the
runner scores what a turn showed (its facts lines, then its reply), and `ObservedOutcome.assumed`
counts the narrowing values the request did not state that the last facts part does not show
with who set them (`uncarried_assumptions`).

# Why

Each retired rule held the prose to one fact the product already held, and the model restated
the fact in a new shape on the next site or phrasing. Rendering the fact from the record makes it
right by construction, and one rule over one string replaces twelve over the ways a sentence can
restate a count.

# What was rejected

- **Rendering the facts as markdown in the reply.** The reply would still be a string the model
  could edit, and the eval and the e2e specs would read counts out of prose again.
- **Holding the prose to this turn's facts only.** A later turn that asks for a count an earlier
  turn showed ("how many before the narrowing?") could then answer only with a number the page
  does not hold beside it, or with none: the correct 2,160 was refused and a wrong 82 from a
  measurement clause stood.
- **Showing a record a replaced step listed under "read earlier, no longer in the strategy".**
  The facts part is the copy of the strategy the researcher holds, and such a record is
  evidence for none of its steps; a copy of the page would still carry it beside the result.
  The reply may not name it either: held is what the page shows.
- **Keeping the per-fact rules beside the facts part.** A rule that asks the prose to restate a
  number the facts part shows asks for the duplicate that disagrees with it.
- **Holding every value a tool of the turn returned.** The guard then held ids and numbers the
  page never showed, and the refusal told the reply to point at facts that were not there; a
  chromosome number a record read made "6 more genes" pass.
- **Recording the counts before an edit at each write tool.** The delete, clear and replace
  paths had no copy, and a second bind in one turn recorded the first bind's count as "before".
- **Refusing every number, even one the facts part shows.** The first version did, on the
  argument that a restated count is the same count in a second place. Measured on the recorded
  dry-UAT turns, it refused 8 first drafts whose every printed token but two was a value the
  facts showed: a step count ("10", "4", "178", "3"), a saved set's count ("48"), a root count
  ("2", "4") and a parameter value ("0.7"). Each refusal cost one Lead request that re-sent the
  whole context, 18,454 to 22,180 tokens, and removed a true value. A number the facts hold
  cannot disagree with them, because the check reads it from the same text the researcher sees.
  With the sharpened scope 7 of those 8 drafts pass; the eighth still prints two product names
  ("A2", "Cortexin-1") the facts do not show.

# What would prove this wrong

`tests/unit/ai/lead/test_the_prose_holds_no_fact_outside_the_block.py` holds the rule,
`tests/unit/ai/lead/test_the_facts_hold_the_thread.py` the thread's facts, the counts before an
edit, the sources by step and the resolved genes,
`tests/unit/ai/lead/test_the_facts_hold_what_the_turn_read.py` the listings and the held numbers,
`tests/unit/ai/lead/test_the_strategy_at_arrival_is_recorded.py` the record the counts before derive from,
`tests/unit/ai/lead/test_the_turn_shows_its_facts.py` the builder,
`tests/unit/ai/graph/test_the_facts_are_written_before_the_reply.py` and
`tests/unit/ai/graph/test_the_text_beside_a_card.py` the order on the wire, and
`tests/unit/ai/models/test_mock_replies_meet_the_contract.py` every mock arc's reply.
