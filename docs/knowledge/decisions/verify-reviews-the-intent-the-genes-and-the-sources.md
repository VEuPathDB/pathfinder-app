---
type: Decision
title: VERIFY reviews the intent, the genes and the sources
description: A check writes one typed row per requirement the researcher stated in any message of the request, reads each search step's columns over the whole step and samples only where no column shows, and may search the literature or the web; the code adds the rows the checker cannot omit, keeps only the genes and sources the turn read, refuses a success over an unmet row, and the evidence card shows all three. A model-only "looks right" verdict and a literature search on every turn were rejected.
tags: [verification, evidence, turn-contract, requirements, genes, literature]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: stable
---

# What was decided

A check is a review of the strategy against what the researcher asked. Its output
is `VerificationDigest.review`, a `VerificationReview` (`domain/evidence.py`) with
three typed lists, and the evidence card carries the same review.

## What VERIFY must do

- **One row per stated requirement.** `review.requirements` holds a
  `RequirementCheck` per requirement any message of the request states: `text` in
  the researcher's words, `turn` (the message's number), `answered_by` (criterion
  or step ids), `how` (search, parameter, structure, transform, analysis),
  `status` (met, unmet, unexpressed) and a one-line `note`. A met row names what
  answers it. Each combinator the researcher used ("and", "or", "but not",
  "except", "only those") is a row naming the combine that answers it.
- **The messages are the request.** `StrategyDomainState.request_messages` keeps
  every message classified for the request, oldest first, and is cleared with the
  request. `verification_scope` numbers them (with the original request and this
  turn's message) and pins them for VERIFY with the ledger's stated
  requirements, each word no search states and each combination the structure
  breaks (`pinned_researcher_request`).
- **The genes themselves.** A turn that built or changed the strategy reads the
  columns of each search step first (`read_step_columns`). Each numeric value a
  step's criterion binds is read against the search's own columns, by its WDK
  type: a number range is one bound with both sides, a number (or a string WDK
  marks `isNumber`) is one threshold whose direction the site does not state,
  read on the side that holds every record or reported with its count on each
  side. The columns read are those the search lists, that the site reports a
  histogram of, and that at most half the record type's searches carry. Each is one report over
  the whole step, the byValue column reporter for a record type column and the
  column's attribute histogram for a search's own column, and the answer is a
  `ColumnFit` ("840 of 840 genes fit # TM Domains (2 to 99)"). A sole such
  column's fit stands; several such columns stand only when every one holds
  every record inside the bounds, since no site data says which of them the
  bounds read (`ai/tools/standalone/_step_columns.py`). No column is chosen by
  its words. Only for a step whose search shows no such column, or whose
  columns disagree, does VERIFY sample the root
  (`get_sample_records`, one record at each of N offsets spread over the
  step, at most 100, so a gene family whose ids sort together fills one
  offset and not the sample) and read up to 8 sampled genes with
  `read_gene_record`, which refuses a gene no sample returned and every
  control. Each read is a `SampledGene`: `gene_id`,
  `product`, `organism`, `fits` (yes, no, unclear) and a one-line `why`.
  `read_gene_record` refuses, as a `ModelRetry` naming the records the check
  already read and `read_step_columns`, a record the check read and any read
  past `SAMPLED_GENE_LIMIT` (8); the budget is per check
  (`TurnMarkers.records_read`), so the refusal memory and the failed status
  see it.

## What VERIFY may do

- `research_literature_search` and `research_web_search` are VERIFY's to call
  when a claim about biology is one the records do not settle, or when a
  requirement's meaning needs a source. Nothing requires them. Each source relied
  on is a `Citation` in `review.sources` with a url, a DOI or a PMID and a why.

## What the code holds, whatever the checker wrote

- A study step's cut is compared with the request by `check_study_step`
  (`ai/tools/standalone/study_step.py`), each value rounded to the decimals
  the other is written with in its own units (a log2 cut of 0.585 meets a
  requested 1.5-fold). The computed checks are the digest's
  `constraint_report`, which the checker's schema omits; one not honored is a
  `CheckGap` of the digest and of the facts ("Not met: fold change asked 1.5,
  built 2.82843", `domain/constraint_check.py::shortfalls`) and refuses a
  success. A stated fold-change requirement is grounded by the same
  comparison against each fold-change threshold, in the scale the threshold
  declares (`domain/strategy/fold_grounding.py`); a threshold at another
  value is `substituted`, never grounded by its presence.
- A row whose text is a question the researcher asked (it ends with a
  question mark, or it and a question sentence of the request carry each
  other's words) is dropped: a question is answered in the reply, never a
  requirement or a gap (`domain/question_rows.py`). So is a row an ask of the
  intent gate carries: the whole message the gate classified as a
  `follow_up_question`, and each part of a request it lists in
  `UserIntent.asks` ("tell me how the two counts compare"), kept as
  `StrategyDomainState.researcher_asks` with the message it came from.
- A `met` row that only a text query answers is held to the records: a text
  value states the row (they share a word that is not filler) and every
  criterion that answers the row binds a text query. Such a row turns `unmet`
  only when no record shows it (`shown_by` names a sampled gene judged `yes`,
  every sampled gene is judged `yes`, or a column's fit holds every record) and
  a record shows it missing: a sampled gene judged `no` whose `why` a text
  query of the row states, or a column of its criteria that some record falls
  outside. An `unclear` judgement, or a `no` for another requirement, is no
  evidence of absence, since the checker judges each gene against the whole
  request (`domain/shown_requirements.py`). A held row that no record shows
  either way stays `met` and is marked `no_record_judged_it`: the Lead reads
  it as `unjudged` (`RequirementCheck.shown_status`), its note says "no
  sampled record judged it", and the eval counts it apart from `met`. A text query is a `TextQuery`, the
  value of a parameter of the free-text class of the parameter rules table
  that is not unset (`services/strategies/text_queries.py`,
  `parameter_rules.text_query`): a placeholder ("N/A", "(Example: chr22)"),
  the sheet default, a vocabulary term, a number and a phyletic code are none.
  A text query matches words, never the thing the words name. Such a row
  stays `met`, since its step answers it, and carries the runtime's mark
  `no_record_shows_it`, hidden from the check's schema: the Lead reads it as
  `unshown`, and its gap reads "no sampled record shows it", not "nothing in
  the strategy answers it". An `unmet` row names no step: the type refuses one
  with a non-empty `answered_by`, and a combine the strategy joins another way
  is named in the row's note. The sheets are read once per check
  (`search_definitions`); a sheet the catalog cannot read binds no text query.
- A row that names one of the researcher's uploads is `met` by the criteria
  that run on it: a user-dataset search (one that declares
  `userDatasetType`) whose dataset parameter binds the upload, or an
  analysis on the upload's study (`services/strategies/bound_uploads.py`,
  `shown_requirements.answered_by_uploads`). The upload's name comes from the
  researcher's VDI listing, read only when a criterion binds an upload id.
- A data-type requirement is grounded by the data a step runs on, never by
  a search's name: the VDI type of the upload the step reads (the one a
  user-dataset search's dataset parameter binds, or the study its analysis
  reads) for a step on an upload, and the curated expression search it runs
  for any other step. The check reads each step's upload before the checker
  runs and keeps the types on the state (`StrategyDomainState.upload_types`),
  so the ledger the checker and the Lead read grounds "RNA-Seq" on a DESeq
  step over an `rnaseqrc` upload (`constraint_grounding._ground_data_type`).

`review_held_to_the_turn` (`ai/lead/verify_review.py`) runs on every returned
digest before the verdict is recorded:

- Each stated combination the structure breaks (`first_combination_violation`,
  run per requirement) is an `unmet` structure row, and replaces a checker's row
  about the same criteria.
- Each word of `Criterion.unexpressed_qualifiers` is an `unexpressed` row; a row
  that names the word and calls it met is corrected.
- A sampled gene stands only when a `read_gene_record` of this turn read its
  record page, and a source only when a read of this turn returned every
  identifier it carries (`TurnMarkers.retrieved_as`).
- An `unmet` or `unexpressed` row is a typed gap and refuses a success
  (`verify_dispatch._held`), and each column fit short of every gene, or that
  the site does not show, is a typed caveat with its counts ("12 of 40 genes
  fit # TM Domains (2 to 99)", `domain/caveats.py`). The column fits are the
  reads' own (`TurnMarkers.column_fits`); a gene judged "unclear" is no caveat.

Before that, the verification agent's output validator refuses once per check a
digest that states a sampled-gene count its sample does not hold, lists a gene
no read returned, cites a source no read returned, or numbers a message the
request lacks.

## Where the gaps and caveats are shown

The facts part beside the Lead's reply links the strategy at the root it
holds now (`services/strategies/commit.py::live_strategy_url`, from the sync
state), and VERIFY's work order names the root's count from the same state,
never from the last build. The stopped-turn text reads the same link, and a
delete or an edit records the build as the live state holds it
(`services/strategies/graph_outcome.py::live_outcome`). The build outcome
holds no count: every count a reader shows (the build tool, the turn contract,
the case memory, the evidence card, the budget stop, the staleness check) is
read from the sync state through
`domain/strategy/build_outcome.py::built_counts`, the source the link reads. An EDA export that replaces a step,
and an edit that changes one in place, keep the count the step held before, so
a count that moves against a loosen or a tighten is a caveat. It shows each gap and each caveat of the
verdict on the strategy as its own sentence, and each column fit
(`ai/lead/turn_facts.py`, see
[the product renders the facts](the-product-renders-the-facts-the-reply-narrates.md)).
The reply says what each means for the question and restates none of their
numbers; the turn contract's `unrendered_prose` refuses a reply that
writes one. A caveat is a measurement the runtime reads from the records: a value
the checker writes is never one. A computed check short of the request is a
gap row of its own.

## What a check never claims

A requirement no message stated, a gene whose record it did not read, a source no
read of the turn returned, or a success over an unmet row.

# Rejected

- **A model-only "looks right" verdict.** A success over a strategy that joins
  two stated requirements with the wrong operator, or drops a qualifier, reads
  the same as a correct one. The structure breach and the unexpressed words are
  computed in code, so the checker cannot omit them.
- **A literature or web search on every turn.** Most checks are settled by the
  counts and the records; a mandatory search spends a research call and a model
  step to cite what the records already show, and a citation made to satisfy a
  rule is not evidence.
- **Sampling every gene.** A read per gene is a site call per gene; eight
  records show a misbinding (a histone in a signal-peptide set) at a bounded cost.
- **Choosing a column by the words it shares with a parameter.** Two columns
  of one search often share a word with the bound (`exon_count` and
  `gene_exon_count`), and the one the words pick can be the one the search does
  not filter on, which states genes outside a bound they are inside.
- **Pairing two numeric parameters by their names.** Two thresholds on
  different quantities have names one word apart (`min_sequence_count`,
  `min_spectrum_count`), and WDK already types a range as one `number-range`
  parameter.

- **The build outcome's url as the link, and its root count as the check's.**
  A delete does not record a build and a value-only edit puts no tree, so the
  outcome names a deleted step or no link, and a normal count change reads as
  a disagreement.
- **The checker's `honored`.** The checker restated a 2.83-fold cut as the
  1.5-fold the researcher asked for; a comparison the code can compute is the
  code's.
- **A met row on the query text.** A text search returns words, so a Boolean of
  names can match none of the genes it names.
- **Reading a value's letters to call it a text query.** Every string that is
  not a number read as text, so a GO, InterPro or location step at its
  placeholder default, and a phyletic pattern, turned each met row of the step
  into a gap. The parameter's class and its default decide, as the site
  publishes them.
- **The bound value's source as the unset test.** A value read from a strategy
  that already exists is `held`, so its source cannot tell a placeholder from a
  typed query; the sheet and the placeholder shapes can.
- **Every row a text step answers held to the records.** The organism a text
  step binds by vocabulary, and a row a second step without a text query also
  answers, turned into gaps on records that all showed the organism.
- **An unclear fit as absence.** The checker judges each gene against the
  whole request, so an `unclear` on one clause said nothing of the others.
- **A word list for an ask.** Which part of a message asks for an answer is
  the intent gate's classification of that message, not a list of verbs.

# What would prove this wrong

`tests/unit/ai/lead/test_verify_holds_the_review.py` holds the code rows,
`tests/unit/ai/lead/test_the_link_and_the_counts_are_the_live_strategys.py`
the link and the counts, `tests/unit/ai/lead/test_verification_verifies_a_study_step.py`
the computed cut, `tests/unit/domain/test_a_text_requirement_is_met_only_by_the_records.py`
the text rows, `tests/unit/services/strategies/test_a_text_query_is_a_free_text_value.py`
the text queries, `tests/unit/domain/test_a_question_is_no_requirement.py` the asks,
`tests/unit/domain/strategy/test_constraint_grounding.py` the fold-change grounding,
`tests/unit/ai/lead/test_verify_reviews_the_request.py` the success rule, the
caveat and the read cap, and `tests/unit/ai/lead/test_the_reply_reports_the_review.py`
the gap the facts part shows. A real plasmodb turn with two requirements shows the rows, the
genes and whether the checker chose to search.
