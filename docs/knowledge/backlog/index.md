# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

60. [The last pushed round is checked live](a-pushed-round-is-checked-live.md) - The gene-certainty attribution, the resent-build bound and the per-organism singleton count across all of OrthoMCL were tested only against recorded turns; run them once live.
61. [A reply never claims an approval it did not get](a-reply-never-claims-an-approval-it-did-not-get.md) - A reply said 'the reading you approved' when the researcher approved nothing and FRAME chose the reading; a typed check must tie such a claim to a recorded card answer.
62. [A phyletic set is described once](a-phyletic-set-is-described-once.md) - veupathdb-py's phyletic expression description repeats a set's genome and species breakdown for every clause over the same set ('at least 139 genomes of Apicomplexa (...) and exactly 139 proteins of Apicomplexa (...)'); describe a set once, release veupathdb-py and veupathdb-mcp, and take both pins.
63. [Guards that refuse too much are narrowed](guards-that-refuse-too-much-are-narrowed.md) - Several reply and build guards refuse correct output or cover only part of their case; each needs a typed narrowing or widening.
65. [The edited browser tests run](the-edited-browser-tests-run.md) - Sixteen Playwright specs and fixtures were edited for the settings gear move and the appendix change without being run; run the e2e suite against a stack and fix what fails.
66. [Thread surgery is a runtime primitive](thread-surgery-is-a-runtime-primitive.md) - Fork and revert are copy code in PathFinder that must track rules owned by assistant-core, LangGraph and WDK; move fork into the runtime as fork_thread, make revert a fork without the tail, and give external effects a compensating saga.
67. [The remaining audit phases are built](the-remaining-audit-phases-are-built.md) - Phase 3 tasks 19 to 25 (task 24 needs approval), phase 4 task 17 and tasks 24 to 54, and phase 5 of the gene-model audit are not built; one screened finding (PfNF54_040013300, truncated model) needs a manual check.
68. [Every model has a catalog price](every-model-has-a-catalog-price.md) - OpenAI and Google models have no price meter in the model catalog, so their cost comes from the bundled genai_prices snapshot; give each deployment model a meter with its provider's listed rates, including cache-write rates and long-context tiers.
69. [A computed verdict is run live](a-computed-verdict-is-run-live.md) - The verdict computed from the site was tested only on recorded bodies; replay the verifying eval cases on QA and record one organism column body.
57. [A count per species groups the genome codes of each species](a-count-per-species-groups-the-genome-codes.md) - asked to aggregate a per-genome tally to species, an edit bound a phyletic filter every species must meet and emptied the result; count the result step by genome code and sum each species' codes from the site's taxonomy.
51. [A clarifying question offers what the site can build](a-clarifying-question-offers-what-the-site-can-build.md) - a consult asks for raw search parameters and then still refuses; it offers two or three buildable readings in the user's terms, builds the one picked, and refuses once with the nearest buildable thing.
50. [A copy-number comparison between clades is built in bands](a-copy-number-comparison-between-clades-is-built-in-bands.md) - "more genes per genome in Toxoplasma than Plasmodium" is refused although `build_phyletic_expression` writes a clade-average comparison; guide the Lead to that pattern, offer it in the question and state the clade-average caveat.
49. [An audit screens a genome for selenoproteins](an-audit-screens-a-genome-for-selenoproteins.md) - a genome-scope run screens length and split candidates from the gene reports; the selenoprotein check needs each genome's proteins with a `U`, which no library function reads per genome, so until one does it runs on explicit gene targets only.
47. [A member count reaches framing on the first message](a-built-step-is-counted-by-a-column.md) - a count of a result's members by a column is classified a follow-up question on a conversation with no strategy and the column tally guesses a search; the tally's refusal now names the reroute to framing, and a replay of the first message must reach `frame_problem`, build the transform and answer with the site's tally.
43. [A suggested prompt is measured before it ships](a-suggested-prompt-is-measured-before-it-ships.md) - the OrthoMCL single-copy suggestion binds a search that cannot name a clade and returns 8,699 groups from any taxa; reword it, run every suggestion once before it is offered, and let biologists propose candidates in a reviewable file, each shipped only after its measured run (depends on two veupathdb-mcp cards).
42. [A gene-model audit runs on the evidence tools](a-gene-model-audit-runs-on-the-evidence-tools.md) - COMING QUESTION: a read-only evidence sub-agent ranks genes whose model two or more kinds of site evidence contradict and writes an evidence card per gene; retrospective test and a 100-gene pilot first, bulk data access before any genome-wide run.
41. [A deleted step stays in the site's strategy](a-deleted-step-stays-in-the-sites-strategy.md) - a strategy GET on WDK saves the strategy back, and the gene-set refresh's GET overlapped a delete's step-tree write and restored the old tree; verify the tree after the write in veupathdb-py and order the refresh behind the thread lock.
40. [Each site release is checked for a per-user search vocabulary](each-site-release-is-checked-for-a-per-user-search-vocabulary.md) - the WDK catalog shares one copy of a search definition across logins, correct only while no gene search's vocabulary takes `user_id`; search ApiCommonModel and EbrcModelCommon at every release.
38. [A drop card asks about a combination as one requirement](a-drop-card-asks-about-a-combination-as-one-requirement.md) - "a GPI anchor and a signal peptide" is held as one requirement, so the card offers to drop the searchable part with the unsearchable one; choose between the intent gate and the numbered list by replay.
37. [A drop card asks about a requirement the plan answers](a-drop-card-asks-about-a-requirement-the-plan-answers.md) - the card asks about every requirement the ledger lists as ungroundable, and one turn offered to drop a data type a bound transcript search answers; trace the grounding first.
36. [The corpus holds no plan with an analysis below the root](the-corpus-holds-no-plan-with-an-analysis-below-the-root.md) - BLOCKED on QA admitting automated clients: no case states two study analyses under one OR, and the requirement reports are measured by replay and unit tests only; two cases and one full corpus run close both.
35. [A join under a saved-strategy branch is not measured](a-join-under-a-saved-strategy-branch-is-not-measured.md) - a combine added above a step inside an inserted saved strategy may land inside the nested strategy on the site; measure the WDK tree, then write the six headings.
34. [QA sites need a pass for automated clients](qa-sites-need-a-pass-for-automated-clients.md) - BLOCKED on the VEuPathDB team: outside the network the QA sites redirect every service call to a pre-release login, so the e2e jobs and both nightlies stay disabled; the e2e re-measure remains.
12. [A dependent pick's label is the vocabulary it was bound under](a-dependent-picks-label-is-the-vocabulary-it-was-bound-under.md) - a dependent pick is labelled under its own parents on the bind, on hydration and on replay; the site-default count still reads a dependent pick at the published default, and no recorded dependent pick has a non-empty published default yet.

31. [A message that commands a change is an edit when it also asks a question](a-message-that-commands-a-change-is-an-edit.md) - a command beside a question can be classified a question that withdraws nothing, and the turn answers read-only.
29. [A decision model is chosen on our own scorecards](a-decision-model-is-chosen-on-our-own-scorecards.md) - PARKED: Cloudflare's open-weight Clef and Clef-flash take Jev's request shape; the five Jev scorecards are rerun on both, on hosted Workers AI, before any decision model is wired.
53. [A recorded gold strategy builds from its file](a-recorded-gold-strategy-builds-from-its-file.md) - no recorded gold file validates as a typed step tree, so the gold build route builds none of them.

56. [A histogram fit and a byValue fit agree on one step](a-histogram-fit-and-a-by-value-fit-agree-on-one-step.md) - the recorded tm_count histogram sums to 854 transcripts and the byValue report of the same search to 840, with no request bodies kept; record one step with both reports, `totalCount` and the bodies, since until then a histogram fit may overstate its total.

54. [Three site bugs are reported to VEuPathDB](two-site-bugs-are-reported-to-veupathdb.md) - OrthoMCL's Single Copy Orthogroups runs the genome-count query (8,699 groups, largest 1,255 proteins); WDK answers 500, not 422, when a hidden parameter empties a dependent vocabulary; the phyletic parser recurses once per operator with no bound and froze the QA OrthoMCL instance.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
