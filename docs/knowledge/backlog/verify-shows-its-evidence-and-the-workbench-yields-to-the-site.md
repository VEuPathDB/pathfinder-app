---
type: Backlog
---

# VERIFY shows its evidence, and the workbench yields to the site

Release a15. The workbench duplicates what VEuPathDB already offers (GO, pathway
and word enrichment are WDK step analyses; set operations are combine steps) and
keeps what the site lacks (control sets, control tests, parameter optimization,
comparisons) in a tab of its own. Meanwhile VERIFY's verdict is a sentence, and
an AI skeptic cannot check it.

## What

Remove from the workbench everything WDK offers on the site itself; keep custom
and statistical enrichment only where the site has none. Fold what remains into
VERIFY as evidence: for every verified strategy, one evidence card that names
the positive controls recovered and the negative controls excluded (with gene
ids), each step's count against the site's count at the time of the check, the
citations behind each criterion from the research tool, and the WDK strategy
link. The card is a data part the thread renders under the verification digest
and the rail's Verification tab, and the eval extract records it.

## Constraints

Nothing on the card is generated: every value is read from a tool result or the
ledger, and a claim the ledger cannot back fails the turn contract like an
unrecorded question does. Removing a workbench feature deletes its plumbing
(routes, hooks, stores, tests) in the same change. Regression tests: the card's
values equal the tool results that produced them; a removed feature's route
answers 404; the rail renders the card from a snapshot.
