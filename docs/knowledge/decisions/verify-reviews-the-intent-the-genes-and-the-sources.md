---
type: Decision
title: VERIFY reviews the intent, the genes and the sources
description: A check writes one typed row per requirement the researcher stated in any message of the request, reads the records of up to eight sampled genes and judges each, and may search the literature or the web; the code adds the rows the checker cannot omit, keeps only the genes and sources the turn read, refuses a success over an unmet row, and the evidence card shows all three. A model-only "looks right" verdict and a literature search on every turn were rejected.
tags: [verification, evidence, turn-contract, requirements, genes, literature]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
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
- **The genes themselves.** A turn that built or changed the strategy samples the
  root the work order names (`get_sample_records`, at most 8 records) and reads
  each sampled gene with `read_gene_record`. The sample carries the record
  attributes the strategy's searches show by default and few other searches
  do, read from the catalog (`tm_count`, `signalp_60_probability`), and is
  bounded at 20 s. A record's text is plain, its markup stripped. Each read is
  a `SampledGene`:
  `gene_id`, `product`, `organism`, `fits` (yes, no, unclear) and a one-line
  `why` naming the evidence read. VERIFY's repetition guard caps
  `read_gene_record` at `SAMPLED_GENE_LIMIT` (8) calls per run
  (`build_verification_repetition_guard`).

## What VERIFY may do

- `research_literature_search` and `research_web_search` are VERIFY's to call
  when a claim about biology is one the records do not settle, or when a
  requirement's meaning needs a source. Nothing requires them. Each source relied
  on is a `Citation` in `review.sources` with a url, a DOI or a PMID and a why.

## What the code holds, whatever the checker wrote

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
- An `unmet` row refuses a success (`_digest_the_build_supports`), and the genes
  judged "no" are one caveat with the count ("2 of 8 sampled genes do not fit:
  ...").

Before that, the verification agent's output validator refuses once per check a
digest that states a sampled-gene count its sample does not hold, lists a gene
no read returned, cites a source no read returned, or numbers a message the
request lacks.

## What the reply must say

The turn contract's `unreported_requirement` rule refuses once a reply of a turn
that checked the strategy and does not name each unmet or unexpressed row, and
`unbacked_evidence` refuses a sampled-gene count the card's sample does not hold
("all 8 sampled genes fit" when 2 do not).

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

# What would prove this wrong

`tests/unit/ai/lead/test_verify_holds_the_review.py` holds the code rows,
`tests/unit/ai/lead/test_verify_reviews_the_request.py` the success rule, the
caveat and the read cap, and `tests/unit/ai/lead/test_the_reply_reports_the_review.py`
the contract. A real plasmodb turn with two requirements shows the rows, the
genes and whether the checker chose to search.
