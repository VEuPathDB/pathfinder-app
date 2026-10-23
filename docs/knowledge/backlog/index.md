# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

52. [The every-species reading is built by the library](the-every-species-reading-is-built-by-the-library.md) - FRAME writes presence in every species of a group by hand from the parameter's help; veupathdb-mcp gains a builder that writes it from the taxonomy, and FRAME binds it whole.
51. [A clarifying question offers what the site can build](a-clarifying-question-offers-what-the-site-can-build.md) - a consult asks for raw search parameters and then still refuses; it offers two or three buildable readings in the user's terms, builds the one picked, and refuses once with the nearest buildable thing.
50. [A copy-number comparison between clades is built in bands](a-copy-number-comparison-between-clades-is-built-in-bands.md) - "more genes per genome in Toxoplasma than Plasmodium" is refused although the phyletic expression counts proteins over a genome list; build it as count bands joined with OR and state the clade-average caveat.
49. [An audit screens a genome for selenoproteins](an-audit-screens-a-genome-for-selenoproteins.md) - a genome-scope run screens length and split candidates from the gene reports; the selenoprotein check needs each genome's proteins with a `U`, which no library function reads per genome, so until one does it runs on explicit gene targets only.
48. [An audit counts its genome reads](an-audit-counts-its-genome-reads.md) - veupathdb-py reports WDK requests to the observer and no JBrowse read, so a run's request counts leave out every genome window its checks read; the client gains a JBrowse hook and `PathfinderObserver` counts it into the same tally.
47. [A built step is counted by a column](a-built-step-is-counted-by-a-column.md) - "which organisms have the most singleton groups" needs a count over a transformed result, and the Lead's count_by_column counts only a catalog search; give the Lead the byValue step reader VERIFY already has, and name the transform-then-count pattern.
46. [An answer opens its result on the site](an-answer-opens-its-result-on-the-site.md) - the site link sits only in the rail's Strategy panel and the canvas top bar; the answer that reports a result opens that step's records on the site in one click.
45. [An "all" over many genomes is asked about](an-all-over-many-genomes-is-asked-about.md) - presence in every one of 61 Plasmodium genomes drops a group missing from one draft assembly; the turn asks whether "all" means every genome, a share such as 90%, or every species, and binds absence without asking.
44. [A mention of Settings opens Settings](a-mention-of-settings-opens-settings.md) - the first-run notice and the help pages name Settings tabs in plain text while the only way in is the gear at the bottom left; each mention opens Settings on its tab, and the gear moves beside Help.
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

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
