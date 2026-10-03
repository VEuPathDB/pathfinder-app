---
type: TestPlan
title: UAT flows - the dry UAT investigations
description: The multi-turn investigations of the dry UATs, driven turn by turn on the real model, each recorded as one corpus case uat-dry-<tester>-<site>; every row states the outcome the product owes, with the count the site returned.
tags: [uat, flows, corpus, multi-turn, provenance]
generated: { by: claude-code/opus-5.5, at: 2026-09-28T00:00:00Z }
status: draft
---

# The dry UAT investigations (U)

Each flow is one conversation, one message per step, sent in order; a card step
answers the card the previous message raised. The messages are quoted as they were
sent. Counts are genes on build 71, read on 2026-09-28 from the site through the
tool that built the step; the amoebadb trophozoite counts at the chosen definition
were read on the site with the same search. A row states the outcome the product
owes, not every word of the reply. On every flow no reply applies a value the
request did not state unless the reply names it (the model check's
`assumedStated: 0`), every count is in genes, and no reply prints a search's
internal name, a step id or a record id the UI does not show.

The model check of each flow is its corpus case, named in [the index](index.md).

## U1 - A withdrawn cutoff leaves no gap - toxodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `I'm studying Toxoplasma gondii ME49 secreted effectors. Which genes encode proteins with a signal peptide but no transmembrane domain, and are expressed in tachyzoites?` | `Predicted Signal Peptide` (720) AND `Transmembrane Domain Count` 0 to 0 (6,399) = 461, AND the tachyzoite RNA-Seq percentile step (1,644) = 129; the reply names the percentile range the site applied |
| 2 | Same | Send `The 80th percentile cutoff for tachyzoite expression feels too strict; plenty of secreted effectors are moderately expressed. Can you loosen it to the 50th percentile and above and tell me what changes?` | The expression step at 50 to 100 (4,148); root 259 |
| 3 | Same | Send `Thanks. Just to be sure before I go on: how many genes does the signal peptide plus no-transmembrane step return on its own, before the expression filter, and is that number still current after the change?` | 461, current; nothing is rebuilt |
| 4 | Same | Send `Good. Now drop the tachyzoite expression requirement entirely; I'll look at expression myself later. What's the count without it?` | A `delete_step` approval card |
| 5 | Card | Approve | Root 461; the reply states no gap for the 50th-percentile cutoff: the requirement is withdrawn, and the check leaves no row that no search states |
| 6 | Same | Send `Good, 461 it is. Why do you still mention a 50th percentile verification gap when I removed that requirement? Anyway, please save these 461 genes as a gene set named "ME49 signal peptide, no transmembrane domain".` | A gene set of 461 genes under that name; the reply names it |

## U2 - The strategy link is the workspace route - cryptodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Give me Cryptosporidium parvum Iowa II genes that have an ortholog in Toxoplasma gondii but none in Homo sapiens.` | `Orthology Phylogenetic Profile`; when the profile requires every T. gondii strain (15 strains, 484) the reply says so, or a card asks which strain |
| 2 | Same | Send `Which searches did you use for this, and why those? I want to understand exactly what 'has an ortholog in Toxoplasma gondii' means in your search.` | The reply names the searches by display name and the strains the profile requires |
| 3 | Same | Send `That's stricter than I meant. I don't need an ortholog in all 15 Toxoplasma strains, one in the reference strain ME49 is enough. Please change it to: ortholog in T. gondii ME49, none in Homo sapiens, and tell me the new count. Also please use strain names, not codes.` | The profile on `Toxoplasma gondii ME49` only, excluding `Homo sapiens`: 497; the reply of this turn states 497, whole sentences only |
| 4 | Same | Send `I got an error message saying the content was flagged for biological risk and to send the message again. Did my change to ME49-only go through? What is the count now?` | Yes, 497; the reply names `Toxoplasma gondii ME49` |
| 5 | Same | Send `OK, 497. Now narrow it: and that are predicted to be secreted.` | AND `Predicted Signal Peptide` (437) = 68 |
| 6 | Same | Send `Thanks, 68 is a workable list. Can you give me the link to this strategy on CryptoDB so I can open it there?` | A link on the route the site serves, `https://cryptodb.org/cryptodb/app/workspace/strategies/<strategy id>/<root step id>`; never `/app/strategy/<id>` |

## U3 - An exact family phrase states its wildcard count - piroplasmadb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `List Babesia bovis T2Bo genes in the ves multigene family.` | The reply states what the text search found; a list it cannot stand behind is not presented as the family |
| 2 | Same | Send `The ves genes are annotated on the site as "variant erythrocyte surface antigen" (VESA1), not by the word ves. Please search the product names for that instead and tell me how many you get.` | The quoted phrase finds 1 gene; the reply states beside it that the wildcard form finds 146 |
| 3 | Same | Send `One gene can't be right; the ves family in T2Bo has well over a hundred members. Most product names on the site read "variant erythrocyte surface antigen-1" with a hyphen, so the exact phrase probably misses them. Try a wildcard on that phrase instead.` | `variant erythrocyte surface antigen*`: 146 |
| 4 | Same | Send `Great, 146 looks more like it. How many of those VESA1 genes sit on chromosome 1? Keep the full list too, I want both.` | AND `Genomic Location` chromosome 1 (540) = 47; both counts stated |
| 5 | Same | Send `Can you compare the two counts in one sentence I could put in a paper, i.e. what fraction of the VESA1 genes are on chromosome 1?` | 47 of 146 (32.2 %) |

## U4 - A vocabulary value by its label - tritrypdb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Which Trypanosoma brucei TREU927 protein kinases are more highly expressed in the bloodstream form than in the procyclic form?` | The Naguleswaran RNA-Seq fold change step, 2-fold up in the bloodstream forms (1,020), AND `GO Term` GO:0004672 (223) = 40 |
| 2 | Same | Send `You say a 2-fold cutoff. Is that the only threshold on the expression step, or is there also an expression floor? Please raise the fold change to 4-fold and tell me how the count changes.` | 318 at 4-fold, root 4; the floor is named by its label, `10 reads`, never by its term `734.0197714535435` |
| 3 | Same | Send `What does a floor of 734.0197714535435 mean? That number means nothing to me. And what was the expression dataset: who generated it, which samples, and is it the one I should trust for slender versus procyclic?` | The floor is the site's `10 reads`, a value near-zero expression is raised to before the ratio; the dataset answer names its samples and its source |
| 4 | Same | Send `OK, culture-derived is fine for now. Next, keep only the kinases that have a predicted transmembrane domain.` | AND `Transmembrane Domain Count` 1 to 99 (1,776) = 0; the searches are named by display name only |
| 5 | Same | Send `Zero is not useful. Put the fold change back to 2-fold, keep the transmembrane filter, and list the kinases that remain.` | Root 3: Tb927.11.14070, Tb927.2.2720, Tb927.5.3320 |
| 6 | Same | Send `Is RDK1 really a transmembrane kinase? How many transmembrane domains does each of the three have, and where did that prediction come from?` | The per-gene counts the site holds (`tm_count` 3, 2 and 1 in the order above), never "not exposed" |

## U5 - A family count the site holds is a caveat - giardiadb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Find Giardia Assemblage A isolate WB genes annotated as variant-specific surface proteins.` | The exact phrase finds 20; the reply states that the site holds 216 genes under the family's names, `VSP` included |
| 2 | Same | Send `How many of those have a signal peptide?` | AND `Predicted Signal Peptide` (355) |
| 3 | Same | Send `Thanks. Can you explain in one paragraph what each step does, for a colleague who does not use VEuPathDB?` | One paragraph; nothing is rebuilt |
| 4 | Same | Send `Wait, only 20 VSPs? The WB genome is supposed to have well over a hundred VSP genes. Are we missing some?` | Yes; the reply gives the site's count |
| 5 | Same | Send `Yes, please broaden the first step so it also catches genes whose product is just VSP, keep the signal peptide filter, and tell me both counts.` | Text `"variant-specific surface protein" OR VSP`: 216; AND the signal peptide step = 86; both counts stated |

## U6 - A GO term by the label the site reads - fungidb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `On FungiDB, which Candida albicans SC5314 genes are predicted to be GPI-anchored and have no ortholog in Saccharomyces cerevisiae S288c?` | A GO term AND `Orthology Phylogenetic Profile` (1,681); the reply names the GO term with its label |
| 2 | Same | Send `Good. Now also require that they are expressed during hyphal growth.` | The hyphal expression step, its cutoff named in the reply |
| 3 | Cards | Answer the cards in order: approve; `Use a direct protein-prediction search if available`; approve; `Keep the current GPI-biosynthesis search` | Every option a card offers binds what it says; no card recommends a search the catalog does not hold |
| 4 | Same | Send `One gene is too few to be meaningful. Remove whichever step you added last and tell me what the count goes back to.` | A `delete_step` approval card |
| 5 | Card | Approve | The count before the hyphal step |
| 6 | Same | Send `Give me the final count in one sentence a grant reviewer would accept.` | One sentence with the count and the GO term's label |
| 7 | Same | Send `A reviewer will say GPI biosynthesis enzymes are not GPI-anchored proteins. Is there a GO cellular component term for GPI-anchored or anchored-membrane proteins on FungiDB that fits my question better? If so, use it instead and give me the new count.` | `GO Term` GO:0031225 (82) AND the profile = 58; the reply quotes the label `obsolete anchored component of membrane` |

## U7 - The closing summary names the set this conversation saved - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `I want candidate vaccine antigens in Plasmodium falciparum 3D7: surface-exposed proteins expressed in sporozoites.` | (`Predicted Signal Peptide` 479 OR `Transmembrane Domain Count` 1,628) AND the sporozoite percentile step = 549 |
| 2 | Same | Send `Thanks. Can you tell me how many genes each step returns, and does each of those numbers seem right to you? 549 feels like a lot of candidates for sporozoite surface antigens.` | Each step's count; nothing is rebuilt |
| 3 | Same | Send `Let's tighten it then. Right now signal peptide is only an alternative to the transmembrane branch. I want a signal peptide required as well, not just as one of two options.` | Signal peptide AND transmembrane (288), AND sporozoite = 125 |
| 4 | Same | Send `Good, 125 is a workable size. Now make the sporozoite expression cutoff stricter - top 5 percent instead of the top 20 - and tell me what that does to the count.` | Sporozoite 95 to 100 (463); root 50 |
| 5 | Same | Send `Actually, use the 3D7 blood-stage expression instead of sporozoite.` | The blood-stage percentile step at 95 to 100 (635); root 39 |
| 6 | Same | Send `Before I accept 39, flip the last combine - the one joining the surface features to blood-stage expression - to a UNION, and explain to me why the counts differ.` | UNION: 884 (288 + 635 - 39) |
| 7 | Same | Send `Undo that, keep the intersection.` | INTERSECT, 39 |
| 8 | Same | Send `Here are three genes I would expect a good antigen list to contain: PF3D7_0304600, PF3D7_1133400, PF3D7_0930300. Check them against the strategy - are they in the 39, and if not, which step drops them?` | 2 of 3 in the 39; the blood-stage step drops PF3D7_0304600 (3 of 3 on the signal peptide, transmembrane and combined steps) |
| 9 | Same | Send `Don't re-run it - the control check you already ran reported 2 of 3 recovered on the final step, so one of my three is being dropped somewhere; I'll come back to that. For now, save the current 39-gene result as a gene set called 'vaccine candidates draft'.` | A gene set of 39 genes named `vaccine candidates draft` |
| 10 | Same | Send `Now the other direction: 39 is on the short side and one of my three known antigens is missing from it. If you had to drop exactly one step to loosen the list, which would you drop and why?` | Advice naming the step by its display name, no step id |
| 11 | Same | Send `Agreed, drop the blood-stage expression step and tell me the new count.` | A `delete_step` approval card |
| 12 | Card | Approve | Root 288; the reply states no gap for the sporozoite or blood-stage requirement and none for words only the plan wrote |
| 13 | Same | Send `Last thing: give me a five-sentence summary of this whole session that I could put in front of my PI, including the final count and what the saved gene set holds.` | The final count 288, and the saved set `vaccine candidates draft` with its 39 genes |

## U8 - A settled question is not a gap - vectorbase

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Aedes aegypti LVP_AGWG odorant receptors that are expressed in female antennae.` | `InterPro Domain` PF02949 (76) AND the SRP171130 antennal percentile step on female 1, 3 and 5 dpe (4,174) = 15; the reply names the percentile range |
| 2 | Same | Send `Which expression dataset did you use for the female antennae, and is there a better one on VectorBase for this question?` | The dataset, and an answer to the question |
| 3 | Same | Send `Keep SRP171130 then. Can you exclude anything that is also expressed in male antennae in that same study, if the site lets you do that?` | MINUS the same search on male 1, 3 and 5 dpe (4,281) = 12; the reply states no open question about another dataset |
| 4 | Same | Send `I already told you to keep SRP171130, so that question is settled. What is the count of the final step, and give me a one-line reason for each search in the strategy.` | 12, one reason per search; the check leaves no row that no search states |

## U9 - A card answer binds its definition - amoebadb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Entamoeba histolytica HM-1:IMSS cysteine proteases with a predicted signal peptide.` | `GO Term` GO:0008234 (74) AND `Predicted Signal Peptide` (634) = 22 |
| 2 | Same | Send `Good. Can you also require that they are expressed in trophozoites, if AmoebaDB has an expression dataset for that?` | A card on what "expressed" means |
| 3 | Card | Pick `Minimum expression percentile 1` | The trophozoite percentile step at the floor the option states (a floor of 0 is no filter: 389 genes sit at percentile 0), not the site's 80th-percentile default, which keeps 1,665 genes and a root of 6; root 17 |
| 4 | Same | Send `Thanks. Now please delete the signal peptide step from the strategy.` | A `delete_step` approval card |
| 5 | Card | Approve | GO Term AND the trophozoite step = 68 |
| 6 | Same | Send `What was the count right before you deleted the signal peptide step, and what is it after?` | 17 before, 68 after; the earlier count is accepted as the one the conversation recorded |

## U10 - A genus on the portal, then orthologs - veupathdb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Across all VEuPathDB organisms, which genes have the GO term "heme binding" and are in the Plasmodium genus?` | One `GO Term` step, GO:0020037, organism the genus `Plasmodium`: 429 |
| 2 | Same | Send `Thanks. Please narrow that to Plasmodium vivax P01 only.` | The same step on `Plasmodium vivax P01`: 8 |
| 3 | Same | Send `OK. Now carry those 8 P. vivax P01 genes over to their orthologs in Plasmodium falciparum 3D7.` | `Transform by Orthology` to `Plasmodium falciparum 3D7`: 7; the searches are named by display name only |
| 4 | Same | Send `You said one of the 8 vivax genes probably has no falciparum ortholog. Which one is it? Can you check rather than guess?` | PVP01_0005540, read from the records; no gene set is left in the account |

## UA-plasmodb - The radio-off value is no text query - plasmodb

Recorded from the third dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Plasmodium knowlesi strain H genes with a Plasmodium-specific domain that have no ortholog in Homo sapiens.` | `InterPro Domain` (144) AND `Orthology Phylogenetic Profile` excluding `hsap` (2,795) = 142; Free Text `N/A` shows as the site default; Excluded Species `hsap (Homo sapiens REF)` shows as stated; no row says a sampled record does not show the organism or the domain |

## UC-piroplasmadb - An organism a text step shares is not held to the records - piroplasmadb

Recorded from the third dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Cytauxzoon felis Winnie genes with a predicted GPI anchor or a signal peptide.` | No GPI search on the site; a card offers the signal peptide alone or another evidence type; `Predicted Signal Peptide` 288 |
| 2 | Card | Pick `Specify an alternative evidence type` | A free-text card asks which evidence stands in |
| 3 | Card | Answer `Use a text search for GPI anchor in the gene product descriptions as the stand-in and keep it OR with the signal peptide` | `Text` "GPI anchor" in the product (1) UNION `Predicted Signal Peptide` (288) = 289; document_type `gene` shows as the site default; no gap for `Cytauxzoon felis Winnie`, since every sampled record is that organism |

## UA-toxodb - A step the turn created has no count before it - toxodb

Recorded from the third dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Hammondia hammondi strain H.H.34 genes with a microneme protein annotation.` | `Text` "microneme protein" in the product: 23 |
| 2 | Same | Send `Now do the same on Toxoplasma gondii ME49, and give me the Hammondia microneme genes that have an ortholog among the ME49 microneme genes.` | ME49 `Text` 25 with no count before it; the Hammondia step 23 with no count before it; `Transform by Orthology` 47; result 19 with 23 before this turn's edit; every id the reply names is a row of the facts part |
| 3 | Same | Send `Which four of the original 23 Hammondia genes dropped out of the result?` | The two listings are rows under the steps they listed; HHA_208730, HHA_208740, HHA_218310, HHA_247195 |

## UB-fungidb - An EDA cutoff shows its names and the compute's counts - fungidb

Recorded from the third dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Cryptococcus neoformans H99 genes upregulated at 37 degrees compared with 30 degrees.` | One EDA step: 8 genes; Subset `genotype is one of wild type, fraction is one of total`; each chosen cutoff beside its other count, 8 of 7,884 genes tested; the reply may say 37 and 30 |
| 2 | Same | Send `Please tighten the p-value cutoff to 0.001 and tell me how the count changes, with both cutoffs shown with who set them.` | 0 genes, 8 before this turn's edit; p 0.001 stated, fold change 1 chosen |

## UD-hostdb - The same sample twice - hostdb

Recorded from the third dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Mus musculus C57BL/6J genes on chromosome 17 with the GO term 'MHC class I protein complex'.` | `Genes by Genomic Location` chromosome 17: 2,268; `GO Term` GO:0042612: 11; INTERSECT 9; the sequence id reads `not set (site placeholder)` |
| 2 | Same | Send `Change the chromosome to 19. How does the count change?` | Location 1,372, 2,268 before; result 0, 9 before |
| 3 | Same | Send `Put it back to chromosome 17 and show me a sample of five genes from the result.` | Result 9, 0 before; five sampled genes |
| 4 | Same | Send `Can you show me that same sample of five genes again? I want to copy the IDs.` | The same five genes as step 3 |

## UB4-giardiadb - An unquoted text keeps its phrase reading - giardiadb

Recorded from the fourth dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Giardia muris Roberts-Thompson genes with a cysteine-rich protein annotation.` | `Text` "cysteine-rich protein" 4,497; the facts show it as the phrase at 0 genes; the organism `Giardia muris strain Roberts-Thomson` shows as stated |
| 2 | Same | Send `OK. Please exclude the genes that have a transmembrane domain from this result.` | `Transmembrane Domain Count` 563; MINUS 3,961 with 4,497 before this turn's edit |
| 3 | Same | Send `Wait, 4,497 genes before the exclusion seems like almost the whole G. muris genome. How many genes actually have the exact phrase 'cysteine-rich protein' in their product description? Just tell me, don't change the strategy yet.` | The exact phrase counts 0 genes; no edit |

## UB4-tritrypdb - A chosen sample is not the site's default - tritrypdb

Recorded from the fourth dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Leishmania infantum JPCM5 genes with a zinc finger domain that are expressed in amastigotes.` | `InterPro Domain` 122 INTERSECT the amastigote percentile step 1,603 = 28; the organism shows as stated |
| 2 | Same | Send `Thanks. Actually, change the stage to promastigotes instead of amastigotes, keeping the zinc finger part the same.` | The promastigote step 569 with Samples `0 hr` chosen (851 at all 8 options); INTERSECT 5 with 28 before; the reply never calls the 0 hr sample the site's default |


## UA4-toxodb - A count question is answered with its count - toxodb

Recorded from the fourth dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Toxoplasma gondii GT1 genes with a signal peptide that have no ortholog in Neospora caninum Liverpool.` | `Predicted Signal Peptide` 680 INTERSECT `Orthology Phylogenetic Profile` 1,240 = 53; the facts draw no Profile Pattern row |
| 2 | Same | Send `The facts list shows the excluded species as Neospora caninum Liverpool, so I think that part is fine. Just a question, don't change anything: how many of the signal-peptide genes did the ortholog filter remove?` | The reply says 627 (680 less 53); no edit |

## UD4-microsporidiadb - A count question is answered with its count - microsporidiadb

Recorded from the fourth dry UAT; counts read on 2026-09-30.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Encephalitozoon intestinalis ATCC 50506 genes with a signal peptide and no ortholog in Encephalitozoon cuniculi GB-M1.` | `Predicted Signal Peptide` 66 INTERSECT `Orthology Phylogenetic Profile` 129 = 9 |
| 2 | Same | Send `how many genes would there be without the ortholog filter` | The reply says 66 against 9, a difference of 57; no edit |

## UCORE-A-cryptodb - A comparison states its counts - cryptodb

Counts read on 2026-09-30 from the site, build 71.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Cryptosporidium parvum IOWA-ATCC genes whose product description matches mucin*.` | One `Text` step on the product field: 2 genes |
| 2 | Same | Send `Just a question, don't change the strategy: how many genes would mucin* match if every text field were searched instead of the product field alone, and how many of those are beyond the ones here?` | The reply says 84 genes over every text field and 82 genes beyond the 2 here, both rendered from the comparison; the strategy keeps its one step |

## UCORE-D-veupathdb - A narrower organism replaces the family - veupathdb

Counts read on 2026-09-30, build 71.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Genes across Trypanosomatidae with the GO term 'glycosome'.` | `GO Term` GO:0020015, shown by its label glycosome |
| 2 | Same | Send `Please narrow that to Leishmania donovani BPK282A1, and show me the count before next to the count after.` | 115 genes on Leishmania donovani BPK282A1; the facts show Trypanosomatidae replaced by Leishmania donovani BPK282A1, never withdrawn, and the GO term keeps its label |

## UCORE-A-plasmodb - A requirement dropped by one card retires - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Plasmodium falciparum 3D7 genes with a transmembrane domain and a predicted apicoplast targeting signal.` | `Transmembrane Domain Count` INTERSECT the PlasmoAP apicoplast targeting step |
| 2 | Same | Send `Drop the transmembrane domain requirement: remove that step.` | One `delete_step` approval card |
| 3 | Card | Approve | The PlasmoAP step alone; the transmembrane domain requirement shows as withdrawn, the organism and the apicoplast signal stay, and no gap says nothing in the strategy answers the apicoplast signal |
