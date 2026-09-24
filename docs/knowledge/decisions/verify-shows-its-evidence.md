---
type: Decision
title: VERIFY shows its evidence, and the workbench yields to the site
description: Every finished check emits one evidence card assembled from records (the control tests the turn ran, the build's step counts, one read of the strategy on the site, the references each criterion was bound on), a reply or a digest that states a control result no test holds is refused once, and the workbench tab is removed because the site offers what it duplicated.
tags: [verification, evidence, controls, workbench, wdk-alignment, turn-contract]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

## The card

`run_verification` (`ai/lead/verify_dispatch.py`) emits one `data-evidence-card` part per
finished check, after the digest is recorded and held to the build. A check that parks on a
durable call emits nothing; the resumed check emits the card once. The payload is
`EvidenceCard` (`domain/evidence.py`), assembled by `assemble_evidence_card`
(`ai/lead/evidence_card.py`), which takes no model output:

| Field | Read from |
|---|---|
| `controls[*].positive/negative` (`returned`, `notReturned`, and the counts and rate computed from them) | the control tests this turn ran, recorded on `TurnMarkers.control_tests` (`control_tests_answered` for the durable step test, the tool itself for the inline search test) |
| `controls[*].enrichment` | the one-sided hypergeometric test of positives among the returned controls (`services/enrichment/stats.py`), only when both kinds ran |
| `steps[*].recordedCount` | the ledger's build section (`BuildSection.node_results`) |
| `steps[*].siteCount`, `siteRead` | one `GET /users/{id}/strategies/{id}` (`services/strategies/site_counts.py`); `siteRead` is `read`, `not_answered` or `not_read` (no strategy on the site), and a missing count is `None`, never 0 |
| `strategyUrl` | `SiteInfo.strategy_url(strategy, root step)`, the step page whose Analyze results tab runs GO, pathway and word enrichment |
| `citations` | `Criterion.rationale.sources`, the references FRAME cited when it bound the criterion; a DOI links to doi.org, a PMID to PubMed, anything else that is no web address is text |
| `verdict` | the digest's success and pending checks after `_digest_the_build_supports`, and the ledger's own sentence when it refused a success |

The card of the last check is kept on `StrategyDomainState.last_evidence_card`, so a later
message can restate its results while the strategy holds the revision the check judged
(`StrategyDomainState.card_of_the_strategy`, the same guard the digest has). The card is not in the ledger: the ledger is re-emitted after every sub-agent tool call, and
the card is logged once per check. The thread (`DataEvidenceCard`) and the rail's
Verification tab (`VerificationDetail`) render one body, `EvidenceCardBody`. The eval extract
records the last card on `ExtractedVerification.evidence`, its texts redacted.

## The grounding rule

`ai/lead/evidence_claims.py` reads two kinds of claim from prose: a control count ("7 of 10
positive controls", "0/12 negatives") and a backticked control gene id inside a clause that
says the target returned it or not. A count names controls ("positive controls",
"negatives"), and the clause's verb says which list it is read from; a clause with no verb may
name either. A claim is backed when a control result of this message holds it (a control test,
a scored comparison variant, a sweep setting) or the last check's card does, while the
strategy is the one that check judged. The Lead's reply is held by the `unbacked_evidence` rule of the turn contract; VERIFY's
digest (prose, key findings, caveats) by an output validator on the verification agent, once
per check (`TurnMarkers.refused_digests`, keyed by the dispatch). Each is refused once, with the recorded values in the correction, like an unrecorded question.

## The workbench

Rule: a feature VEuPathDB offers on the step or the strategy is removed with its plumbing;
a feature the site lacks stays and reaches the researcher through VERIFY and the card. See
the removal inventory in the log entry of 2026-09-24.

# What was rejected

**A generated card.** A model that copies "7 of 10" can write "8 of 10"; the contract would
then have to check the card against the tools, which is the assembler written twice.

**Evidence in the reply prose only.** Prose is not in the rail, the snapshot or the eval
extract as a typed value, and a list of thirty gene ids in a paragraph cannot be checked.

**The card inside the ledger chunk.** The ledger is logged after every sub-agent tool call;
the card would be logged many times per turn and the extract would read whichever came last.

**Keeping the workbench tab beside the card.** Two surfaces would state the same control
numbers from two computations, and eight of its panels re-implemented what the site shows.

**A link to the strategy only.** The site's analysis tabs live on a step's result page;
`strategy_url(id, root_step_id)` lands there.

# What would prove this wrong

`tests/live/test_evidence_card_live.py` builds a step on plasmodb, runs a control test of 25
positives and 32 negatives on it and assembles a card: every list, count and link must equal
what the site returned. `tests/unit/ai/lead/test_evidence_claims.py` holds the parser.
