---
type: Findings
title: Pre-UAT findings
description: Defects measured while writing the UAT flows, each in the six-heading bug format with the values of the run that showed it; engineers fix these before UAT starts.
tags: [uat, findings, bugs]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Pre-UAT findings

Measured on 2026-09-24, VEuPathDB build 71, with `pathfinder.devtools.chat` on the host (model `openai:gpt-5.6-luna` for every role, at the tier's `medium` effort; the debugger's `--effort` flag now sets every role's effort and `turn_settings.json` records it) and raw WDK reads under the dev login. Run directories are under `apps/api/.pf-runs/uat/` (gitignored); the pass-2 re-checks of 2026-09-25 ran every role at `high` effort and are under `apps/api/.pf-runs/p2/`. Each finding names the flow that catches it at UAT.

| Id | Severity | Title | Flow |
|---|---|---|---|
| FND-1 | blocker | "Carry these to their orthologs" builds syntenic orthologs only | X3 |
| FND-2 | blocker | A control test's evidence card shows the last partial test, not the full one | V2 |
| FND-3 | blocker | A 500 on one unrelated search definition fails every bind of the pass | N1, X5 |
| FND-4 | major | A cross-organism INTERSECT is written to VEuPathDB before it is refused | N3 |
| FND-5 | major | The trace counts genes as transcripts | S1 |
| FND-6 | major | "0 of 8 sampled genes fit" beside `Supported` when every gene is `Unclear` | E2, X3 |
| FND-7 | blocker | "Delete the intersection step" deletes another step, the card does not say which, and the reply says the intersection is gone | N5 |
| FND-8 | blocker | The parameter sweep never runs | V3 |
| FND-9 | blocker | The orthology transform is missing from the transform list, so fungidb says it has none | X4 |
| FND-10 | major | A search the pass hits three rationale refusals on stops the build with one search bound | S2 |
| FND-11 | major | On plasmodb a mosquito question opens a VectorBase study and exports a 0-gene step | X1, E8 |
| FND-12 | major | A portal-only request either offers a site switch the conversation cannot make or gives no route at all | N8, X6 |
| FND-13 | minor | An image with a transparent background is read as black or as off-topic | C13 |
| FND-14 | major | A turn that ends on an offer card writes no reply, so `/analyze` answers with a card and no analysis | C9, N7 |

---

## FND-1 - "Carry these to their orthologs" builds syntenic orthologs only

Fixed in a16: a word the bound search's own name states is not held to a parameter (`_qualifier_words.py::named_stems`); live on toxodb the 78-gene seed carried to Neospora caninum Liverpool binds `isSyntenic` at its default and answers 145 genes.

Pass 2 re-check (2026-09-25, effort `high`, run dirs `p2/fnd1/t1`, `/t2`): the toxodb seed built 78 genes (720, 946); "Carry these to their orthologs in Neospora caninum Liverpool." bound `GenesByOrthologs` with `isSyntenic` at its default and the reply reads "**Transform by Orthology** finds 145 *Neospora caninum* Liverpool ortholog records".

**What I did.** On toxodb, built "Find Toxoplasma gondii ME49 genes with a predicted signal peptide and 2 to 99 transmembrane domains." (78 genes), then sent "Carry these to their orthologs in Neospora caninum Liverpool." Same pair on vectorbase with Anopheles gambiae PEST (343 genes) and "Carry these to their orthologs in Aedes aegypti LVP_AGWG." Neither message says "syntenic". Run dirs `X-tx-S2/t2`, `X-vb-S2/t2`.

**What I got.**

| Site | Transform the app built | App count | WDK, `isSyntenic=no` (the site default) | WDK, `isSyntenic=yes` |
|---|---|---|---|---|
| toxodb | `GenesByOrthologs` `isSyntenic=yes` | 69 | 145 | 69 |
| vectorbase | `GenesByOrthologs` `isSyntenic=yes` | 235 | 850 | 235 |

The vectorbase reply: "finding **235 Aedes records**", "verification succeeded", no mention of synteny. The evidence card: `Supported`, requirement "Carry these to their orthologs" `Met`. The bind that kept the default was refused: "c_aegypti_orthologs states 'orthologs', and Transform by Orthology states it only through Syntenic Orthologs Only? (isSyntenic), which this call leaves at its default or switched off. Set isSyntenic to yes."

**Why that's wrong.** The researcher asked for orthologs and received the syntenic subset: 76 of 145 Neospora orthologs and 615 of 850 Aedes orthologs are missing, and the card calls the count right. On plasmodb the same request kept the default and answered 142, so the answer depends on the words the model wrote.

**Why it happens.** `ai/tools/standalone/_frame_qualifiers.py` reads "orthologs" in the criterion text as a qualifier that only the parameter named "Syntenic Orthologs Only?" states, so it refuses the site default.

**Fix.** A word the bound search's own name already states (the orthology transform states "ortholog") is not a qualifier of one of its parameters; only "syntenic" is.

**What you'd get.** toxodb 145 genes, vectorbase 850 genes, `isSyntenic=no`, unless the message says "syntenic".

---

## FND-2 - A control test's evidence card shows the last partial test, not the full one

Fixed in a16: the card merges every test of one step, and a repeat test of ids already tested on that step is answered from the first result with no new task (rerun: 1 task, card rows 80/52 and 40/2).

Pass 2 re-check (`p2/fnd2/t2`, through the worker): one `Run control tests` task, a second call answered from the first result, card rows `Positive` 80 / 52 (0.65) and `Negative` 40 / 2 (0.05); the reply: "the strategy returned **52 of 80** supplied positive controls ... returned **2** that were expected to be excluded: `PF3D7_0508800` and `PF3D7_1215900`". The same reply called the 479 genes "479 Plasmodium falciparum 3D7 transcripts": the unit rule missed a count with a strain name ("3D7") before the noun; `reply_claims.counts_named_as` now reads a word that holds a letter.

**What I did.** On plasmodb, in the conversation holding the one-step strategy `GenesWithSignalPeptide` (479 genes), sent "Test this strategy against my controls. Positive controls (should be returned): <the 80 positives of the seed `PF3D7 Signal Peptide Genes`>. Negative controls (should not be returned): <its 40 negatives>." through the worker. Run dir `S1-one-step/t2`.

**What I got.** 52 `run_control_tests_on_step` calls in one turn: the full 80+40 twice, then subsets (23 calls of 10 positives, 16 of 5, 4 of 20, 3 of 8 negatives, 2 of 40 negatives, one of 16 negatives, one of 9 positives). 52 task rows and 52 `Control tests` tables in the thread, 521 s of wall time. The reply is right: "52 of 80 were returned (65% recall)", "`PF3D7_0508800` and `PF3D7_1215900` were returned". The evidence card holds one control row: `Negative`, 16 controls, 1 returned (`PF3D7_1215900`), rate 0.06, and no `Positive` row.

**Why that's wrong.** The card is the record a researcher cites, and it says 1 of 16 negatives and nothing about positives, beside a reply that says 52 of 80 and 2 of 40. Raw WDK agrees with the reply: the SignalP-6.0 step's 479 gene ids hold 52 of the 80 positives and 2 of the 40 negatives.

**Why it happens.** `ai/lead/evidence_card.py::_controls` keeps the latest control test per step, so the last partial call replaces the full one; nothing stops the check from re-testing subsets of ids it has already tested.

**Fix.** The card keeps the test that covered the turn's whole control set (or merges the tests of one step), and a repeat test of ids already tested on the same step is answered from the first result.

**What you'd get.** One task row; the card's rows `Positive` 80 controls, 52 returned, 28 not returned, 0.65 and `Negative` 40 controls, 2 returned, 38 not returned, 0.05.

---

## FND-3 - A 500 on one unrelated search definition fails every bind of the pass

Fixed in a16: a neighbour the site cannot answer is left out of the comparison and named in the trace ("not compared: ...") and in `SetCriterionResult.unreadSearches`; live on plasmodb the N1 prompt bound its three criteria with the antibody-array search answering 500 and ended on a question card.

Pass 2 re-check (`p2/fnd3/t1`): no `set_criterion` failed on a definition the site could not read; the pass bound `c_blood_expression` (`GenesByRNASeqpfal3D7_Newbold_ebi_rnaSeq_RSRCPercentile`) and `c_no_human_equivalent` (`GenesByOrthologPattern`, 2,812 genes) and ended recording one question: "Which statistic and cutoff should define low variation between Plasmodium falciparum isolates: maximum variant density or maximum allele frequency, and what threshold should I use?" ($0.198).

**What I did.** (a) On plasmodb sent the corpus prompt "Find drug targets that are expressed in the blood stage, do not vary much between isolates, and have no human equivalent." Run dir `N1-ambiguous/t1`. (b) On the portal, after the 116-gene seed, sent "Carry these to their syntenic orthologs in Toxoplasma gondii ME49." Run dir `X-po-S2/t2`.

**What I got.** (a) 14 `set_criterion` calls failed with "Search definition could not be read: reading GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection failed: ... '500 500'", while each call bound another search (`GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile`, `GenesByVariantCharacteristics`, `GenesByOrthologPattern`). 71 tool calls, $0.297, no strategy and no question: the reply ended "The plan is not yet created because the isolate-conservation search requires a quantitative cutoff." (b) 11 of 12 binds of `GenesByOrthologs` failed the same way, on `GenesByRNASeqtgonME49_tgme49_spor_ocyst_rnaseq_ebi_rnaSeq_RSRC`, `GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection` and `GenesByGeneType`; $0.375; the reply: "the site could not read the orthology-transfer search". Raw WDK the same minute (`GET /record-types/transcript/searches/<name>?expandParams=true`, twice each): `GenesByOrthologs` 200 on the portal, the three others 500.

**Why that's wrong.** One search the site breaks makes every other search of the conversation unbindable, and the reply blames the one that works. On the portal `GenesByGeneType` is a ranked neighbour of most requests, so portal flows fail today. The ambiguous request, which must end on a question, ends on a statement.

**Why it happens.** `ai/tools/standalone/_frame_qualifiers.py::_definitions` reads every search the pass ranked in one `asyncio.gather`, and `veupathdb_mcp.catalog.fetch_search_details` raises for the one that answers 500, so the whole `set_criterion` fails.

**Fix.** A neighbouring search whose definition cannot be read is left out of the qualifier comparison, not raised.

**What you'd get.** (a) the pass binds its three criteria and asks its question; (b) the transform binds and the build answers 0 genes (syntenic Plasmodium to Toxoplasma on the portal), or 87 without synteny.

---

## FND-4 - A cross-organism INTERSECT is written to VEuPathDB before it is refused

Fixed in a16: `set_structure` refuses the INTERSECT with `cross_organism_refusal`'s sentence (`first_cross_organism_refusal` over `orthology.stated_steps`); live on plasmodb no step and no strategy were written and the card offered the orthologs of one set in the other organism.

Pass 2: not re-driven live; the unit and integration suites that pin the refusal pass.

**What I did.** On plasmodb sent "Intersect the Plasmodium falciparum 3D7 genes that have a predicted signal peptide with the Plasmodium vivax P01 genes that have a predicted signal peptide." Run dir `N3-crossorg/t1`.

**What I got.** FRAME bound both searches (479 and 593 genes) and the structure `INTERSECT`. The build created three WDK steps, then failed the strategy with "Cannot INTERSECT steps with different organism scopes (Plasmodium falciparum 3D7 vs Plasmodium vivax P01). Gene IDs from different species never match, so this always returns 0 results. Scope every seed to one organism: Plasmodium falciparum 3D7 or Plasmodium vivax P01." That sentence is shown only in the Progress panel's `Building` tab. The thread shows `Strategy updated` with `3 steps, count not available` and an evidence card `Not supported` whose three steps read `-`. The first reply offered the orthology route; the contract refused it (a build nothing verified) and the second reply dropped the offer.

**Why that's wrong.** The researcher sees a strategy that does not exist on the site and loses the one route that answers the question. Three orphan steps stay on the account.

**Why it happens.** `domain/strategy/validate.py::cross_organism_refusal` runs at strategy compilation, after the build minted the steps; `set_structure` does not call it.

**Fix.** `set_structure` refuses the INTERSECT with the same sentence, so nothing reaches WDK, and the reply offers the orthology transform.

**What you'd get.** No `Strategy updated` figure, no steps on the account, a reply that states the refusal and offers the orthologs of one set in the other organism.

---

## FND-5 - The trace counts genes as transcripts

Fixed in a16: `graph_helpers.py::counted_records` counts a transcript answer in genes, and the strategy line says "1 step"; both trace lines read "479 genes" and "3 steps, 116 genes".

Pass 2 re-check (`p2/fnd2/t1`): the trace reads "c_signal_peptide set to GenesWithSignalPeptide, 479 genes, sets Organism" and "1 step, 479 genes".

**What I did.** On plasmodb sent "Find Plasmodium falciparum 3D7 genes whose proteins have a predicted signal peptide." Run dir `S1-one-step/t1`.

**What I got.** Trace rows `Choose a search`: "c_signal_peptide set to GenesWithSignalPeptide, 479 transcripts, sets Organism" and `Read the strategy`: "1 steps, 479 transcripts". Raw WDK for the same search: `estimatedSize` 479, report `meta.displayTotalCount` 479 (genes), `meta.totalCount` 483 (transcripts). The same on every site: vectorbase "2,928 transcripts" for 2,928 genes.

**Why that's wrong.** The number is the gene count and the trace calls it transcripts, beside a reply and a `Strategy updated` figure that say genes. A researcher who reads the trace expects fewer genes than 479.

**Why it happens.** `ai/tools/standalone/graph_helpers.py::count_summary` and `ai/tools/standalone/_frame_count.py::criterion_line` pass the record type (`transcript`) to `count_noun` as the noun.

**Fix.** A transcript record type counts genes, the way `apps/web/src/lib/utils/countNoun.ts` already writes `gene` for it; and `1 step`, not `1 steps`.

**What you'd get.** "479 genes", "1 step, 479 genes".

---

## FND-6 - "0 of 8 sampled genes fit" beside `Supported` when every gene is `Unclear`

Fixed in a16: the line counts each fit word, "8 of 8 sampled genes unclear" when every gene shares one, "5 fit, 3 unclear" when they differ.

Pass 2: not re-driven live; `EvidenceReview.test.tsx` pins the wording.

**What I did.** (a) On plasmodb asked for the DESeq comparison of wild type and DHC mutant in "Heat shock response in sensitive mutants (LRR5, DHC)". Run dir `E-eda/t1`. (b) The vectorbase orthology turn of FND-1 (`X-vb-S2/t2`).

**What I got.** Both cards: verdict `Supported`, every requirement `Met`, eight sampled genes each `Unclear`. `apps/web/src/features/conversation/rail/EvidenceReview.tsx::sampleCountLine` counts only `yes`, so the card and its caption read "0 of 8 sampled genes fit".

**Why that's wrong.** "0 of 8 fit" reads as eight genes that fail the request, next to a verdict that says the strategy is supported. The check could not judge them; it did not judge them wrong.

**Why it happens.** `sampleCountLine` has no wording for `unclear`.

**Fix.** Count each fit word: "8 of 8 sampled genes unclear", or "5 fit, 3 unclear".

**What you'd get.** "0 fit, 8 unclear" beside `Supported`.

---

## FND-7 - "Delete the intersection step" deletes another step, the card does not say which, and the reply says the intersection is gone

Fixed in a16: the card reads "Delete step 'Intersect' (116 genes)?" from the live strategy, a reply that names a step the turn did not delete is corrected, and a No is final for the message.

Pass 2 re-check (`p2/fnd7/t3`, `/t3a`, over the 142-gene P. vivax P01 strategy of `/t2`): the call was `delete_step(step_id="step_fa532a43")`, the card read "Delete step 'Intersect' (116 genes)?" beside the reply "I found the intersection step joining the predicted signal-peptide search with the 2-99 transmembrane-domain search ..."; a No answered "Nothing was removed because the deletion was not approved." Two follow-ons were fixed: a removal a building pass parks (`delete_step`, `replace_subtree`) now carries the same question ("Replace step '<title>' (<search>, <n> genes) and the steps under it?"), and a No on a removal withdraws the requirements its message recorded (the next turn's check had reported "Delete the intersection step" as unmet).

**What I did.** On plasmodb, in the conversation holding `GenesByOrthologs(INTERSECT(GenesWithSignalPeptide, GenesByTransmembraneDomains))` (142 P. vivax P01 genes; run dirs `S2-intersect-r2/t1`, `/t2`), sent "Delete the intersection step but keep both searches exactly as they are." then approved the card. Run dirs `N5-breaktree/t1`, `/t1a`.

**What I got.** The card: "Delete step needs your approval before it runs." with no step named. The call was `delete_step(step_id="c_orthologs_pvivax_p01")`, the orthology transform. After approval the strategy is `INTERSECT(GenesWithSignalPeptide, GenesByTransmembraneDomains)`, 3 steps, 116 genes. The reply: "Removed the intersection step. Both underlying searches were kept exactly as they were: the predicted signal-peptide search retains 479 Plasmodium vivax P01 ortholog records, and the 2-99 transmembrane-domain search retains 840 Plasmodium vivax P01 ortholog records."

**Why that's wrong.** The step the researcher named still stands, the one they kept is gone, and the reply states the opposite and calls 479 and 840 P. falciparum 3D7 genes P. vivax P01 records. The card gave no chance to catch it.

**Why it happens.** `apps/web/src/features/conversation/toolNames.ts` writes the generic "<tool> needs your approval before it runs." for `delete_step`, so the card never shows the `step_id` the call carries; the turn contract checks that the strategy changed, not which step the reply says it removed.

**Fix.** The `delete_step` card names the step by its title and search ("Delete step 'Transform by Orthology' (142 genes)?"), and the reply is checked against the deleted step's title.

**What you'd get.** A card naming "Transform by Orthology"; a No; then the Lead's refusal or question about deleting a combine that has two inputs.

---

## FND-8 - The parameter sweep never runs

Fixed in a16: the Lead calls the sweep itself with the 80 and 40 ids, a call with no control or a parameter label is refused before the card, and the result is a `Scored variants` table with SignalP-4.1 first.

Pass 2 re-check (`p2/fnd2/t3` to `/t5a`, through the worker): the Lead called `optimize_search_parameters` itself; the first call carried 79 of the 80 saved positives (`PF3D7_0207900` dropped in the copy), so the table read SignalP-4.1 75/79 and SignalP-6.0 51/79. The tool now takes the saved set as `control_set_id`, read whole on the worker; rerun: SignalP-4.1 first, 76/80 positives, 1/40 negatives, 572 genes; SignalP-5.0 70/80 and 2/40; SignalP-6.0 52/80 and 2/40; one `Scored variants` part.

**What I did.** (a) On plasmodb, in the conversation of FND-2 (the 80 positive and 40 negative ids were sent the turn before), sent "Optimize the SignalP version of the signal peptide search to recover as many of my positive controls as possible while returning as few of my negative controls as possible." and approved. Run dirs `V3-optimize/t3`, `/t3a`, `/t3b`. (b) In a fresh one-step conversation, sent the same request with both id lists in the message and said yes to the card. Run dirs `V3b-optimize/t2`, `/t2a`. Both through the worker.

**What I got.** (a) The card `Optimize parameters needs your approval before it runs.`; the call carried `{"budget": 30, "parameters": ["signalp_version"], "wdk_step_id": 440606243}` and no controls; the task failed at once: "At least one of positive_controls or negative_controls must be provided." The Lead then offered a proposal card; its yes ran a FRAME edit, `read_gene_ids_from_gene_set` failed with "Gene set not found" on the control set's id, and the reply asked the researcher to paste the ids again. (b) A proposal card ("Run a control-based sweep of the SignalP version setting ...?"); its yes ran a FRAME edit that changed nothing, and the reply offered the sweep again. No `optimize_search_parameters` task ran in six turns.

**Why that's wrong.** The researcher cannot get the sweep. The answer exists: on the site SignalP-4.1 returns 76 of 80 positives and 1 of 40 negatives in 572 genes, against 52 of 80 and 2 of 40 for the SignalP-6.0 step they hold (measured the same day by reading each step's gene ids).

**Why it happens.** A yes on `propose_changes` runs `edit_strategy` from the card's changes (`decisions/an-offer-is-a-card-not-prose.md`), which has no path to a durable tool, and the Lead's direct call does not carry the control ids the conversation holds.

**Fix.** A sweep offer calls `optimize_search_parameters` itself (its own approval is the card), with the ids from the message or from the control set the thread saved.

**What you'd get.** One approval card, one task row `Optimize parameters`, a `Scored variants` table ranking SignalP-4.1 first.

---

## FND-9 - The orthology transform is missing from the transform list, so fungidb says it has none

**What I did.** On fungidb, after the 64-gene seed (run dir `X-fu-S2b/t2`), sent "Carry these to their orthologs in Aspergillus nidulans FGSC A4." Run dir `X-fu-S2b/t3`.

**What I got.** `list_transforms` answered two searches, `TranscriptsFromGenes` and `GenesBySpanLogic`; three `search_for_searches` calls (10, 20, 30 results) returned A. nidulans RNA-Seq searches and no `GenesByOrthologs`. The turn ended on a question card: "The site does not provide a direct step that carries the current genes to Aspergillus nidulans FGSC A4 ortholog records. Should I use the nearest available ortholog-pattern search as the transfer step?" Raw WDK: fungidb lists `GenesByOrthologs` (`allowedPrimaryInputRecordClassNames: ["transcript"]`, full name `InternalQuestions.GenesByOrthologs`), and it answers 257 genes for this seed. `list_transforms` gave the same two searches on plasmodb, toxodb and vectorbase.

**Why that's wrong.** The card tells the researcher something false about the site, and a core flow cannot complete on fungidb. On the other sites the transform is found only when a text ranking happens to return it.

**Why it happens.** `veupathdb_mcp/catalog/searches.py::list_transforms` skips every search whose full name starts with `InternalQuestions.`, and WDK files `GenesByOrthologs`, `GenesByWeightFilter`, `GenesByPathwaysTransform` and `GenesByCompoundsTransform` there.

**Fix.** Keep the input-step searches of `InternalQuestions` (leave out only the boolean question).

**What you'd get.** `list_transforms` lists `GenesByOrthologs`; the fungidb transform binds; 257 genes.

Fixed in a16: `list_transforms` keeps the input-step searches of `InternalQuestions` (veupathdb-mcp v0.2.0a28). Pass 2 re-check (`p2/fnd9/t1`, `/t2`): the Af293 seed built 64 genes (748, 1,341); "Carry these to their orthologs in Aspergillus nidulans FGSC A4." called `list_transforms`, bound `GenesByOrthologs`, and the reply reads "**Result:** **257 records in Aspergillus nidulans FGSC A4**".

---

## FND-10 - A search the pass hits three rationale refusals on stops the build with one search bound

Fixed in a16: a `TOOL_RETRIES` stop that bound part of the plan is continued once like a budget stop, its work order quotes the refusal, and the reason refusal names the term and the 160-character cap in one sentence; the S2 seed bound in one turn on plasmodb (116), toxodb (78) and the portal (116).

Pass 2: the five S2 seeds of the re-checks each built in one turn (toxodb 78, fungidb 64, plasmodb 116).

**What I did.** Sent the S2 seed prompt ("Find <organism> genes with a predicted signal peptide and 2 to 99 transmembrane domains.") in ten conversations: plasmodb five times, one each on vectorbase, toxodb and the portal, twice on fungidb. Run dirs `S2-intersect*/t1`, `X-*-S2*/t1`.

**What I got.** Every run had 2 to 4 `set_criterion` refusals ("the reason does not hold the term Minimum Number of Transmembrane Domains", "String should have at most 160 characters"). In 2 of the 9 runs FND-3 did not stop (plasmodb `S2-intersect/t1`, fungidb `X-fu-S2b/t1`), the transmembrane criterion was refused three times in a row, the fourth call was cut off, and the reply was "I could not complete the search: ... the 2-99 transmembrane-domain criterion was not [bound] ... Would you like me to continue and finish the transmembrane-domain filter?" A "yes" built it (116 genes, 130 s, $0.090; fungidb 64 genes, $0.102).

**Why that's wrong.** The simplest two-search request costs the researcher a second turn in about one run in five, and the reply sounds like a failure of the site.

**Why it happens.** The FRAME toolset gives `set_criterion` `max_retries=3` (`ai/tools/toolsets/frame.py`); the rationale rules refuse most first attempts, and three refusals in a row raise pydantic-ai's "exceeded max retries", which `ai/lead/sub_agent_stream.py` records as a `TOOL_RETRIES` stop that nothing continues.

**Fix.** A `TOOL_RETRIES` stop that bound part of the plan is continued once by the dispatch, as a budget stop is (`decisions/a-budget-stop-is-retried-by-the-system.md`), and the reason rules name the fix in one retry (the term to include and the 160-character cap together).

**What you'd get.** 116 genes in one turn.

---

## FND-11 - On plasmodb a mosquito question opens a VectorBase study and exports a 0-gene step

**What I did.** On plasmodb sent "Which genes are upregulated in female mosquitoes after a blood meal?", then "Run that comparison now and make a strategy step from the genes that are higher in the blood-fed samples." through the worker. Run dirs `X1-bloodmeal-pl/t1`, `/t2`. The same first message on vectorbase: `X1-bloodmeal-vb/t1`.

**What I got.** On plasmodb the assistant searched EDA studies, opened "Antennal expression following a blood meal" (`DS_89c1f6f48a`, sites `["portal"]`), later "Antennae from females non-blood fed ..." (`DS_bdc44768c5`), ran DESeq ("136 of 12852 genes pass"), and exported a step on plasmodb: `GenesByEdaVizWithCompute`, 0 genes. The reply: "It returned **0 genes** ... recovery requires changing the comparison dataset/control or relaxing the thresholds." On vectorbase the same question bound the site's own `GenesByMicroarrayDirectagamPEST_microarrayExpression_E-MTAB-1621_Bloodfed_vs_Sugarfed_RSRC` and answered 6 genes, which WDK confirms (up-regulated, 2-fold, protein coding: 6).

**Why that's wrong.** The genes of a mosquito study are not PlasmoDB genes, so the step is empty by construction, and the reply sends the researcher to relax thresholds instead of to VectorBase.

**Why it happens.** `search_eda_studies` ranks the study catalog every site shares (747 studies, `sites: ["portal"]` for these), and nothing stops the Lead from opening a study the current site does not publish.

**Fix.** On a component site, a study whose `sites` do not include that site is refused at open with a sentence naming the site that publishes it (the EDA twin of `decisions/another-site-informs-and-never-binds.md`).

**What you'd get.** "This study is on VectorBase; its genes are not PlasmoDB genes. Ask on VectorBase", and no step.

**Fixed in a16.** Run dirs `X1-bloodmeal-pl-a16/t1`, `/t2` (effort `high`): every study listed carries "This study is on the VEuPathDB Portal; its genes are not PlasmoDB genes. Ask on the VEuPathDB Portal." (the five matches, `DS_89c1f6f48a` among them, read `sites: ["portal"]`, so the sentence names the portal and not VectorBase), the t2 reply ends on that sentence, no analysis opens and no step is built; the bind refuses such a study with 422 (`decisions/a-study-another-site-publishes-is-not-opened-here.md`).

Pass 2: `services/eda/thread_surgery.py` applies the same refusal when a revert or a branch reopens an analysis (`test_surgery_opens_no_study_another_site_publishes.py`).

---

## FND-12 - A portal-only request either offers a site switch the conversation cannot make or gives no route at all

Fixed in a16: the organism refusal records the portal sentence on the pass, a pass that changed nothing answers with it alone, and FRAME and the Lead ask no switch question; live on plasmodb the reply is the sentence with the `/veupathdb/conversation` link.

Pass 2: not re-driven live; the unit suites that pin the sentence pass.

**What I did.** On plasmodb, in the 116-gene seed conversation, sent "Carry these to their orthologs in Toxoplasma gondii ME49.", then answered the question card with its recommended option. Run dirs `N8-portalonly/t3`, `/t3r`.

**What I got.** The card "Should this strategy switch to the VEuPathDB Portal so the existing Plasmodium falciparum 3D7 result set can be mapped to Toxoplasma gondii ME49 orthologs?", options "Yes - use the Portal orthology search" (recommended) and "No - keep the current site". After "Yes": FRAME tried the plasmodb transform again (organism refused), and the reply: "The Portal switch is already the confirmed choice; please confirm it once more in the exact form below so the mapping can be bound to the strategy." Nothing is below, and nothing changed.

On vectorbase, after the 343-gene seed, "Carry these to their orthologs in Plasmodium falciparum 3D7." (run dir `X6-vb-pf/t2`): FRAME read "Transform by Orthology on vectorbase reaches Arthropoda and Mollusca; a transform to Plasmodium falciparum 3D7 runs on the VEuPathDB portal, where one strategy holds both organisms. Plasmodium falciparum 3D7 is on plasmodb.", asked nothing, and the reply said only "I could not add the ortholog step because the current VectorBase search cannot target *Plasmodium falciparum* 3D7."

**Why that's wrong.** On plasmodb the card offers a switch the conversation cannot make (a conversation is bound to its site), then asks the researcher to confirm again: a loop with no way out. On vectorbase the researcher is not told that the portal answers the question.

**Why it happens.** The organism refusal in FRAME says "Switching sites is the researcher's decision: set disposition="needs_user" and ask", and no tool acts on the answer.

**Fix.** The card says what the researcher does: "Open a new conversation on the VEuPathDB Portal and ask there; this conversation stays on PlasmoDB", with a link to the portal's new conversation.

**What you'd get.** A link to `/veupathdb/conversation` and no loop.

---

## FND-13 - An image with a transparent background is read as black or as off-topic

**What I did.** On plasmodb attached a PNG of a three-row gene table (black text, transparent background, 612 x 792) and sent "Which genes are in this image?" three times. Then the same table rendered on an opaque white page, twice. Run dirs `C-png/t1`, `C-png-r2/t1`, `C-png-r3/t1`, `C-png-r4/t1`, `C-png-r5/t1`.

**What I got.** Transparent: two runs classified `off_topic` ("PathFinder builds, edits, and checks search strategies ... Please put your question in those terms"), one "it appears completely black, with no visible text". Opaque: 2 of 2 listed PF3D7_0709000, PF3D7_1133400, PF3D7_0102600.

**Why that's wrong.** A figure exported from a plotting tool often has a transparent background; the researcher is told the question is off-topic.

**Why it happens.** The composer sends the PNG as is (`runtime/chatAttachmentAdapter.ts`) and the model reads transparent pixels as black.

**Fix.** Flatten an image with an alpha channel onto white before it is attached.

**What you'd get.** The three genes, as with the opaque file.

**Fixed in a16.** `chatAttachmentAdapter.ts` draws an image with a transparent pixel on white and attaches the PNG; a transparent 2x2 PNG attaches with every alpha 255 and white where it was clear (`chatAttachmentAdapter.test.ts`); the same canvas steps in Chromium give the same four pixels; not re-driven through the composer, since the debugger's `--attach` sends the file as is.

Pass 2: not re-driven live; `chatAttachmentAdapter.test.ts` passes.

---

## FND-14 - A turn that ends on an offer card writes no reply, so `/analyze` answers with a card and no analysis

Fixed in a16: every card call carries the reply as a required `reply` argument, which streams as text before the card (rerun: the sweep result sentence, then the adopt card).

Pass 2 re-check: the delete card (`p2/fnd7/t3`) and the sweep card (`p2/fnd2/t3`, `/t5`) each streamed their reply before the card.

**What I did.** On plasmodb, in the 116-gene seed conversation, sent the `/analyze` prompt ("Analyze my current strategy. Summarize topology and step flow, any weak spots or redundant steps, concrete improvement suggestions, and what I should try next."). Run dir `C9-analyze/t4`. Also the offers of N7 and N12 (`N7-proposal/t2`, `N12-context/t1`).

**What I got.** No `text-delta` chunk in any of the three turns: the thread shows the trace and one proposal card ("Would you like to refine the strategy toward a smaller, higher-confidence membrane-protein candidate set?" with three changes), and no reply.

**Why that's wrong.** The researcher asked for an analysis and gets a yes-or-no question; the topology, the weak spots and the reasons are never written.

**Why it happens.** The Lead ends the turn on the deferred `propose_changes` call, and a run that stops on a deferred call emits no `LeadResponse.prose`, so the text the decision asks for beside the card (`decisions/an-offer-is-a-card-not-prose.md`) never streams.

**Fix.** The turn writes its prose before it parks on the card (the prose rides the deferred call, or is emitted before it).

**What you'd get.** The analysis as text, then the card.

---

## FND-15 - A rating sent while offline shows the browser's error, not the product's sentence

Fixed in a17: a network failure answers the caller's sentence (`lib/api/errors.ts::toUserMessage` returns the fallback for a `TypeError`, which is what `fetch` rejects with and whose message is the browser's).

**What I did.** R6 step 3 from the Playwright suite on the mock stack: a built S2 thread on plasmodb, the browser set offline through the Playwright context, then `Good response` clicked on the reply.

**What I got.** The toast read `Failed to fetch`. The flow table expects `The rating was not saved.`

**Why that's wrong.** The researcher reads a browser message in the product's voice and cannot tell whether the rating reached the server; the same wording differs by browser (`Load failed` on Safari).

**Why it happens.** `toUserMessage` forwards the message of every `Error`, and a failed `fetch` rejects with a `TypeError` whose message is the browser's.

**Fix.** A `TypeError` answers the caller's fallback sentence.

**What you'd get.** Toast `The rating was not saved.` on every browser; the same for every other caller that passes its own sentence.

---

## FND-16 - "Reset all local settings" leaves the model preset in place

Fixed in a17: the reset removes the key the store persists under.

**What I did.** A1 from the suite: opened the Model tab (`Balanced` pressed), picked `Fast`, ran `Reset all local settings`.

**What I got.** The page reloaded with `Fast` still pressed.

**Why that's wrong.** The reset's own prompt says it clears the model preferences, and it does not.

**Why it happens.** `state/useSettingsStore.ts::resetAllPersistedSettings` removes `pathfinder-settings`, and the store is saved under the dated key `state/middleware.ts` builds (`pathfinder-settings-20260625`).

**Fix.** The reset calls each persisted store's own `persist.clearStorage()`, so the key it writes is the key it clears.

**What you'd get.** `Balanced` pressed after the reload.

---

## FND-17 - The file chooser keeps the previous model's file types

Fixed in a17: the attachment adapter follows the current model.

**What I did.** C15 from the suite: switched the message-reading model to GPT-5.6 Luna. The Attach button then read `Attach a gene-ID list, an image or a PDF`.

**What I got.** The chooser's accepted types were still `.csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain`. After a reload they include images and PDFs.

**Why that's wrong.** A researcher who has just picked an image-reading model cannot select an image until they reload.

**Why it happens.** The attachment adapter is rebuilt on every render, but assistant-ui's composer notifies its listeners only when cancel, send-disabled or the queue changes, never when the adapter changes, so `ComposerPrimitive.AddAttachment` reads a stale accepted-types list from the composer snapshot (the same gap is in the latest published assistant-ui).

**Fix.** `AttachButton` owns its own file input whose `accept` is the same value its label reads, and hands the chosen file to the composer, which still checks the live adapter.

**What you'd get.** Images and PDFs offered right after the switch.

---

## FND-18 - A saved strategy lists no count

Fixed in a17: saving carries the root's count.

**What I did.** S7 from the suite on plasmodb and vectorbase: saved a built 3-step strategy (root 116 genes on plasmodb, 343 on vectorbase) as a reusable strategy and opened Saved strategies.

**What I got.** The row reads `3 steps` only. The database row has `estimated_size` NULL while its stored step counts give the root 116 (343 on vectorbase).

**Why that's wrong.** The flow expects `3 steps - 116 genes`; a saved strategy with no count cannot be compared with another at a glance.

**Why it happens.** `services/strategies/wdk_sync.py::upsert_chat` stores the strategy AST with its step counts and never writes `estimated_size`.

**Fix.** The save sets `estimated_size` from the stored root count.

**What you'd get.** `3 steps - 116 genes` (343 on vectorbase).

---

## FND-19 - The EDA gene-id list is cut at 4,000

Fixed in a17: the id list carries every retained gene; only the plot's points are capped.

**What I did.** E2, E3 and E4 from the suite on vectorbase: a comparison that keeps 4,402 genes.

**What I got.** The list under the plot reads `Gene ids (4,000)` and `Copy gene ids` copies 4,000.

**Why that's wrong.** 402 retained genes are silently missing from the copied list, an export.

**Why it happens.** `ai/tools/standalone/eda_stream_parts.py` caps the points sent to the thread at 4,000 for the plot, and the id list reads the capped points.

**Fix.** The part carries the full retained id list beside the capped points, and the list reads it.

**What you'd get.** `Gene ids (4,402)`.

---

## FND-20 - Rating a reply while offline shows no message

Fixed in a17: the rating mutation runs regardless of the browser's online state, so it fails at once and the toast shows.

**What I did.** R6 step 3 from the suite: the browser set offline, then `Good response` clicked on the reply (after FND-15's fix to the error mapping).

**What I got.** Nothing appears; the notifications area is empty.

**Why that's wrong.** The flow expects `The rating was not saved.`; the researcher gets no sign the rating was lost.

**Why it happens.** The rating mutation in `RateMessageActions.tsx` uses TanStack Query's default network mode, which pauses a mutation while offline instead of failing it, so its error handler never runs.

**Fix.** `networkMode: "always"` on that mutation.

**What you'd get.** The toast `The rating was not saved.`.

---

## FND-21 - Another user's conversation address shows a spinner forever

Fixed in a17: a 403 on the conversation read is treated as no conversation, and the view redirects to the conversation list.

**What I did.** F12 from the suite: a second dev-login user opened another user's `/plasmodb/conversation/<id>`.

**What I got.** The page stays on that address with the view's spinner. The api answered 403 `FORBIDDEN` for the conversation (the ownership helper `services/conversations/authz.py::get_owned_thread` raises `ForbiddenError` for another user's thread, as the tenancy decision requires).

**Why that's wrong.** A researcher who follows a colleague's link waits on a spinner with no way out and no message.

**Why it happens.** `lib/api/strategy.ts::fetchStrategy` turned only a 404 into "no conversation"; a 403 left the read in an error state, `ChatView` redirects only when the data is null, and the transcript read never starts.

**Fix.** A 403 on the read is "not the caller's conversation" and answers null like a 404.

**What you'd get.** A redirect to `/plasmodb/conversation`.

---

## FND-22 - The rail shows no strategy after an EDA export lands during a slow conversation read

Fixed in a17: the strategy write cancels the conversation read in flight before it stores, so an older read cannot overwrite it.

**What I did.** The EDA export-step spec on the mock stack, repeated three times with two Playwright workers; then once with the conversation read held until the export answered.

**What I got.** The tab read `This step is now the strategy's first step.` while the thread's rail read `No strategy built yet` and the strategy panel was absent after 20 s. In the passing trace the conversation read took 278 ms and the export landed 417 ms after that read started; under load the read is the slower of the two, and two of three parallel repeats failed.

**Why that's wrong.** The researcher is told the step began the strategy and the rail says there is none, until a reload: the read is never stale (`staleTime: Infinity`).

**Why it happens.** `lib/api/strategy.ts::writeStrategy` stores the exported strategy with `setQueryData` while the conversation read started at page open is still in flight; that read answers with the older strategy, which has no step, and replaces the written one.

**Fix.** `writeStrategy` cancels the conversation read before it writes; every caller (the export, operations, step-count refreshes, the slash commands) is covered.

**What you'd get.** The rail lists the exported step at once; the spec now holds the first read until the export answers, so it exercises the race every time.

---

## FND-23 - A recalled memory from a conversation older than a16 shows `Invalid Date`

Fixed in a17: a recalled-memory part whose data does not match the current wire is shown as a stale part, never as a date.

**What I did.** Opened a conversation whose first turn ran under a15 and read its `Recalled memories` figure.

**What I got.** Some rows read `Invalid Date` under the memory's name; rows in conversations started under a16 read a date.

**Why that's wrong.** The researcher reads a browser error where the memory's date belongs, and cannot tell which memories the turn actually used.

**Why it happens.** `createdAt` joined the recalled-memory payload in the a16 release, so every `data-memory-retrieved` event logged before it carries none; the renderer (`content/parts/DataMemoryRetrieved.tsx`) does not validate the part against its schema and hands `undefined` to `new Date`.

**Fix.** The part is validated against its generated schema before it renders; a part that does not match is shown as a stale part.

**What you'd get.** Conversations from a16 on show the date; older ones show the stale-part notice on that figure.

