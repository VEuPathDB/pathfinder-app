---
type: Decision
title: An audit run is stored unit by unit and resumes where it stopped
description: A run row holds the approved scope, a sampling seed, its four stages with their progress and its deadline; every collected genome, finding and piece of evidence is its own row with its own status, attempts and stops. A site that does not answer is waited for until the deadline, any other failure settles its unit failed, a unit the worker stops on three times is failed, and a unit the deadline left untried is unread. Holding the run in memory and writing it at the end, a fixed number of tries per unit, and marking an untried unit unreached with a reason were rejected.
tags: [audit, persistence, resume, jobs]
generated: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

**One row per unit.** `audit_runs` holds the scope the researcher approved, a
seed, the four stages (collect, screen, confirm, tie-break) with each stage's
request count and progress, the release the site reported and the deadline the
run waits for a site until (`AUDIT_RUN_HOURS`, 6 by default, counted from each
start). `audit_genomes`, `audit_findings` and `audit_evidence` hold one row per
unit, each with a status, its attempts and the times a worker stopped on it.
A resumed run starts from the first unfinished stage and reads only the open
units of that stage.

**How a unit settles.** A unit is `trying` while it is read. A site that does
not answer settles it `unreached`. `services/site_errors.py::unreached` is the rule:
a transport error, a timeout, a broken connection, or a status of 500 or more (a
JBrowse store by its upstream status). An error with the data parsing code, such as
a malformed table or track file, is an answer the site gave, so it is `failed` at
any status. The stage reads an `unreached` unit again after a pause that doubles
from 30 seconds to 15 minutes, until the deadline; the other units go on
meanwhile. Any other failure settles it `failed` with the site's message. A
unit still `trying` when a stage starts was being read when a worker stopped:
it reopens, and the third time it is `failed`. A run that does not halt
therefore always finishes and lists its failed, unreached and unread units; a
run halted for its sign-in or by a job that raised waits for a new start.

**`unread` is a status of its own.** A unit the deadline left with no attempt
is `unread`, with the message "not read before the run's deadline" and zero
attempts. A unit that was tried and is still open at the deadline is
`unreached`. It keeps the message stored on it, and gets "not read before the
run's deadline" when it holds none: a retry clears the message of each unit it
reopens, and a unit returned to open by a halt or a stop keeps only a message
stored before that try. The per-status counts and the
run view therefore tell "the site did not answer" from "the run had no time to
ask". Both are open: `start_run(..., retry_unreached=True)` reopens exactly the
unreached and unread units and the stages from the first that holds one.

**A screen that runs again keeps its first sample.** It screens only the
genomes that hold no screened finding yet, so a genome with candidates keeps
its first candidates and sample, and a comparison genome read late does not
judge it again. The exception: a genome screened with no candidate holds no
finding, so a screen that runs again after a retry screens it again against
every comparison genome then collected, and may find candidates the first
screen could not. Pseudogene calls are screened apart, from the stored rows
of the audited genome and of the reference genome: a genome is paired until it
holds a pseudogene-call finding, so a reference genome collected after a retry
pairs a genome whose other checks were screened before it. An audited genome's
BUSCO scores are part of its collection: it settles `collected` only when its
rows are stored and its scores read was answered, a scores read the site does
not answer leaves it `unreached` (or `unread` at the deadline) like a rows
read, and stored scores are never read again. A genome the site serves no
scores for is collected with none. The site serves the scores of every organism
in one report, and the library refuses the whole report when one record is
unreadable; every audited genome of that pass is then collected with none, its
message names the failed read, and a reader shows its gap as unknown, not as
absent.
The confirm stage checks a fixed-size sample per genome and
check, chosen by a hash of the stored seed, so a rebuilt report shows the same
sample.

**The screen and the served check read different groups.** The screen judges
each gene against the rows of its ortholog group in the collected genomes
only, the audited ones and the comparison set; the confirm stage calls the
library check, which reads the site's whole Orthologs table for the gene. A
gene that is short in the collected subset and typical across the site is a
candidate the check does not confirm: it can answer `NOT_CHECKED` or another
verdict that names no error. A verdict that names no error in the model settles
the finding `confirmed` with no error type and no certainty, and the stored
answer keeps the verdict. The pairs of a split are the two adjacent members of
one group in one genome, as the library pairs them.

**Rates, targets and impact.** A finding records two genomes: the screened
genome, whose screen produced it (for a gene target, the genome its first gene
was placed in), and the model genome, where its error lives. The two differ only
when a check moves the error to the reference's model. A strain target also
records the genome of its reference gene, because the check judges both models.

Each screened genome and check has a rate from the library's
`rate_with_bounds`, over the random sample only: the confirmed findings that name
an error over the judged confirmed findings, with its Wilson 95% interval on
that count, and a floor and a ceiling over every candidate, where each finding
that is not confirmed (screened, unsampled, trying, failed, unreached or unread)
counts as unresolved. A finding is an error only of its model genome: a sampled
finding whose error moved to another genome counts as judged clean in the genome
that screened it. A check with no judged finding has no rate. A finding the
check could not judge (its classification states what was not judged: GAP,
NO_SYNTENY, NOT_FOUND, NO_RELATIVES, NOT_JUDGED, ANNOTATED_IN_GENOME, a fusion
check on a gene that is not LONG, an intron check answering NOT_EXPRESSED or
NOT_CHECKED) is stored `judged = false`, is in neither count, and is counted as
`unjudged` beside the rate and in the run's counts.

The intron check (`intron_support`) is a gene target only. Its answer names an
error per verdict: a missing exon (high certainty), a shifted splice site for a
shifted or a replaced intron (medium; the stored answer keeps which), a spurious
intron for a noncanonical or a retained one (medium), and an unsupported intron
for an annotated intron no evidence explains (low).

A researcher's gene targets are not in any rate. The run reports them apart:
each judged target counts as checked in every genome it judged (both genomes of
a strain pair), and its error counts in its model genome only. A target that was
never placed is counted as unplaced.

Every confirmed finding that names an error stores its impact and the weighing
it came from: its certainty weight (high 1.0, medium 0.6, low 0.3) times the
importance of the genes read (1.0 when a gene record the site serves cites a
PubMed article or holds a user comment, else 0.5) times the use of its model
genome (1.0 when the site marks it as its species' reference strain, else 0.5),
rounded to three places. The weighing names each input and where it came from:
`cited`, `uncited` or `not_read` for the genes, and `reference_strain`,
`other_strain`, `unknown` or `model_role` for the genome. The tie-break stage
weighs every named finding when it starts, with `not_read` until its genes are
read, so a read that fails, is not answered or is cut off by the deadline leaves
the 0.5 fallback, never a missing impact. Collect reads the reference-strain mark
from the site's organism report, once per pass, for each audited genome, and
stores it on the genome: a report the site does not answer leaves the genome
`unreached` like a scores read, and a genome the report does not hold is
collected with the mark unknown and the reason in its message. A strain finding
takes its genome use from its model role (the reference model 1.0, the strain
0.5); a genome collect never read is `unknown`.

The genes read are those of the model that holds the error: the strain gene, or
the reference gene for a strain check that blames the reference, and both parts
of a split model. Two checks read a proxy: for `organelle_join` the gene read is
the reference gene the check compared, and for `missing_gene` it is the example
gene in another genome, because the genome in error serves no record of the
gene. The relatives evidence of a length error stores the library's `tie_break`
side, the reference's organism and each relative's length by organism
(`relative_lengths`) with the tier they were drawn from (`relatives_tier`, the library's
`RelativeTier`, as a strain result keeps it), all from the one `relatives_of` read that gives
the median; both are empty when no relatives qualify or the evidence was stored without them. A `truncated_model` finding whose relatives
answer `REFERENCE_LONG` is classed as the strain check classes that side: an
`over_extended_model` of medium certainty in the reference's model genome, whose
gene is then read; the genome the error moved to is also recorded as its paired
genome, so a target report counts the error where it lives. A gene record stored
before the move is set back to pending, and the stage continues at once to read
the moved gene. The gene read of a
length finding waits until its relatives are settled for that reason, and a read
still held back at the deadline is stored `unread`. The findings pages are ordered by impact in SQL,
highest first and unweighed last, on an index in that order.

**A model's judgement is a verdict row.** `audit_verdicts` (alembic
`2026_10_23_0001`) holds one row per judgement a model made about a gene model,
with its origin (`auditor`, `lead`, `verification` or `review`), the site, the
model that wrote it and the thread it was made in. A review names the finding it
judged and the run that holds it, and a finding holds at most one review; a
review takes its owner, application, thread and site from its run. A chat
verdict names no run. A run's review progress and its synthesis are the
`review` and `synthesis` columns of `audit_runs`, empty before a review starts.
Deleting a run deletes its reviews; deleting a thread keeps its verdicts. A
purge of the user's data deletes the user's verdicts of the purged site, or of
every site, and reports them as `auditVerdicts`.

# What was rejected

**The run in memory, written at the end.** One row per run with a result blob
is simpler, and a worker that stops after three hours starts the run again from
collect.

**A fixed number of tries per unit.** A site that is down for an hour would
spend every try in the first minutes and fail units it would answer later. The
run instead waits for a site until one deadline, and a failure that is not an
outage fails the unit at once.

**An untried unit marked `unreached` with a reason.** It reads the same in the
counts as a site that did not answer, so a researcher could not tell an outage
from a deadline spent in the queue without reading each message. A status
value separates them in the tally and the views with no other change.

# Anchor

`apps/api/src/pathfinder/services/audit/units.py`,
`apps/api/src/pathfinder/persistence/repositories/audit.py`,
`apps/api/src/pathfinder/persistence/repositories/audit_findings.py`,
`apps/api/src/pathfinder/persistence/repositories/audit_reviews.py`,
`apps/api/src/pathfinder/domain/audit/screen.py`,
`apps/api/src/pathfinder/domain/audit/findings.py`,
`apps/api/src/pathfinder/domain/audit/confirmations.py`,
`apps/api/src/pathfinder/domain/audit/rates.py`,
`apps/api/src/pathfinder/services/audit/collect.py`,
`apps/api/src/pathfinder/services/audit/tie_break.py`. The jobs that carry the run
are [Audits run on a queue of their own](audits-run-on-a-queue-of-their-own.md);
the sign-in they read with is
[An audit run keeps its owner's sign-in sealed](an-audit-run-keeps-its-owners-sign-in-sealed.md).
