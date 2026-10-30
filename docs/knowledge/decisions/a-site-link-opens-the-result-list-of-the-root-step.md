---
type: Decision
title: A site link opens the result list of the root step
description: Every link PathFinder writes to a strategy on a VEuPathDB site is `/app/workspace/strategies/<strategy>/<root step>/summary:_default`, built in one place (`services/strategies/result_list.py`), so it opens the root step with the site's result table showing. A link to the strategy page, and a link to the step with no tab, were rejected.
tags: [frontend, strategy, site-link, wdk]
status: stable
---

# What was decided

**One builder.** `services/strategies/result_list.py::result_list_url(site_id, strategy, step)`
writes every link to a strategy on a site, and `live_result_list_url` reads the root from the
sync state. These read it: the facts part of a reply (`Open results on <Site>`), the strategy
link part, the build and edit tool results, the stopped-turn text, the evidence card, the link
of a step's records and of a column tally, and the `wdkUrl` that the rail, the canvas and the
saved list show. The site is the one the strategy lives on: the conversation's site, or the
site of the step a tally reads.

**The route is the site's own.** wdk-client serves `/workspace/strategies/:subPath*`
(`Core/routes.tsx`). `StrategyWorkspaceController` splits the sub-path into the strategy id,
the step id and a tab id, and `StrategyViewController` shows the result panel of that step.
WDK's own step link is `/workspace/strategies/<strategy>/<step>` (`StrategyUtils.getStepUrl`).
A tab id `summary:<view>` selects that summary view (`StepAnalysisSelectors.activeTab`), and
WDK gives every record class the summary view `_default`, the results table
(`SummaryView.createSupportedSummaryViews`). The tab is the same for genes, OrthoMCL groups
and proteins.

**A root PathFinder does not know is left to the site.** When the strategy is on the site but
no pushed root is known (a thread linked to a strategy id only, or a stored tree whose last
push failed), the link is the strategy page. The site then selects its own root step.

# What was rejected

**The strategy page.** The site moves to the root step, but the result panel opens the tab
the researcher last chose for that search, which is a user preference per search
(`prefSpecs.resultPanelTab`). That can be the genome view or an analysis.

**The step page with no tab.** It names the right step, and it opens the same remembered tab.

# What would prove this wrong

A site whose record class has no `_default` summary view, or a WDK release that renames the tab
ids. An unknown tab id is ignored by `activeTab`, so the link would still open the root step,
on the remembered tab.
