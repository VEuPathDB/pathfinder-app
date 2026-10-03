---
type: Backlog
title: A membership question is answered by a read-only search
description: A question about which of the shown genes a second search also returns is answered from record pages that lack the field, over different genes than the ones shown, so the site's answer is withheld.
tags: [lead, reads, wdk]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A membership question is answered by a read-only search

**What I did.** On tritrypdb, after a turn sampled TcIL3000_0_26385, _50050, _01550, _34210, _12330, _17170, _57830 and _41230 from a GPI-anchor step, asked: "of the genes you sampled from this result, which ones also have a predicted signal peptide?"

**What I got.** `read_step_ids` with `limit: 5` and five `read_gene_record` reads on TcIL3000_0_04900, _26320, _39760, _43280 and _56250, genes the researcher was never shown. Reply: "I cannot identify any sampled genes as signal-peptide positive from the available evidence." Live WDK `GenesWithSignalPeptide` (IL3000, SignalP-6.0, 1,094 genes) holds six of the eight sampled genes, all but TcIL3000_0_26385 and TcIL3000_0_50050.

**Why that's wrong.** The site has the answer and the researcher gets none; the reply also changed which genes "the sampled genes" means.

**Why it happens.** `read_gene_record` shows no signal-peptide attribute, and the Lead has no read-only way to test named ids against another search; `read_step_ids` samples afresh instead of reusing the ids the facts listed as read.

**Fix.** A Lead tool that runs a catalog search read-only over a list of gene ids (a `GenesByLocusTag` or ids-list step INTERSECT the search, as an anonymous report, never a step of the strategy) and answers which ids it holds; the ids default to the records the facts listed as read this thread.

**What you'd get.** "Of the 8 genes sampled, 6 have a predicted signal peptide (SignalP-6.0), and 2 do not: TcIL3000_0_26385 and TcIL3000_0_50050."
