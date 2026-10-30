---
type: Decision
title: The product renders the facts; the reply narrates
description: Every turn that holds a fact writes a typed facts part before the reply, built from the strategy, the spec, the ledger and the turn's reads and rendered by React; the reply is a note beside it that writes no number and no link of the turn and names a record only as [record:<id>], and one bounded check refuses a note that writes one. A guard that read the model's free text for facts, a reference grammar the reply wrote in place of each fact, and rendering the Lead's facts as markdown in the reply were rejected.
tags: [agents, lead, turn-contract, reply, facts]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-30T00:00:00Z }
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
  reads "not set (site placeholder)" with no measurement. A bound parameter the sheet does not
  show (`BoundValue.visible` false: a phyletic profile pattern, an RNA-Seq `dataset_url`, a
  hidden `channel`) draws no row, no ledger value line and no reason term, and still rides the
  step, and a value a count measures never shows a not-measurable clause. A measurement a row
  shows as a note is no caveat as well (`TurnFacts._one_drawer_per_measurement`), and a clause
  or a caveat names a pick of more than three values by its size
  (`measurement_clauses.shown_value`); the row shows it whole. An analysis row names its filters
  and its measured variable as the study does (`AnalysisBinding.shown_subset`,
  `value_variable_name`, read by the export, or by the pre-turn for a step the graph editor or
  the site added) and each chosen cut beside the count the compute holds at its other reading
  (`CutTallies`). While nothing is built the bound criteria of the spec stand in as a draft,
  each with the count it bound at;
- the root count, the titles of the steps the turn deleted, the strategy's last change and the
  strategy link the build recorded; the pre-turn records the root and every step's count once,
  when the message arrives (`TurnMarkers.at_arrival`), and every count before an edit derives
  from that record (`TurnMarkers.count_before`, `root_count_before`): a step this turn's writes
  moved shows the count the message found, a step the turn created or left unchanged shows
  none, an export that took a step's place shows that step's count, and the root shows the
  count of the root the message found after any write, a delete included;
- the caveats (`caveats_for` over the verdict on the strategy, so an assumed value shows even
  before a check), the gaps (with each requirement a framing pass reports the site has no
  search for, `FrameResult.requirement_problems`, in the words the thread holds, so a turn that
  builds nothing still shows what the site lacks), the column fits, and the requirements the
  researcher withdrew or an answer replaced (`retired_requirements`), shown as retired and never
  as gaps; a withdrawn combination shows only the sides a delete removed
  (`RetiredRequirement.shown_requirements`), never a side a step can still answer; a turn whose
  change carried the records to another organism adds a `records_organism` caveat
  (`domain/organism_caveat.py::RecordsOrganismCaveat`) that names that organism and the seed's;
- the gene sets and control sets this turn saved, the control results it measured, a stopped
  check, and that the last check of the strategy failed (`failed_check`, shown on any turn but
  an audit turn while that verdict stands), with its reason unless a gap of the facts already
  states it;
- every record a read of the turn returned, as a `SourceFact` under the step whose listing gave
  it (`TurnMarkers.listed_from`, the WDK step a sample or a step read listed the gene from) with
  its product, its other words (gene name, chromosome, and the orthologs of the one organism a
  read asked for with `ortholog_organism`; the first rows of the ortholog table are never drawn)
  and the fit the check judged (`VerificationReview.sampled_genes`), never under the root when
  it is a leaf's; a record a step the live strategy no longer holds listed is no source; every
  id a listing or a sample of the turn returned, as a `ListedFact` under the step it listed
  (`TurnMarkers.listings`), each id linked to its record page; the other references the turn
  read; and the genes the message names that the classification gate resolved, each with its
  site record link (`named_genes`);
- the counts each completed comparison of the turn returned (`comparisons`, a
  `domain/comparison_facts.py::ComparisonFact`: each variant that ran with its genes, its result
  in place and the wire value of each parameter whose value differs between the variants). A
  `compare_search_variants` comparison is on its card (`on_its_card`), so the facts part draws no
  row for it; a `count_search` count has no card, so the facts part draws it as "label: N
  genes". The text form of the facts (`TurnFacts.lines`) gives every variant a row;
- which of the asked genes each membership check held (`memberships`, the
  `domain/membership_facts.py::MembershipFact` that `genes_in_search` records): held, not held
  and past the capped read, each gene linked to its record page;
- each read with no card of its own (`reads`, a `domain/read_facts.py::ReadFact`): an audit read
  of this turn (a run, a list of runs, a page of findings, a finding with its stored certainty
  and evidence, a plan, a start, a rate, a gene check) and a computed comparison the thread
  holds; its title and the rows of its answer at most two named fields deep, each labeled in
  words, with no link and at most forty rows;
- the column tallies the turn ran (`tallies`), which their card draws; their text form is "In
  all", "Values" and one "value: count" line each;
- the records the conversation showed last (`shown_before`, the `TurnFacts.shown_records` of the
  latest facts part that showed any, kept as `StrategyDomainState.shown_records`), which a record
  reference of a later note links; the field stays off the wire and out of `lines` and
  `record_ids`, so it is no fact of this turn;
- the provider's or the site's refusal whole, with only a link's query left out because a query
  can carry a credential.

React renders it (`content/parts/DataFacts.tsx`, `DataFactsNotices.tsx`, `FactsRecords.tsx` and
`FactsReads.tsx`, one test id per fact kind and per step row), beside the reply in the default
thread. The statistics the EDA service computed have their own card, and the Lead's pinned
statistics list each as "row = value" for the Lead to read.

**What shows where, by answer.** A strategy built or edited: the steps with their values and
who set each, the result count with its noun, the last change, the strategy link, and the
caveats and gaps of the computed verdict beside the evidence card the check leaves. A tally or
ranking: the tally card's table of value and count. A gene or record read: the records table,
each record with its product, its other words and its fit. An audit read: its `ReadFact`. A
failed or refused turn: one notice line (`stopped_check`, `failed_check`, `refusal`,
`unverified`, `unchecked`).

**The note.** `LeadResponse.prose`, a card's `reply` and `AuditReply.prose` are a note beside the
facts: what they mean for the question, why this reading answers it, and what to do next
(`ai/lead/card_reply.py::REPLY_NOTE`, read by the schema descriptions and the Lead's
instruction). A name is written as it stands, letters and digits together ("3D7", "ME49",
"PfEMP1", "SignalP-6.0", "GO:0016301"). The one reference is `[record:<record_id>]`:
`domain/reply_note.py::render_note` links a record the facts can cite
(`TurnFacts.citable_records`: this turn's reads, listings, checks and resolved genes, then the
records shown last) to its page and drops any other. The emitter renders once, from the facts
object the turn shows: `show_the_facts` keeps the `TurnFacts` it writes on the run capture,
`ai/graph/_lead_capture.py::_emit_residual_prose` renders the typed reply from it and
`ai/graph/_lead_card_hold.py::CardHold.release` each held card's reply. The conversation events
hold the rendered text, so a saved conversation replays with no renderer. The audit assistant's
reply text is each `ReadFact` as markdown, then the rendered note
(`ai/audit/reply.py::reply_text`).

**No model-written link reaches the reader.** `domain/written_links.py` reads every link a
text writes after it decodes HTML entities: each inline link and image destination, each
autolink, each `href` or `src` of an HTML tag, and each bare address with a scheme and `//`,
`www.`, a protocol-relative `//host.`, or `mailto:`, `javascript:`, `vbscript:`, `data:`,
`file:`, `tel:` or `doi:`. `render_note` shows an inline link or image as its words and drops
every other one before it links the record references, so the only link a note shows is one it
rendered itself. A read's title, labels and values are escaped in the audit assistant's
markdown (`ReadFact.markdown`), and a row whose value holds a link is not shown.

**The one check on the note.** `domain/reply_note.py::note_facts` returns each link a note
writes, on any turn, and each number it writes, once, when the turn's facts hold site data
(`TurnFacts.holds_site_data`); a note on a turn that read nothing from a site writes numbers
freely. A number a researcher message writes as a whole token is their word, a list's item numbers are
marks, and a name that mixes letters and digits is prose. The turn contract refuses such a note
as the `note_facts` mismatch (`contract_messages.note_facts_message`, which names each token to
take out) on a bound of its own
([the refusal bound](an-output-check-refuses-at-most-twice-and-never-on-the-last-answer.md)),
and reads every card reply of a response whole. Past the bound the note is shown and the facts
part carries `UNCHECKED_PROSE`; nothing is withheld. The audit assistant holds its note to the
same check (`ai/audit/reply.py::hold_the_reply`), and an audit synthesis summary and each
section's cause and confirmation write no number and no link (`ai/audit/synthesis.py`). The turn contract's other rules read what the turn did, not
the note's wording ([one turn contract](one-turn-contract.md)).

Retired with their tests: the reference grammar (`[count:]`, `[before:]`, `[root]`,
`[root_before]`, `[last_change:]`, `[diff:]`, `[value:]`, `[source:]`, `[compare:]`, `[stat:]`,
`[cite:]`, `[tally:]`, `[url]`) and its modules (`reply_references`, `reference_grammar`,
`reference_placement`, `reply_notes`, `reply_suggestions`, `source_words`, `tally_labels`,
`strategy/comparison_placement`), the withheld reply, the placement, list and reference fault
messages, the note labels, `LeadResponse.strategy_changed`, the `factId` of an audit read and a
computed comparison, and the rules `unrendered_prose`, `misreported_change`, `stopped_check`,
`failed_check`, `unnamed_record_organism` and `unplaced_breakdown`, each of which the facts part
now states. Earlier: `unnamed_search`, `misstated_count`, `counted_in_the_wrong_unit`,
`machine_words`, `unstated_gap`, `unstated_caveat`, `misstated_control_list`,
`misnamed_deletion`, `unretrieved_source`, `unbacked_evidence`, `unwritten_gene_set`,
`unwritten_control_set`.

The eval extract reads each turn's facts part beside its reply (`chunk_reader.read_turns`), the
runner scores what a turn showed (its facts lines, then its reply), and `ObservedOutcome.assumed`
counts the narrowing values the request did not state that the last facts part does not show
with who set them (`uncarried_assumptions`).

# Why

A fact the product writes from the object the facts part shows cannot disagree with it. A note
that states no fact leaves one thing to check: whether it writes one. Every rule that policed
how a reply placed a fact refused true text and made the model rewrite it; a note places no
fact, so there is no placement to police.

# What was rejected

- **A reference grammar the reply wrote in place of each fact.** The model wrote
  `[count:<step_id>]`, `[value:<step_id>.<param>]`, `[stat:<id>.<row>]` and a dozen other
  kinds, the emitter rendered them, and rules on placement, nouns and repetition held the prose
  to the grammar. The rules policed a trap the grammar made: a count reference rendered its own
  noun, so the noun the model wrote after it doubled ("797 groups of ortholog groups"), and a
  value written beside the reference that rendered it doubled too. The rule against a written
  number pushed the model to spell names out ("three-D-seven" for 3D7). Over 61 recorded reply
  refusals in live QA runs, 14 refused a correct draft and 12 retries were worse than the draft
  they replaced.
- **Reading the model's free text for facts** (`fact_outside_the_block`, with its source-word
  and record-text rules). Its tokens were guessed from shapes, so a thousands separator, a unit,
  an ordinal, a hyphen, a record's own words and a question's options each needed a rule, and a
  true count outside the held set was refused.
- **Rendering the Lead's facts as markdown in the reply.** The reply would still be a string the
  model could edit, and the eval and the e2e specs would read counts out of prose again. The
  audit assistant has no data part of its own, so its facts are markdown the product writes
  before the note, never text the model writes.
- **Withholding a note past the bound.** It hid the interpretation the researcher asked for
  while the facts part already showed the true values; the unchecked notice says what the note
  is.
- **Showing a record a replaced step listed under "read earlier, no longer in the strategy".**
  The facts part is the copy of the strategy the researcher holds, and such a record is
  evidence for none of its steps.
- **Keeping the per-fact rules beside the facts part.** A rule that asks the prose to restate a
  number the facts part shows asks for the duplicate that disagrees with it.
- **Recording the counts before an edit at each write tool.** The delete, clear and replace
  paths had no copy, and a second bind in one turn recorded the first bind's count as "before".

# What would prove this wrong

`tests/unit/domain/test_a_note_names_records_and_writes_no_fact.py` holds the record links, the
dropped record, the names with digits and the free note of a turn with no site data;
`tests/unit/ai/lead/test_the_note_writes_no_fact_the_facts_show.py` and
`tests/unit/ai/lead/test_a_note_fact_has_a_bound_of_its_own.py` the contract on a typed reply and
a card's reply and its bound;
`tests/unit/ai/graph/test_the_reply_is_rendered_from_the_facts_it_shows.py` that the text part
and the facts part come from one `TurnFacts`; `tests/unit/ai/lead/test_a_failed_check_is_a_fact.py`,
`tests/unit/ai/lead/test_the_record_organism_is_a_fact.py`,
`tests/unit/ai/audit/test_an_audit_finding_read_is_a_fact.py` (a recorded fungidb finding) and
`apps/web/src/features/conversation/content/parts/FactsReads.test.tsx` the new facts;
`tests/unit/ai/lead/test_the_facts_hold_the_thread.py` the counts before an edit, the sources by
step and the resolved genes; `tests/unit/ai/lead/test_the_turn_shows_its_facts.py` the builder;
`tests/unit/ai/graph/test_the_facts_are_written_before_the_reply.py` the order on the wire; and
`tests/unit/ai/models/test_mock_replies_meet_the_contract.py` every mock arc's note. A live note
that spells a name out or restates a count the facts part shows proves the instruction is not
followed.
