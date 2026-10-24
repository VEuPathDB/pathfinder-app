---
type: Decision
title: An audit plan is composed from the site's genomes and priced from measured unit costs
description: The planner reads three site answers (the organism list, the organism report and the BUSCO priorities), resolves each named genome, picks the species reference, keeps the audited genomes the genome cap allows by served BUSCO gap, orders the comparison genomes, refuses the intron and Sec targets the site cannot judge without uploading a dataset, admits the scope under AUDIT_MAX_GENOMES and prices it from per-unit means measured on QA. A single bound per run, prices from the library's ceilings and a Sec pre-filter through an id-list upload were rejected.
tags: [audit, planning, estimate, cost, genome-cap]
generated: { by: claude-code/opus-5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

**The rules are pure, the reads are a service.** `domain/audit/planning.py`
holds every rule and imports no library: the genome budget, the audited genomes
by gap, the species reference, the comparison order, the screened checks, the
estimate, the start card and the scope comparison a start uses.
`services/audit/planning.py` makes the reads and composes them in
`propose_scope`.

**The genome cap counts every whole-genome read.** The budget for audited
genomes is `AUDIT_MAX_GENOMES` less the reference genome and each target genome
that is not also named. Named genomes that fit keep their order; otherwise the
largest served BUSCO gaps are kept and the rest are reported as left out. A
named genome that a target reads whole is always audited, and the cut falls on
the others. Gene targets that read more whole genomes than the cap are refused
with that count. When the reference would take the slot of a named genome, the
pseudogene screen is not proposed and the proposal says why. When the requested
checks leave no check for the named genomes, they are left out with that reason
and the targets are kept; with no target left, the plan is refused with the
reason. A plan whose every target is refused says so. Two targets that
place to one key are checked once, and a request over the confirm limit or the
target count is refused in words. The
scope is admitted with `AuditScope.admitted` at the same cap that `begin_run`
uses, and an admission error is the proposal's refusal, never an exception.

**The reference is the one marked strain of the audited species.** No
reference is chosen when the named genomes span species, include the marked
strain, or when the species has no marked strain or more than one. The proposal
states the reason, and the pseudogene screen is then not proposed.

**A target the site cannot judge is refused before the card.** An intron target
needs an RNA-seq junction track for its genome (two reads: the gene's organism
and the track list). A Sec target needs a reference protein that holds a `U`,
read through the record reads of `record_proteins`. A reference that serves no
protein keeps its target, and the check judges it in the run. Planning never
uploads a dataset, because WDK cannot delete one from the researcher's account.
A target whose read fails is refused on its own, with the service's error in
the log: "<site name> did not answer the read of <gene>" for a transport or
server failure, and "<site name> could not read <gene>" otherwise; the site-wide reads
still fail the plan. A name that resolves to no organism, or to several, gets up
to five suggestions that hold all of its words.

**The estimate is a sum of measured unit costs.** `MEASURED_COSTS` holds the
per-unit means of one cost run (QA plasmodb and toxodb, build 71, 2026-10-23),
with request and store-read counts rounded up. A run reads its build once and,
one gene record read for each distinct gene of the targets that enter the run's
gene list (`LIBRARY_READS_PER_LISTED_GENE`, the library's stated cost and not
part of `MEASURED_COSTS`); a run leaves no dataset in the account, and
a scope whose only targets are missing-gene or organelle targets lists no gene.
Each screened check costs `confirm_limit` findings per audited genome, so the
request count is an upper bound. A check's measured confirm cost already holds the gene
model reads it makes beside its own reads (one for a strain or selenoprotein
check, two for a fusion check), because the cost run took a release that makes
them, so the estimate adds no separate charge for them. `model_reviews` is the review cap plus the
agreement sample.

# Rejected

- **One bound for every run.** It hides what a larger scope costs, and the card
  must let the researcher compare scopes.
- **Prices from the library's read ceilings.** The intron ceiling is several
  times the measured reads, so every estimate with an intron target would
  overstate the cost by the same factor.
- **A separate charge for the gene model reads.** The measured confirm cost
  already counts them, so a second charge prices each strain, fusion and
  selenoprotein finding above the requests it sends.
- **A Sec pre-filter through an id-list upload.** It would leave a dataset in
  the researcher's account for every plan, and no plan may write.
