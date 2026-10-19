# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

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

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
