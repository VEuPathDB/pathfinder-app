# Backlog

Everything known to be outstanding, ranked by whether a tester would hit it, then by what moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

### Before testers: a tester would hit it

1. [A suggested prompt is measured before it ships](a-suggested-prompt-is-measured-before-it-ships.md) ([#24](https://github.com/VEuPathDB/pathfinder-app/issues/24)) - every offered suggestion has one recorded passing run; let biologists propose candidates in a reviewable file, each offered only after its recorded run meets the stated expectation.
2. [The last pushed round is checked live](a-pushed-round-is-checked-live.md) ([#14](https://github.com/VEuPathDB/pathfinder-app/issues/14)) - the all-organism singleton ranking and the audit follow-up passed live; one live build refused once remains.
3. [A canvas edit waits for the turn](a-canvas-edit-waits-for-the-turn.md) - `/operations` applies a canvas edit while a turn of the same thread runs, so one commit's whole-tree write drops the other's edit; refuse or queue it while `claim_settled_thread` names the thread busy.
4. [A sample shown again is the same records](a-sample-shown-again-is-the-same-records.md) - asked for the same sample of five genes again, the Lead reads the first five ids of the step instead of the five it showed; show it again from what the thread recorded.
5. [A failed differential-expression job says why](a-failed-differential-expression-job-says-why.md) - four EDA DESeq jobs on QA ended "failed" with no reason, three of them on one sample per group or fewer; count each group's samples before the job and say why it cannot run.
6. [An ortholog in a genus means any of its genomes](an-ortholog-in-a-genus-means-any-of-its-genomes.md) - "an ortholog in Plasmodium" bound all 61 Plasmodium genomes as required (501 Cryptosporidium genes); an ortholog in any genome of a clade needs a union or a phyletic expression, measured on QA.
7. [An upper bound alone keeps no default lower bound](an-upper-bound-alone-keeps-no-default-lower-bound.md) - "under 30 kDa" kept the Molecular Weight search's default 10,000 Da minimum; a one-sided range binds the other side at the published limit.

### After testers

8. [Requirements are typed data](requirements-are-typed-data.md) - every decision about a requirement reads words of a model-written value; replace `requested_value` with typed requirements carrying an id, a verbatim quote and criterion links, and move attribution, lifecycle, drops and the verdict's comparisons onto them in steps 3 to 15.
9. [A count per species groups the genome codes of each species](a-count-per-species-groups-the-genome-codes.md) ([#15](https://github.com/VEuPathDB/pathfinder-app/issues/15)) - asked to aggregate a per-genome tally to species, an edit bound a phyletic filter every species must meet and emptied the result; count the result step by genome code and sum each species' codes from the site's taxonomy.
10. [A copy-number comparison between clades is built in bands](a-copy-number-comparison-between-clades-is-built-in-bands.md) ([#17](https://github.com/VEuPathDB/pathfinder-app/issues/17)) - "more genes per genome in Toxoplasma than Plasmodium" is refused although `build_phyletic_expression` writes a clade-average comparison; guide the Lead to that pattern, offer it in the question and state the clade-average caveat.
11. [A clarifying question offers what the site can build](a-clarifying-question-offers-what-the-site-can-build.md) ([#19](https://github.com/VEuPathDB/pathfinder-app/issues/19)) - a consult asks for raw search parameters and then still refuses; it offers two or three buildable readings in the user's terms, builds the one picked, and refuses once with the nearest buildable thing.
12. [A drop card asks about a combination as one requirement](a-drop-card-asks-about-a-combination-as-one-requirement.md) - "a GPI anchor and a signal peptide" is held as one requirement, so the card offers to drop the searchable part with the unsearchable one; choose between the intent gate and the numbered list by replay.
13. [A drop card asks about a requirement the plan answers](a-drop-card-asks-about-a-requirement-the-plan-answers.md) - the card asks about every requirement the ledger lists as ungroundable, and one turn offered to drop a data type a bound transcript search answers; trace the grounding first.
14. [Thread surgery is a runtime primitive](thread-surgery-is-a-runtime-primitive.md) ([#22](https://github.com/VEuPathDB/pathfinder-app/issues/22)) - Fork and revert are copy code in PathFinder that must track rules owned by assistant-core, LangGraph and WDK; move fork into the runtime as fork_thread, make revert a fork without the tail, and give external effects a compensating saga.
15. [Every model has a catalog price](every-model-has-a-catalog-price.md) ([#23](https://github.com/VEuPathDB/pathfinder-app/issues/23)) - OpenAI and Google models have no price meter in the model catalog, so their cost comes from the bundled genai_prices snapshot; give each deployment model a meter with its provider's listed rates, including cache-write rates and long-context tiers.
16. [The remaining audit phases are built](the-remaining-audit-phases-are-built.md) ([#20](https://github.com/VEuPathDB/pathfinder-app/issues/20)) - Phase 3 tasks 19 to 22, 24 and 25 (task 24 needs approval), phase 4 task 17 and tasks 24 to 54, and phase 5 of the gene-model audit are not built; one screened finding (PfNF54_040013300, truncated model) needs a manual check.
17. [An audit screens a genome for selenoproteins](an-audit-screens-a-genome-for-selenoproteins.md) ([#21](https://github.com/VEuPathDB/pathfinder-app/issues/21)) - a genome-scope run screens length and split candidates from the gene reports; the selenoprotein check needs each genome's proteins with a `U`, which no library function reads per genome, so until one does it runs on explicit gene targets only.
18. [A gene-model audit runs on the evidence tools](a-gene-model-audit-runs-on-the-evidence-tools.md) - COMING QUESTION: a read-only evidence sub-agent ranks genes whose model two or more kinds of site evidence contradict and writes an evidence card per gene; retrospective test and a 100-gene pilot first, bulk data access before any genome-wide run.

### Internal or blocked

19. [The eval reads what the researcher sees](the-eval-reads-what-the-researcher-sees.md) - the corpus phrase checks match a reply's stored markdown, where every punctuation mark is escaped, and two cases leave the consult cards the Lead now asks unanswered; read the reply as shown and record an answer for each card.
20. [QA sites need a pass for automated clients](qa-sites-need-a-pass-for-automated-clients.md) - BLOCKED on the VEuPathDB team: outside the network the QA sites redirect every service call to a pre-release login, so the e2e jobs and both nightlies stay disabled; a stack inside the network reaches QA and the whole e2e suite passes there.
21. [The corpus holds no plan with an analysis below the root](the-corpus-holds-no-plan-with-an-analysis-below-the-root.md) - no case states two study analyses under one OR, and the requirement reports are measured by replay and unit tests only; two cases and one full corpus run on QA close both.
22. [Three site bugs are reported to VEuPathDB](three-site-bugs-are-reported-to-veupathdb.md) - OrthoMCL's Single Copy Orthogroups runs the genome-count query (8,699 groups, largest 1,255 proteins); WDK answers 500, not 422, when a hidden parameter empties a dependent vocabulary; the phyletic parser recurses once per operator with no bound and froze the QA OrthoMCL instance.
23. [A decision model is chosen on our own scorecards](a-decision-model-is-chosen-on-our-own-scorecards.md) - PARKED: the OpenAI Decisions API serves search candidates in veupathdb-mcp; the injection screen, VERIFY fit and disagreement flag are unwired, and Clef was never measured against Jev's scorecards.
24. [Each site release is checked for a per-user search vocabulary](each-site-release-is-checked-for-a-per-user-search-vocabulary.md) - the WDK catalog shares one copy of a search definition across logins, correct only while no gene search's vocabulary takes `user_id`; search ApiCommonModel and EbrcModelCommon at every release.
25. [A dependent pick's label is the vocabulary it was bound under](a-dependent-picks-label-is-the-vocabulary-it-was-bound-under.md) - a dependent pick is labelled under its own parents on the bind, on hydration and on replay; the site-default count still reads a dependent pick at the published default, and no recorded dependent pick has a non-empty published default yet.
26. [A recorded gold strategy builds from its file](a-recorded-gold-strategy-builds-from-its-file.md) - no recorded gold file validates as a typed step tree, so the gold build route builds none of them.
27. [A histogram fit and a byValue fit agree on one step](a-histogram-fit-and-a-by-value-fit-agree-on-one-step.md) - the recorded tm_count histogram sums to 854 transcripts and the byValue report of the same search to 840, with no request bodies kept; record one step with both reports, `totalCount` and the bodies, since until then a histogram fit may overstate its total.
28. [A join under a saved-strategy branch is not measured](a-join-under-a-saved-strategy-branch-is-not-measured.md) - a combine added above a step inside an inserted saved strategy may land inside the nested strategy on the site; measure the WDK tree, then write the six headings.
29. [Parallel browser test workers act as one user](parallel-browser-test-workers-act-as-one-user.md) - Every Playwright worker carries the account's website login, which names the account's own PathFinder user ahead of the dev login, so two workers of a shard share one user's rows; give each worker its own user or run one worker per stack.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
